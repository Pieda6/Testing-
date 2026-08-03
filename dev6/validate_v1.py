"""Validate the inference core against the generator's hidden truth.

Three things have to hold before this task can ship:

1. inference recovers a schedule that reproduces the log exactly;
2. every schedule consistent with the log projects to the SAME future
   firings -- otherwise the answer is not well defined;
3. that projection equals the one computed from the true schedule.
"""
import json
import os
import sys

import infer
from infer import parse_iso, iso

HERE = os.path.dirname(os.path.abspath(__file__))


def truth_projection(doc, spec):
    import gen
    start = parse_iso(doc["predict_start_utc"])
    end = parse_iso(doc["predict_end_utc"])
    s = tuple(frozenset(x) for x in spec)
    return [iso(t) for t in gen.fire_times(s, start, end)]


def main():
    with open(os.path.join(HERE, "jobs.json")) as f:
        doc = json.load(f)
    with open(os.path.join(HERE, "truth.json")) as f:
        truth = {j["id"]: j["spec"] for j in json.load(f)["jobs"]}

    res = infer.solve(doc, all_candidates=True)
    bad = 0
    total_cands = 0
    for r in res:
        total_cands += len(r["candidates"])
        if len(r["projections"]) != 1:
            print("%s: AMBIGUOUS -- %d distinct projections from %d specs"
                  % (r["id"], len(r["projections"]), len(r["candidates"])))
            bad += 1
            continue
        got = [iso(t) for t in next(iter(r["projections"]))]
        # truth spec is (minutes, hours, dom, months, dow)
        spec = truth[r["id"]]
        want = truth_projection(doc, spec)
        if got != want:
            print("%s: MISMATCH -- %d predicted, %d true"
                  % (r["id"], len(got), len(want)))
            bad += 1
        # hours/minutes must match the truth too
        if sorted(spec[1]) != r["hours"] or sorted(spec[0]) != r["mins"]:
            print("%s: hour/minute recovery wrong" % r["id"])
            bad += 1

    n_pred = sum(len(next(iter(r["projections"]))) for r in res
                 if len(r["projections"]) == 1)
    print("jobs %d | consistent specs %d | predicted firings %d | bad %d"
          % (len(res), total_cands, n_pred, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
