"""Reference scheduler for dynamo/exec-calendar-triage.

The booking policy stated in the task description fully determines one
schedule. This implements it directly; there is no search and no heuristic.

Time is handled as integer minutes since 2026-03-02T00:00:00Z. Every person
carries an explicit UTC offset, so no time zone database is consulted and the
result does not depend on the platform. Local midnight of day d for a person
whose offset is `off` sits at (d * 1440 - off) UTC minutes, which is the one
conversion the whole file rests on.

Order of work:

  1. Sort the requests the way the policy says they get considered: priority
     ascending, then required-attendee count descending, then id ascending.
  2. For each request in that order, walk the days of its window in order and
     the 15-minute grid within each day in order, and take the FIRST start that
     every required attendee can make. Because the scan order is total, the
     choice is unique -- there is no tie to break.
  3. Having fixed the slot, admit each optional attendee who independently
     clears the same checks.
  4. Commit the booking so it constrains everything placed after it.

A slot works for a person only if all of these hold: they are not on PTO that
day; the meeting sits inside their working window; it does not overlap anything
already on their calendar; it does not touch their protected lunch unless the
meeting is priority 1; it does not push their booked minutes for the day past
the cap; and there is enough room to travel from whatever precedes it and to
whatever follows it.

No answer key is consulted; only /app/data.
"""
import json

DATA = "/app/data"
OUT = "/app/schedule.json"


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt_utc(day_index, days, minute_of_week):
    """Minutes-since-week-epoch -> ISO 8601 Zulu."""
    import datetime
    base = datetime.datetime.strptime(days[0], "%Y-%m-%d")
    t = base + datetime.timedelta(minutes=minute_of_week)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Calendar:
    """Per-person occupied intervals, in UTC minutes, each tagged with a site."""

    def __init__(self, person, days):
        self.p = person
        self.days = days
        self.off = person["utc_offset_min"]
        self.ws = hhmm(person["work_start_local"])
        self.we = hhmm(person["work_end_local"])
        self.pto = set(person["pto_days"])
        self.busy = []          # (start, end, site)
        self.used = {}          # day -> booked minutes
        for c in person["commitments"]:
            d = days.index(c["day"])
            s = self.local_to_utc(d, hhmm(c["start_local"]))
            self.busy.append((s, s + c["duration_min"], c["site"]))
            self.used[c["day"]] = self.used.get(c["day"], 0) + c["duration_min"]
        self.busy.sort()

    def local_to_utc(self, day_index, local_min):
        return day_index * 1440 - self.off + local_min

    def work_window(self, day_index):
        return (self.local_to_utc(day_index, self.ws),
                self.local_to_utc(day_index, self.we))

    def lunch(self, day_index, lunch_start, lunch_len):
        s = self.local_to_utc(day_index, lunch_start)
        return (s, s + lunch_len)

    def add(self, start, end, site, day):
        self.busy.append((start, end, site))
        self.busy.sort()
        self.used[day] = self.used.get(day, 0) + (end - start)


def travel_needed(sites, a, b):
    if a == b:
        return 0
    if a == "remote" or b == "remote":
        return sites["remote_switch_min"]
    return sites["travel_min"][a][b]


def can_attend(cal, day_index, day, start, dur, site, priority, cfg, sites):
    """Every condition the policy places on one person for one slot."""
    if day in cal.pto:
        return False
    end = start + dur

    ws, we = cal.work_window(day_index)
    if start < ws or end > we:
        return False

    if cal.used.get(day, 0) + dur > cfg["daily_cap_minutes"]:
        return False

    if priority != 1:
        ls, le = cal.lunch(day_index, hhmm(cfg["lunch_start_local"]),
                           cfg["lunch_minutes"])
        if start < le and ls < end:
            return False

    prev_item = None
    next_item = None
    for bs, be, bsite in cal.busy:
        if bs < end and start < be:
            return False                    # overlap
        if be <= start and (prev_item is None or be > prev_item[1]):
            prev_item = (bs, be, bsite)
        if bs >= end and (next_item is None or bs < next_item[0]):
            next_item = (bs, be, bsite)

    if prev_item is not None:
        if start - prev_item[1] < travel_needed(sites, prev_item[2], site):
            return False
    if next_item is not None:
        if next_item[0] - end < travel_needed(sites, site, next_item[2]):
            return False
    return True


def solve(people_doc, sites, requests):
    days = people_doc["days"]
    slot = people_doc["slot_minutes"]
    cfg = people_doc
    cals = {p["id"]: Calendar(p, days) for p in people_doc["people"]}

    order = sorted(requests,
                   key=lambda r: (r["priority"], -len(r["required"]), r["id"]))

    placed = {}
    for req in order:
        dur = req["duration_min"]
        site = req["site"]
        prio = req["priority"]
        d_from = days.index(req["earliest_day"])
        d_to = days.index(req["latest_day"])

        chosen = None
        for d in range(d_from, d_to + 1):
            day = days[d]
            # Candidate window: the intersection of every required attendee's
            # working window for this day, walked on the grid.
            wins = [cals[p].work_window(d) for p in req["required"]]
            lo = max(w[0] for w in wins)
            hi = min(w[1] for w in wins)
            if hi - lo < dur:
                continue
            first = ((lo + slot - 1) // slot) * slot
            for start in range(first, hi - dur + 1, slot):
                if all(can_attend(cals[p], d, day, start, dur, site, prio,
                                  cfg, sites) for p in req["required"]):
                    chosen = (d, day, start)
                    break
            if chosen:
                break

        if chosen is None:
            placed[req["id"]] = {"status": "declined", "day": "",
                                 "start_utc": "", "attendees": []}
            continue

        d, day, start = chosen
        going = list(req["required"])
        for p in req["optional"]:
            if can_attend(cals[p], d, day, start, dur, site, prio, cfg, sites):
                going.append(p)
        going.sort()
        for p in going:
            cals[p].add(start, start + dur, site, day)

        placed[req["id"]] = {
            "status": "scheduled",
            "day": day,
            "start_utc": fmt_utc(d, days, start),
            "attendees": going,
        }

    # Emit in catalogue order, not placement order.
    return [dict(id=r["id"], **placed[r["id"]]) for r in requests]


def main():
    with open("%s/people.json" % DATA) as f:
        people_doc = json.load(f)
    with open("%s/sites.json" % DATA) as f:
        sites = json.load(f)
    with open("%s/requests.json" % DATA) as f:
        requests = json.load(f)["requests"]

    rows = solve(people_doc, sites, requests)
    with open(OUT, "w") as f:
        json.dump({"schedule": rows}, f)

    n_sched = sum(1 for r in rows if r["status"] == "scheduled")
    print("scheduled %d of %d requests (%d declined) -> %s"
          % (n_sched, len(rows), len(rows) - n_sched, OUT))


if __name__ == "__main__":
    main()
