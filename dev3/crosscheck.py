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

    def ok(pid, day, start, dur, site, prio):
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
        booked = sum(e - s for s, e, _, d in book[pid] if d == day)
        if booked + dur > cap:
            return False
        prev_i = next_i = None
        for bs, be, st, bd in book[pid]:
            if bs < end and start < be:
                return False
            if be <= start and (prev_i is None or be > prev_i[0]):
                prev_i = (be, st)
            if bs >= end and (next_i is None or bs < next_i[0]):
                next_i = (bs, st)
        # Travel in from the home site to the first engagement of the day, and
        # home again from the last.
        ws_ = utc(pid, day, hhmm(p["work_start_local"]))
        we_ = utc(pid, day, hhmm(p["work_end_local"]))
        if prev_i is None:
            if start - ws_ < trav(home, site):
                return False
        elif start - prev_i[0] < trav(prev_i[1], site):
            return False
        if next_i is None:
            if we_ - end < trav(site, home):
                return False
        elif next_i[0] - end < trav(site, next_i[1]):
            return False
        return True

    order = sorted(R, key=lambda r: (r["priority"], -len(r["required"]), r["id"]))
    res = {}
    for r in order:
        dur, site, prio = r["duration_min"], r["site"], r["priority"]
        hit = None
        for day in days:
            if not (r["earliest_day"] <= day <= r["latest_day"]):
                continue
            lo = max(utc(p, day, hhmm(who[p]["work_start_local"]))
                     for p in r["required"])
            hi = min(utc(p, day, hhmm(who[p]["work_end_local"]))
                     for p in r["required"])
            t = -(-lo // slot) * slot
            while t + dur <= hi:
                if all(ok(p, day, t, dur, site, prio) for p in r["required"]):
                    hit = (day, t)
                    break
                t += slot
            if hit:
                break
        if not hit:
            res[r["id"]] = {"status": "declined", "day": "", "start_utc": "",
                            "attendees": []}
            continue
        day, t = hit
        going = sorted(set(r["required"]) |
                       {p for p in r["optional"]
                        if ok(p, day, t, dur, site, prio)})
        for p in going:
            book[p].append((t, t + dur, site, day))
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
