"""Validate the inference core against the generator's hidden truth.

Four things have to hold before this task can ship:

1. the clock recovered from the log alone matches the true clock, including
   the two transitions inside the prediction window that the log never shows;
2. the rule fitted to the observed changes is the only one that fits, so the
   extrapolation is not a guess;
3. every schedule consistent with the log projects to the SAME future firings,
   so the answer is well defined even where the schedule is not unique;
4. that projection equals the one computed from the true schedules.
"""
import json
import os
import sys

import infer
from infer import parse_iso, iso

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "jobs.json")) as f:
        doc = json.load(f)
    with open(os.path.join(HERE, "truth.json")) as f:
        t = json.load(f)
    truth = {j["id"]: j["spec"] for j in t["jobs"]}
    true_trans = [(x["utc"], x["offset_min"]) for x in t["transitions"]]

    bad = 0

    # 1 + 2: the clock
    clocks, sets, observed = infer.recover_clock(doc, all_rule_sets=True)
    got = [(iso(u), o) for u, o in clocks[0].trans]
    if got != true_trans:
        print("CLOCK MISMATCH\n  got  %s\n  want %s" % (got, true_trans))
        bad += 1
    future = [x for x in got if x[0] >= doc["predict_start_utc"]]
    if len(sets) != 1:
        projections = set(tuple((iso(u), o) for u, o in c.trans) for c in clocks)
        print("%d rule sets fit; %d distinct clocks" % (len(sets),
                                                        len(projections)))
        if len(projections) != 1:
            bad += 1
    print("clock: %d transitions recovered, %d of them inside the prediction "
          "window and never observed | rule sets fitting the log: %d"
          % (len(got), len(future), len(sets)))

    # 3 + 4: the schedules
    res = infer.solve(doc, all_candidates=True, clock=clocks[0])
    total_cands = 0
    for r in res:
        total_cands += len(r["candidates"])
        if len(r["projections"]) != 1:
            print("%s: AMBIGUOUS -- %d distinct projections from %d specs"
                  % (r["id"], len(r["projections"]), len(r["candidates"])))
            bad += 1
            continue
        spec = truth[r["id"]]
        if sorted(spec[1]) != r["hours"] or sorted(spec[0]) != r["mins"]:
            print("%s: hour/minute recovery wrong" % r["id"])
            bad += 1
        got_f = [iso(x) for x in next(iter(r["projections"]))]
        want = [iso(x) for x in
                truth_projection(doc, spec)]
        if got_f != want:
            print("%s: MISMATCH -- %d predicted, %d true"
                  % (r["id"], len(got_f), len(want)))
            bad += 1

    n_pred = sum(len(next(iter(r["projections"]))) for r in res
                 if len(r["projections"]) == 1)
    print("jobs %d | consistent specs %d | predicted firings %d | bad %d"
          % (len(res), total_cands, n_pred, bad))
    return 1 if bad else 0


def truth_projection(doc, spec):
    import gen
    s = tuple(frozenset(x) for x in spec)
    return gen.fire_times(s, parse_iso(doc["predict_start_utc"]),
                          parse_iso(doc["predict_end_utc"]))


if __name__ == "__main__":
    sys.exit(main())
