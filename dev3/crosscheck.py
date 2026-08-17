"""Second, independent implementation of the booking policy.

Written from the policy text rather than from solve.py, in a different style
(explicit minute sets instead of interval scans) so that a shared bug is
unlikely. If this and solve.py agree on every request, the policy pins one
schedule and the task is safe to grade exactly.
"""
import json
import sys
from datetime import datetime, timedelta


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def run(data_dir="."):
    P = json.load(open("%s/people.json" % data_dir))
    S = json.load(open("%s/sites.json" % data_dir))
    R = json.load(open("%s/requests.json" % data_dir))["requests"]

    days = P["days"]
    slot = P["slot_minutes"]
    cap = P["daily_cap_minutes"]
    lstart, llen = hhmm(P["lunch_start_local"]), P["lunch_minutes"]
    who = {p["id"]: p for p in P["people"]}

    def utc(pid, day, lm):
        return days.index(day) * 1440 - who[pid]["utc_offset_min"] + lm

    def trav(a, b):
        if a == b:
            return 0
        return (S["remote_switch_min"] if "remote" in (a, b)
                else S["travel_min"][a][b])

    # book[pid] = list of (start, end, site, day)
    book = {pid: [] for pid in who}
    for pid, p in who.items():
        for c in p["commitments"]:
            s = utc(pid, c["day"], hhmm(c["start_local"]))
            book[pid].append((s, s + c["duration_min"], c["site"], c["day"]))

    def ok(bk, pid, day, start, dur, site, prio):
        p = who[pid]
        home = p["home_site"]
        if day in p["pto_days"]:
            return False
        end = start + dur
        if start < utc(pid, day, hhmm(p["work_start_local"])):
            return False
        if end > utc(pid, day, hhmm(p["work_end_local"])):
            return False
        if prio != 1:
            ls = utc(pid, day, lstart)
            if start < ls + llen and ls < end:
                return False
        booked = sum(e - s for s, e, _, d in bk[pid] if d == day)
        if booked + dur > cap:
            return False
        prev_i = next_i = None
        for bs, be, st, bd in bk[pid]:
            if bs < end and start < be:
                return False
            if bd != day:
                continue        # only same-day items count as neighbours
            if be <= start and (prev_i is None or be > prev_i[0]):
                prev_i = (be, st)
            if bs >= end and (next_i is None or bs < next_i[0]):
                next_i = (bs, st)
        # Travel in from the home site to the first engagement of the day. The
        # journey home afterwards is on their own time, so no end-of-day check.
        ws_ = utc(pid, day, hhmm(p["work_start_local"]))
        if prev_i is None:
            if start - ws_ < trav(home, site):
                return False
        elif start - prev_i[0] < trav(prev_i[1], site):
            return False
        if next_i is not None and next_i[0] - end < trav(site, next_i[1]):
            return False
        return True

    def slots_for(bk, r, limit=None):
        """Feasible slots in day-then-time order, using calendar state bk."""
        found = []
        dur, site, prio = r["duration_min"], r["site"], r["priority"]
        for day in days:
            if not (r["earliest_day"] <= day <= r["latest_day"]):
                continue
            lo = max(utc(p, day, hhmm(who[p]["work_start_local"]))
                     for p in r["required"])
            hi = min(utc(p, day, hhmm(who[p]["work_end_local"]))
                     for p in r["required"])
            t = -(-lo // slot) * slot
            while t + dur <= hi:
                if all(ok(bk, p, day, t, dur, site, prio) for p in r["required"]):
                    found.append((day, t))
                    if limit and len(found) >= limit:
                        return found
                t += slot
        return found

    def who_comes(bk, r, day, t):
        return sorted(set(r["required"]) |
                      {p for p in r["optional"]
                       if ok(bk, p, day, t, r["duration_min"], r["site"],
                             r["priority"])})

    def put(bk, r, day, t, people):
        for p in people:
            bk[p] = bk[p] + [(t, t + r["duration_min"], r["site"], day)]

    def fill(bk, queue):
        n = 0
        for r in queue:
            hit = slots_for(bk, r, limit=1)
            if not hit:
                continue
            day, t = hit[0]
            put(bk, r, day, t, who_comes(bk, r, day, t))
            n += 1
        return n

    order = sorted(R, key=lambda r: (r["priority"], -len(r["required"]), r["id"]))
    res = {}
    for idx, r in enumerate(order):
        cands = slots_for(book, r, limit=6)
        if not cands:
            res[r["id"]] = {"status": "declined", "day": "", "start_utc": "",
                            "attendees": []}
            continue
        pick = None
        for day, t in cands:
            trial = {k: list(v) for k, v in book.items()}
            put(trial, r, day, t, who_comes(trial, r, day, t))
            kept = fill(trial, order[idx + 1:idx + 9])
            if pick is None or kept > pick[0]:
                pick = (kept, day, t)
        _, day, t = pick
        going = who_comes(book, r, day, t)
        put(book, r, day, t, going)
        iso = (datetime.strptime(days[0], "%Y-%m-%d")
               + timedelta(minutes=t)).strftime("%Y-%m-%dT%H:%M:%SZ")
        res[r["id"]] = {"status": "scheduled", "day": day, "start_utc": iso,
                        "attendees": going}

    return [dict(id=r["id"], **res[r["id"]]) for r in R]


if __name__ == "__main__":
    mine = run(sys.argv[1] if len(sys.argv) > 1 else ".")
    theirs = json.load(open(sys.argv[2] if len(sys.argv) > 2
                            else "expected_raw.json"))["schedule"]
    diffs = [(a["id"], a, b) for a, b in zip(mine, theirs) if a != b]
    print("cross-check: %d of %d rows agree" % (len(mine) - len(diffs), len(mine)))
    for rid, a, b in diffs[:10]:
        print("  %s\n    crosscheck: %s\n    solver    : %s" % (rid, a, b))
    sys.exit(1 if diffs else 0)
