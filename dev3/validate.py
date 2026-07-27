"""Independent constraint checker for dynamo/exec-calendar-triage.

Deliberately shares no code with solve.py. It re-derives every interval from the
raw inputs and asserts the produced schedule satisfies each rule in the policy.
If the solver has a bug, this is what catches it before the schedule becomes
ground truth.

It checks the constraints, not the choice of slot: satisfying every rule is
necessary but not sufficient, since the policy also demands the EARLIEST
feasible slot. Slot minimality is checked separately in check_minimality.py.
"""
import json
import sys
from datetime import datetime


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def load(path):
    with open(path) as f:
        return json.load(f)


def main(data_dir=".", sched_path="expected_raw.json"):
    people_doc = load("%s/people.json" % data_dir)
    sites = load("%s/sites.json" % data_dir)
    requests = {r["id"]: r for r in load("%s/requests.json" % data_dir)["requests"]}
    rows = load(sched_path)["schedule"]

    days = people_doc["days"]
    cap = people_doc["daily_cap_minutes"]
    lunch_start = hhmm(people_doc["lunch_start_local"])
    lunch_len = people_doc["lunch_minutes"]
    slot = people_doc["slot_minutes"]
    pp = {p["id"]: p for p in people_doc["people"]}
    epoch = datetime.strptime(days[0], "%Y-%m-%d")

    def to_utc(pid, day, local_min):
        return days.index(day) * 1440 - pp[pid]["utc_offset_min"] + local_min

    def travel(a, b):
        if a == b:
            return 0
        if a == "remote" or b == "remote":
            return sites["remote_switch_min"]
        return sites["travel_min"][a][b]

    # Every interval on every person's calendar: standing commitments first.
    cal = {pid: [] for pid in pp}
    for pid, p in pp.items():
        for c in p["commitments"]:
            s = to_utc(pid, c["day"], hhmm(c["start_local"]))
            cal[pid].append((s, s + c["duration_min"], c["site"], c["day"], "standing"))

    errs = []
    for row in rows:
        req = requests[row["id"]]
        if row["status"] == "declined":
            if row["day"] or row["start_utc"] or row["attendees"]:
                errs.append("%s declined but carries placement data" % row["id"])
            continue

        day = row["day"]
        start = int((datetime.strptime(row["start_utc"], "%Y-%m-%dT%H:%M:%SZ")
                     - epoch).total_seconds() // 60)
        dur = req["duration_min"]
        site = req["site"]

        if day not in days:
            errs.append("%s: unknown day %s" % (row["id"], day))
            continue
        if not (req["earliest_day"] <= day <= req["latest_day"]):
            errs.append("%s: %s outside window %s..%s"
                        % (row["id"], day, req["earliest_day"], req["latest_day"]))
        if start % slot:
            errs.append("%s: start not on the %d-minute grid" % (row["id"], slot))

        got = set(row["attendees"])
        if not set(req["required"]).issubset(got):
            errs.append("%s: missing required attendees" % row["id"])
        if not got.issubset(set(req["required"]) | set(req["optional"])):
            errs.append("%s: has attendees who were never invited" % row["id"])
        if row["attendees"] != sorted(row["attendees"]):
            errs.append("%s: attendees not sorted" % row["id"])

        for pid in row["attendees"]:
            p = pp[pid]
            if day in p["pto_days"]:
                errs.append("%s: %s is on PTO on %s" % (row["id"], pid, day))
            ws = to_utc(pid, day, hhmm(p["work_start_local"]))
            we = to_utc(pid, day, hhmm(p["work_end_local"]))
            if start < ws or start + dur > we:
                errs.append("%s: outside %s's working hours" % (row["id"], pid))
            if req["priority"] != 1:
                ls = to_utc(pid, day, lunch_start)
                if start < ls + lunch_len and ls < start + dur:
                    errs.append("%s: overlaps %s's protected lunch (priority %d)"
                                % (row["id"], pid, req["priority"]))
            cal[pid].append((start, start + dur, site, day, row["id"]))

    # Overlap, travel and daily cap, evaluated on the finished calendars.
    for pid, items in cal.items():
        items.sort()
        for i in range(1, len(items)):
            a, b = items[i - 1], items[i]
            if b[0] < a[1]:
                errs.append("%s: %s overlaps %s" % (pid, a[4], b[4]))
            elif a[3] == b[3]:
                need = travel(a[2], b[2])
                if b[0] - a[1] < need:
                    errs.append("%s: only %d min between %s (%s) and %s (%s), "
                                "needs %d" % (pid, b[0] - a[1], a[4], a[2],
                                              b[4], b[2], need))
        per_day = {}
        for s, e, _site, day, _who in items:
            per_day[day] = per_day.get(day, 0) + (e - s)
        for day, mins in per_day.items():
            if mins > cap:
                errs.append("%s: %d booked minutes on %s exceeds cap %d"
                            % (pid, mins, day, cap))

    n_sched = sum(1 for r in rows if r["status"] == "scheduled")
    print("checked %d rows (%d scheduled, %d declined)"
          % (len(rows), n_sched, len(rows) - n_sched))
    if errs:
        print("\n%d CONSTRAINT VIOLATIONS:" % len(errs))
        for e in errs[:40]:
            print("  -", e)
        sys.exit(1)
    print("no constraint violations")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
