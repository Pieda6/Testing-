"""Prove the audit set pins exactly one setting of the withheld constants.

This is the whole basis for the task being well posed. If two settings both
reproduce every validated adjudication and they disagree on the held-out
quarter, the answer is not defined and the task cannot ship.

The grid is deliberately wider than the truth in every direction -- every value
a competent solver might reasonably entertain -- and it is exhausted, not
sampled. Patients are evaluated in a hand-chosen order so that the cheapest
discriminators come first; almost every setting dies on the first two, which is
what keeps an exhaustive search over millions of combinations tractable.
"""
import itertools
import json
import os
import sys
import time

import params
from params import Params

HERE = os.path.dirname(os.path.abspath(__file__))

GRID = {
    "iwp_before": range(1, 6),
    "iwp_after": range(1, 6),
    "rit_days": range(10, 19),
    "hai_day": range(2, 5),
    "order": ["UTI", "BSI"],
    "sec_start": ["iwp", "doe"],
    "sec_len": range(10, 21),
    "line_min_days": range(2, 5),
    "line_grace": range(0, 3),
    "transfer_window": range(0, 3),
    "commensal_gap": range(0, 3),
    "doe_rule": ["earliest", "culture"],
}
FIELDS = list(Params._fields)


def grid_size():
    n = 1
    for f in FIELDS:
        n *= len(list(GRID[f]))
    return n


def main():
    with open(os.path.join(HERE, "audited.json")) as f:
        audit = json.load(f)
    want = {a["id"]: a for a in audit["adjudications"]}
    patients = list(audit["patients"])

    # cheapest discriminators first: the ones whose expected answer differs
    # under the most settings sit at the front, so the search dies early
    order = sorted(patients,
                   key=lambda p: -(len(want[p["id"]]["uti"]) +
                                   len(want[p["id"]]["bsi"])))

    total = grid_size()
    print("grid %d settings over %d parameters" % (total, len(FIELDS)))
    t0 = time.time()
    survivors, seen = [], 0
    for combo in itertools.product(*(list(GRID[f]) for f in FIELDS)):
        seen += 1
        p = Params(**dict(zip(FIELDS, combo)))
        ok = True
        for patient in order:
            if params.report(p, patient) != want[patient["id"]]:
                ok = False
                break
        if ok:
            survivors.append(p)
    dt_ = time.time() - t0

    print("checked %d settings in %.0fs | survivors %d"
          % (seen, dt_, len(survivors)))
    for s in survivors:
        print("  ", s)
    if len(survivors) != 1:
        return 1
    if survivors[0] != params.TRUE:
        print("survivor is not the generating setting")
        return 1
    print("the audit set pins exactly one setting, and it is the true one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
