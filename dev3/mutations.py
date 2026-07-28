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
             overlap=True, pto=True, cap=True, lunch=True, home=True,
             same_day=True):
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
        for bs, be, bsite, bday in cal.busy:
            if overlap and bs < end and start < be:
                return False
            if same_day and bday != day:
                continue
            if be <= start and (pv is None or be > pv[1]):
                pv = (bs, be, bsite)
            if bs >= end and (nx is None or bs < nx[0]):
                nx = (bs, be, bsite)
        ws2, _we2 = cal.work_window(di)
        if travel:
            if pv is None:
                if home and start - ws2 < S.travel_needed(sites, cal.home, site):
                    return False
            elif start - pv[1] < S.travel_needed(sites, pv[2], site):
                return False
            if nx is not None and nx[0] - end < S.travel_needed(sites, site, nx[2]):
                return False
        return True
    return f


def run(data_dir, order="policy", candidates=None, **kw):
    P = json.load(open(data_dir + "/people.json"))
    St = json.load(open(data_dir + "/sites.json"))
    R = json.load(open(data_dir + "/requests.json"))["requests"]
    S.can_attend = _checker(**kw) if kw else _ORIG

    keys = {"policy": lambda r: (r["priority"], -len(r["required"]), r["id"]),
            "priority_only": lambda r: (r["priority"],),
            "catalogue": lambda r: 0}
    days, slot, cfg = P["days"], P["slot_minutes"], P
    cals = {p["id"]: S.Calendar(p, days) for p in P["people"]}
    seq = sorted(R, key=keys[order])
    ncand = S.CANDIDATES if candidates is None else candidates

    prune = kw.get("hours", True)

    def slots(state, req, limit=None):
        if prune:
            return S.feasible_slots(state, req, days, slot, cfg, St, limit=limit)
        # A solver that ignores working hours would not prune to them either.
        out = []
        dur, site, prio = req["duration_min"], req["site"], req["priority"]
        for d in range(days.index(req["earliest_day"]),
                       days.index(req["latest_day"]) + 1):
            day = days[d]
            for start in range(d * 1440, (d + 1) * 1440 - dur + 1, slot):
                if all(S.can_attend(state[p], d, day, start, dur, site, prio,
                                    cfg, St) for p in req["required"]):
                    out.append((d, day, start))
                    if limit and len(out) >= limit:
                        return out
        return out

    def fill(state, queue):
        n = 0
        for r in queue:
            hit = slots(state, r, limit=1)
            if not hit:
                continue
            d, day, start = hit[0]
            S.commit(state, r, day, start,
                     S.attendees_at(state, r, d, day, start, cfg, St))
            n += 1
        return n

    placed = {}
    for idx, req in enumerate(seq):
        cands = slots(cals, req, limit=ncand)
        if not cands:
            placed[req["id"]] = {"status": "declined", "day": "",
                                 "start_utc": "", "attendees": []}
            continue
        best = None
        for d, day, start in cands:
            trial = {k: v.clone() for k, v in cals.items()}
            S.commit(trial, req, day, start,
                     S.attendees_at(trial, req, d, day, start, cfg, St))
            kept = fill(trial, seq[idx + 1:idx + 1 + S.LOOKAHEAD])
            if best is None or kept > best[0]:
                best = (kept, d, day, start)
        _, d, day, start = best
        going = S.attendees_at(cals, req, d, day, start, cfg, St)
        S.commit(cals, req, day, start, going)
        placed[req["id"]] = {"status": "scheduled", "day": day,
                             "start_utc": S.fmt_utc(days, start),
                             "attendees": going}
    S.can_attend = _ORIG
    return [dict(id=r["id"], **placed[r["id"]]) for r in R]


MUTATIONS = [
    ("lunch exemption on P2 not P1", dict(lunch_exempt=2)),
    ("daily cap uses >= not >",      dict(cap_strict=False)),
    ("travel buffers dropped",       dict(travel=False)),
    ("working hours ignored",        dict(hours=False)),
    ("daily cap ignored",            dict(cap=False)),
    ("protected lunch ignored",      dict(lunch=False)),
    ("PTO ignored",                  dict(pto=False)),
    ("home-site travel ignored",     dict(home=False)),
    ("neighbours across whole week",  dict(same_day=False)),
    ("greedy: earliest slot always", dict(_greedy=True)),
]
ORDER_MUTATIONS = [
    ("ordered by priority only", "priority_only"),
    ("ordered by catalogue",     "catalogue"),
]


def report(data_dir):
    base = run(data_dir)
    rows = []
    for name, kw in MUTATIONS:
        if kw.pop("_greedy", False):
            got = run(data_dir, candidates=1)
        else:
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
