"""Feasibility + exact optimisation core for the redesigned calendar task.

The world (people, sites, travel, lunch, cap, PTO, working hours, home-site
arrival) is unchanged and already mutation-tested. What changes is what the task
asks for: instead of a procedure that produces a schedule, the spec states what
makes a schedule the right one, and the solver has to search for it.

Objective, minimised lexicographically:
  1. -(scheduled priority-1 count), -(priority-2 count), -(priority-3 count)
  2. then, over requests in id order, key (0, day, start) if scheduled and
     (1, 0, 0) if declined -- so an earlier id being scheduled beats anything a
     later id could gain, and among scheduled the earlier slot wins.
This is a total order over schedules, so the optimum is unique.
"""
import json


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class World:
    def __init__(self, data_dir):
        self.P = json.load(open("%s/people.json" % data_dir))
        self.S = json.load(open("%s/sites.json" % data_dir))
        self.R = json.load(open("%s/requests.json" % data_dir))["requests"]
        self.days = self.P["days"]
        self.slot = self.P["slot_minutes"]
        self.cap = self.P["daily_cap_minutes"]
        self.lstart = hhmm(self.P["lunch_start_local"])
        self.llen = self.P["lunch_minutes"]
        self.who = {p["id"]: p for p in self.P["people"]}

    def travel(self, a, b):
        if a == b:
            return 0
        if a == "remote" or b == "remote":
            return self.S["remote_switch_min"]
        return self.S["travel_min"][a][b]

    def utc(self, pid, di, local_min):
        return di * 1440 - self.who[pid]["utc_offset_min"] + local_min

    def window(self, pid, di):
        p = self.who[pid]
        return (self.utc(pid, di, hhmm(p["work_start_local"])),
                self.utc(pid, di, hhmm(p["work_end_local"])))


class State:
    """Per-person busy intervals and booked minutes. Copy-on-write via clone."""

    __slots__ = ("busy", "used")

    def __init__(self, world=None):
        self.busy = {}
        self.used = {}
        if world is None:
            return
        for pid, p in world.who.items():
            items = []
            for c in p["commitments"]:
                di = world.days.index(c["day"])
                s = world.utc(pid, di, hhmm(c["start_local"]))
                items.append((s, s + c["duration_min"], c["site"], c["day"]))
                self.used[(pid, c["day"])] = (
                    self.used.get((pid, c["day"]), 0) + c["duration_min"])
            items.sort()
            self.busy[pid] = items

    def clone(self):
        s = State()
        s.busy = {k: list(v) for k, v in self.busy.items()}
        s.used = dict(self.used)
        return s

    def add(self, pid, start, end, site, day):
        self.busy[pid].append((start, end, site, day))
        self.busy[pid].sort()
        self.used[(pid, day)] = self.used.get((pid, day), 0) + (end - start)


def can_attend(w, st, pid, di, day, start, dur, site, prio):
    p = w.who[pid]
    if day in p["pto_days"]:
        return False
    end = start + dur
    ws, we = w.window(pid, di)
    if start < ws or end > we:
        return False
    if st.used.get((pid, day), 0) + dur > w.cap:
        return False
    if prio != 1:
        ls = w.utc(pid, di, w.lstart)
        if start < ls + w.llen and ls < end:
            return False
    prev = nxt = None
    for bs, be, bsite, bday in st.busy[pid]:
        if bs < end and start < be:
            return False
        if bday != day:
            continue
        if be <= start and (prev is None or be > prev[0]):
            prev = (be, bsite)
        if bs >= end and (nxt is None or bs < nxt[0]):
            nxt = (bs, bsite)
    if prev is None:
        if start - ws < w.travel(p["home_site"], site):
            return False
    elif start - prev[0] < w.travel(prev[1], site):
        return False
    if nxt is not None and nxt[0] - end < w.travel(site, nxt[1]):
        return False
    return True


def slots_for(w, st, req):
    """All feasible (day_index, day, start) for req, in day-then-time order."""
    out = []
    dur, site, prio = req["duration_min"], req["site"], req["priority"]
    for di in range(w.days.index(req["earliest_day"]),
                    w.days.index(req["latest_day"]) + 1):
        day = w.days[di]
        wins = [w.window(p, di) for p in req["required"]]
        lo, hi = max(a for a, _ in wins), min(b for _, b in wins)
        if hi - lo < dur:
            continue
        start = ((lo + w.slot - 1) // w.slot) * w.slot
        while start + dur <= hi:
            if all(can_attend(w, st, p, di, day, start, dur, site, prio)
                   for p in req["required"]):
                out.append((di, day, start))
            start += w.slot
    return out


def attendees(w, st, req, di, day, start):
    going = list(req["required"])
    for p in req["optional"]:
        if can_attend(w, st, p, di, day, start, req["duration_min"],
                      req["site"], req["priority"]):
            going.append(p)
    going.sort()
    return going


def place(w, st, req, di, day, start):
    going = attendees(w, st, req, di, day, start)
    for p in going:
        st.add(p, start, start + req["duration_min"], req["site"], day)
    return going
