"""How far each plausible wrong approach gets, measured on the shipped data.

Grading is all-or-nothing across all twenty-four jobs, so anything short of
24/24 scores zero. The per-job numbers are what goes in difficulty_explanation.

The rows are split by whether the mistake announces itself.

  SILENT      the recovered schedules are right and reproduce every one of the
              21308 logged firings, so a solver that validates against the log
              is told everything is fine. Only the future is wrong. Every one
              of these is a mistake about the clock rule, which is exactly the
              part the log cannot check.

  DETECTABLE  the mistake contradicts the log, so a solver that checks finds
              out and can recover. These are the honest, self-correcting ones.

The "reproduces the log" column is the point of the exercise: it is printed
from an actual re-simulation, not asserted.
"""
import datetime as dt
import json
import os

import infer
from infer import parse_iso, iso, day_pred, nth_weekday

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = json.load(open(os.path.join(HERE, "jobs.json")))
BASE = DOC["clock"]["base_offset_min"]
P0, P1 = parse_iso(DOC["predict_start_utc"]), parse_iso(DOC["predict_end_utc"])
L0, L1 = parse_iso(DOC["log_start_utc"]), parse_iso(DOC["log_end_utc"])
OUTAGES = [(parse_iso(o["start_utc"]), parse_iso(o["end_utc"]))
           for o in DOC["outages"]]

TRUE_CLOCK, TRUE_SETS, _OBS = infer.recover_clock(DOC)
REF = {}
for r in infer.solve(DOC, clock=TRUE_CLOCK):
    REF[r["id"]] = (r["hours"], r["mins"]) + r["candidates"][0] + \
        (next(iter(r["projections"])),)


LOGGED = [(u, o) for u, o in TRUE_CLOCK.trans if u < P0]
OFF_AT_P0 = LOGGED[-1][1]


def clock_from(rules):
    """The six transitions the log shows, kept exactly, plus whatever `rules`
    extrapolates into the prediction window.

    This is the shape every realistic clock error takes: the observed changes
    are read off the log correctly -- they are right there -- and the rule
    fitted to them is what goes wrong. Which is why the log still checks out.
    """
    return infer.Clock(BASE, LOGGED + infer.expand(rules, OFF_AT_P0, P0, P1))


def reproduces_log(clock):
    """Does this clock still explain every logged firing? For a clock that only
    differs after the log ends, the answer is yes -- which is the whole problem.
    """
    idx = infer.build_index(clock, L0, L1, OUTAGES)
    for jid, (hours, mins, dom, dw, _p) in REF.items():
        want = set()
        for (d, h, m), times in idx.items():
            if h in hours and m in mins and day_pred(dom, dw, d):
                want.update(times)
        got = set(parse_iso(s) for s in
                  next(j for j in DOC["jobs"] if j["id"] == jid)["fires"])
        if want != got:
            return False
    return True


def score(label, clock, check_log=True):
    idx = infer.build_index(clock, P0, P1)
    ok = 0
    for jid, (hours, mins, dom, dw, want) in REF.items():
        got = tuple(infer.project(idx, hours, mins, dom, dw))
        ok += got == tuple(want)
    same = reproduces_log(clock) if check_log else None
    print("  %-46s %2d / %d   log reproduced: %s"
          % (label, ok, len(REF), {True: "yes", False: "no", None: "-"}[same]))


TRUE_RULES = TRUE_SETS[0]                       # [(3,6,0,1,-150), (11,6,0,1,-210)]


def variant(fn):
    return [fn(r) for r in TRUE_RULES]


def main():
    print("SILENT -- the clock rule is wrong; the log still checks out:")
    score("reference", TRUE_CLOCK)
    score("4th <weekday> read for the last one",
          clock_from(variant(lambda r: (r[0], r[1], 4, r[3], r[4]))))
    score("4th read for the last one, spring change only",
          clock_from([(3, 6, 4, 1, -150), (11, 6, 0, 1, -210)]))
    score("4th read for the last one, autumn change only",
          clock_from([(3, 6, 0, 1, -150), (11, 6, 4, 1, -210)]))
    score("change placed an hour late",
          clock_from(variant(lambda r: (r[0], r[1], r[2], r[3] + 1, r[4]))))
    score("change placed a week late",
          infer.Clock(BASE, LOGGED + [(u + dt.timedelta(days=7), o)
                                      for u, o in TRUE_CLOCK.trans
                                      if u >= P0]))
    score("clock frozen at the end of the log",
          infer.Clock(BASE, [(u, o) for u, o in TRUE_CLOCK.trans if u < P0]))
    score("only the first future change applied",
          infer.Clock(BASE, [(u, o) for u, o in TRUE_CLOCK.trans
                             if u < P0 or u == min(x for x, _ in
                                                   TRUE_CLOCK.trans
                                                   if x >= P0)]))
    score("offsets swapped (change direction reversed)",
          clock_from([(3, 6, 0, 1, -210), (11, 6, 0, 1, -150)]))

    print("DETECTABLE -- these contradict the log:")
    for label, mut in (
            ("UTC treated as local", lambda self, u: 0),
            ("base offset held, no transitions at all",
             lambda self, u: self.base)):
        orig = infer.Clock.offset
        infer.Clock.offset = mut
        try:
            infer.solve(DOC, clock=infer.Clock(BASE, []))
            print("  %-46s recovered a schedule" % label)
        except Exception as exc:
            print("  %-46s no consistent schedule" % label)
        finally:
            infer.Clock.offset = orig

    doc = {k: v for k, v in DOC.items() if k != "outages"}
    try:
        infer.solve(doc, clock=TRUE_CLOCK)
        print("  %-46s recovered a schedule" % "outage silence read as evidence")
    except Exception:
        print("  %-46s no consistent schedule"
              % "outage silence read as evidence")

    idx = infer.build_index(TRUE_CLOCK, P0, P1)
    ok = 0
    for jid, (hours, mins, dom, dw, want) in REF.items():
        if len(dom) == 31 or len(dw) == 7:
            got = tuple(infer.project(idx, hours, mins, dom, dw))
        else:
            got = tuple(t for t in infer.project(idx, hours, mins, dom, dw)
                        if TRUE_CLOCK.local(t).day in dom
                        and infer.dow(TRUE_CLOCK.local(t)) in dw)
        ok += got == tuple(want)
    print("  %-46s %2d / %d   log reproduced: no"
          % ("day-of-month AND day-of-week", ok, len(REF)))

    # walking LOCAL minutes and converting back with the offset in force emits
    # one instant where a backward change repeats a local time, and invents one
    # for a local time a forward change deleted
    ok = 0
    for jid, (hours, mins, dom, dw, want) in REF.items():
        got, seen = [], set()
        for t in infer.project(idx, hours, mins, dom, dw):
            lt = TRUE_CLOCK.local(t)
            if lt in seen:
                continue
            seen.add(lt)
            got.append(t)
        ok += tuple(got) == tuple(want)
    print("  %-46s %2d / %d   log reproduced: yes"
          % ("repeated local time emitted once", ok, len(REF)))


if __name__ == "__main__":
    main()
