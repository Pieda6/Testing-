"""Mutation battery for dynamo/exec-calendar-triage.

The Tier-2 execution probe mutates the stated policy and checks whether the
schedule changes. A rule that can be mutated with no effect is decorative: a
solver that gets it wrong still scores 1.0, which makes the held-out coverage
narrow and hardcodable.

This runs the same test locally, over every rule in the policy, so the data can
be tuned until each rule demonstrably does work.
"""
import importlib.util
import json

_spec = importlib.util.spec_from_file_location(
    "s", "/home/user/Testing-/task4/solution/solve.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
_ORIG = S.can_attend


def _checker(lunch_exempt=1, cap_strict=True, travel=True, hours=True,  # noqa
             overlap=True, pto=True, cap=True, lunch=True, home=True):
    def f(cal, di, day, start, dur, site, priority, cfg, sites):
        if pto and day in cal.pto:
            return False
        end = start + dur
        if hours:
            ws, we = cal.work_window(di)
            if start < ws or end > we:
                return False
        if cap:
            u = cal.used.get(day, 0) + dur
            over = u > cfg["daily_cap_minutes"] if cap_strict else u >= cfg["daily_cap_minutes"]
            if over:
                return False
        if lunch and priority != lunch_exempt:
            ls, le = cal.lunch(di, S.hhmm(cfg["lunch_start_local"]),
                               cfg["lunch_minutes"])
            if start < le and ls < end:
                return False
        pv = nx = None
        for bs, be, bsite in cal.busy:
            if overlap and bs < end and start < be:
                return False
            if be <= start and (pv is None or be > pv[1]):
                pv = (bs, be, bsite)
            if bs >= end and (nx is None or bs < nx[0]):
                nx = (bs, be, bsite)
        ws2, we2 = cal.work_window(di)
        if travel:
            if pv is None:
                if home and start - ws2 < S.travel_needed(sites, cal.home, site):
                    return False
            elif start - pv[1] < S.travel_needed(sites, pv[2], site):
                return False
            if nx is None:
                if home and we2 - end < S.travel_needed(sites, site, cal.home):
                    return False
            elif nx[0] - end < S.travel_needed(sites, site, nx[2]):
                return False
        return True
    return f


def run(data_dir, order="policy", **kw):
    P = json.load(open(data_dir + "/people.json"))
    St = json.load(open(data_dir + "/sites.json"))
    R = json.load(open(data_dir + "/requests.json"))["requests"]
    S.can_attend = _checker(**kw) if kw else _ORIG

    keys = {"policy": lambda r: (r["priority"], -len(r["required"]), r["id"]),
            "priority_only": lambda r: (r["priority"],),
            "catalogue": lambda r: 0}
    out = _solve_with_order(S, P, St, R, sorted(R, key=keys[order]),
                            prune=kw.get("hours", True))
    S.can_attend = _ORIG
    return out


def _solve_with_order(S, people_doc, sites, requests, order, prune=True):
    days = people_doc["days"]
    slot = people_doc["slot_minutes"]
    cals = {p["id"]: S.Calendar(p, days) for p in people_doc["people"]}
    placed = {}
    for req in order:
        dur, site, prio = req["duration_min"], req["site"], req["priority"]
        d_from = days.index(req["earliest_day"])
        d_to = days.index(req["latest_day"])
        chosen = None
        for d in range(d_from, d_to + 1):
            day = days[d]
            if prune:
                wins = [cals[p].work_window(d) for p in req["required"]]
                lo, hi = max(w[0] for w in wins), min(w[1] for w in wins)
                if hi - lo < dur:
                    continue
            else:
                lo, hi = d * 1440, (d + 1) * 1440
            first = ((lo + slot - 1) // slot) * slot
            for start in range(first, hi - dur + 1, slot):
                if all(S.can_attend(cals[p], d, day, start, dur, site, prio,
                                    people_doc, sites) for p in req["required"]):
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
            if S.can_attend(cals[p], d, day, start, dur, site, prio,
                            people_doc, sites):
                going.append(p)
        going.sort()
        for p in going:
            cals[p].add(start, start + dur, site, day)
        placed[req["id"]] = {"status": "scheduled", "day": day,
                             "start_utc": S.fmt_utc(d, days, start),
                             "attendees": going}
    return [dict(id=r["id"], **placed[r["id"]]) for r in requests]


MUTATIONS = [
    ("lunch exemption on P2 not P1", dict(lunch_exempt=2)),
    ("daily cap uses >= not >",      dict(cap_strict=False)),
    ("travel buffers dropped",       dict(travel=False)),
    ("working hours ignored",        dict(hours=False)),
    ("daily cap ignored",            dict(cap=False)),
    ("protected lunch ignored",      dict(lunch=False)),
    ("PTO ignored",                  dict(pto=False)),
    ("home-site travel ignored",     dict(home=False)),
]
ORDER_MUTATIONS = [
    ("ordered by priority only", "priority_only"),
    ("ordered by catalogue",     "catalogue"),
]


def report(data_dir):
    base = run(data_dir)
    rows = []
    for name, kw in MUTATIONS:
        got = run(data_dir, **kw)
        rows.append((name, [a["id"] for a, b in zip(got, base) if a != b]))
    for name, order in ORDER_MUTATIONS:
        got = run(data_dir, order=order)
        rows.append((name, [a["id"] for a, b in zip(got, base) if a != b]))
    return base, rows


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "/home/user/Testing-/task4/environment/data"
    base, rows = report(d)
    n = sum(1 for r in base if r["status"] == "scheduled")
    print("baseline: %d scheduled, %d declined" % (n, len(base) - n))
    inert = 0
    for name, diff in rows:
        if diff:
            print("  BINDS   %-32s %d rows (%s)" % (name, len(diff), ", ".join(diff[:4])))
        else:
            print("  INERT   %-32s no effect" % name)
            inert += 1
    print("\n%d of %d rules inert" % (inert, len(rows)))
    raise SystemExit(1 if inert else 0)
