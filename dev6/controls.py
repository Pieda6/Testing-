"""How far each plausible wrong approach gets, measured on the shipped data.

Grading is all-or-nothing across all thirty jobs, so anything short of 30/30
scores zero. The per-job numbers are what goes in difficulty_explanation.

Two families are reported separately because they behave differently in the
agent's hands. An INFERENCE error contradicts the log, so a solver that checks
its recovered schedule against the log finds out; those rows say "no consistent
schedule". A PROJECTION error is silent -- the recovered schedule is right and
reproduces the log perfectly, and only the future timestamps are wrong.
"""
import datetime as dt
import json
import os

import infer
from infer import parse_iso, day_pred

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = json.load(open(os.path.join(HERE, "jobs.json")))


def reference():
    res = infer.solve(DOC)
    out = {}
    for r in res:
        dom, dw = r["candidates"][0]
        out[r["id"]] = (r["hours"], r["mins"], dom, dw,
                        next(iter(r["projections"])))
    return out


REF = reference()
CLOCK = infer.Clock(DOC["clock"])
P0 = parse_iso(DOC["predict_start_utc"])
P1 = parse_iso(DOC["predict_end_utc"])


def score(label, get):
    ok = sum(1 for jid, (h, m, dom, dw, want) in REF.items()
             if tuple(get(h, m, dom, dw)) == tuple(want))
    print("  %-52s %2d / %d" % (label, ok, len(REF)))


def project_with(offset_of, hours, mins, dom, dw, dedupe=False):
    out, t = [], P0
    step = dt.timedelta(minutes=1)
    while t < P1:
        lt = t + dt.timedelta(minutes=offset_of(t))
        if lt.hour in hours and lt.minute in mins and day_pred(dom, dw, lt):
            out.append(t)
        t += step
    return out


def project_local_naive(hours, mins, dom, dw, offset):
    """Walk local minutes and convert back with a single offset -- this emits an
    instant for a local time the forward transition deleted, and only one for a
    local time the backward transition repeated."""
    out = []
    t = P0 + dt.timedelta(minutes=CLOCK.offset(P0))
    end = P1 + dt.timedelta(minutes=CLOCK.offset(P1 - dt.timedelta(minutes=1)))
    step = dt.timedelta(minutes=1)
    while t < end:
        if t.hour in hours and t.minute in mins and day_pred(dom, dw, t):
            u = t - dt.timedelta(minutes=offset(t))
            if P0 <= u < P1:
                out.append(u)
        t += step
    return sorted(set(out))


def main():
    print("PROJECTION errors (the recovered schedule is right; silent):")
    score("reference",
          lambda h, m, d, w: project_with(CLOCK.offset, h, m, d, w))
    frozen = CLOCK.offset(P0 - dt.timedelta(minutes=1))
    score("clock frozen at the end of the log",
          lambda h, m, d, w: project_with(lambda t: frozen, h, m, d, w))
    score("only the first future transition applied",
          lambda h, m, d, w: project_with(
              lambda t: CLOCK.trans[-2][1] if t >= CLOCK.trans[-2][0] else frozen,
              h, m, d, w))
    score("UTC treated as local (offsets ignored)",
          lambda h, m, d, w: project_with(lambda t: 0, h, m, d, w))
    score("local minutes walked, converted with one offset",
          lambda h, m, d, w: project_local_naive(h, m, d, w, lambda t: frozen))
    score("repeated local time emitted once",
          lambda h, m, d, w: sorted(set(
              project_local_naive(h, m, d, w, CLOCK.offset))))
    score("day-of-month AND day-of-week",
          lambda h, m, d, w: project_with(
              CLOCK.offset, h, m,
              d if len(d) == 31 or len(w) == 7 else d,
              w) if len(d) == 31 or len(w) == 7 else
          [t for t in project_with(CLOCK.offset, h, m, d, w)
           if (CLOCK.local(t).day in d and infer.dow(CLOCK.local(t)) in w)])

    print("INFERENCE errors (they contradict the log, so they are detectable):")
    for label, mut in (("UTC treated as local", lambda self, u: 0),
                       ("base offset, transitions ignored",
                        lambda self, u: self.base)):
        orig = infer.Clock.offset
        infer.Clock.offset = mut
        try:
            infer.solve(DOC)
            print("  %-52s recovered a schedule" % label)
        except Exception as exc:
            print("  %-52s no consistent schedule (%s)"
                  % (label, str(exc).split(":")[1].strip()))
        finally:
            infer.Clock.offset = orig

    doc = {k: v for k, v in DOC.items() if k != "outages"}
    try:
        infer.solve(doc)
        print("  %-52s recovered a schedule" % "outage silence read as evidence")
    except Exception as exc:
        print("  %-52s no consistent schedule (%s)"
              % ("outage silence read as evidence", str(exc).split(":")[1].strip()))


if __name__ == "__main__":
    main()
