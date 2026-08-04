"""Prove the corrupted audit still pins exactly one setting.

With a clean audit the test was "which settings reproduce every entry". With
errors in the audit the question changes to "which setting explains the MOST
entries", and the task is well posed only if that maximum is achieved by one
setting and by a clear margin. If a wrong setting explains as many entries as
the truth -- by bending a constant to accommodate a corrupted row -- the answer
is not defined and this cannot ship.

Staged and pruned so an exhaustive sweep stays tractable: the three constants
that only decide a reported event's ward and line flag cannot improve agreement
beyond what the dates and organisms already allow, so any (pool, walk) setting
whose skeleton agreement is already below the incumbent is skipped whole.
"""
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve                                     # noqa: E402
from solve import Params                         # noqa: E402

# the setting dev7/gen2.py generated from, in the shipped solver's field order
TRUE = Params(iwp_before=3, iwp_after=3, commensal_gap=1, doe_rule="earliest",
              hai_day=3, order="UTI", rit_days=14, sec_start="iwp", sec_len=17,
              line_min_days=3, line_grace=1, transfer_window=1)

HERE = os.path.dirname(os.path.abspath(__file__))

GRID = {
    "iwp_before": range(1, 6), "iwp_after": range(1, 6),
    "commensal_gap": range(0, 3), "doe_rule": ["earliest", "culture"],
    "hai_day": range(2, 5), "order": ["UTI", "BSI"], "rit_days": range(10, 19),
    "sec_start": ["iwp", "doe"], "sec_len": range(10, 21),
    "line_min_days": range(2, 5), "line_grace": range(0, 3),
    "transfer_window": range(0, 3),
}
POOL = ("iwp_before", "iwp_after", "commensal_gap", "doe_rule", "hai_day")
WALK = ("order", "rit_days", "sec_start", "sec_len")
TRIM = ("line_min_days", "line_grace", "transfer_window")


skeleton = None          # bound to the shipped solver's helpers below


def main():
    global skeleton
    skeleton = solve.skeleton
    want_skeleton = solve.want_skeleton
    with open(os.path.join(HERE, "audited.json")) as f:
        audit = json.load(f)
    want = {a["id"]: a for a in audit["adjudications"]}
    want_skel = {k: want_skeleton(v) for k, v in want.items()}
    pts = audit["patients"]
    adms = {p["id"]: [solve.Admission(a) for a in p["admissions"]] for p in pts}

    truth_agree = sum(1 for p in pts
                      if solve.report(TRUE, p) == want[p["id"]])
    print("the generating setting explains %d of %d audit entries"
          % (truth_agree, len(pts)))

    t0 = time.time()
    best, winners, seen = truth_agree, [], 0
    for pc in itertools.product(*(list(GRID[f]) for f in POOL)):
        base = dict(zip(POOL, pc))
        stub = Params(order="UTI", rit_days=10, sec_start="iwp", sec_len=10,
                      line_min_days=2, line_grace=0, transfer_window=0, **base)
        pools = {p["id"]: solve.build_pool(stub, adms[p["id"]]) for p in pts}

        for wc in itertools.product(*(list(GRID[f]) for f in WALK)):
            mid = dict(base, **dict(zip(WALK, wc)))
            stub2 = Params(line_min_days=2, line_grace=0, transfer_window=0,
                           **mid)
            walks, ok_skel = {}, []
            for p in pts:
                w = solve.walk(stub2, pools[p["id"]])
                walks[p["id"]] = w
                if skeleton(w) == want_skel[p["id"]]:
                    ok_skel.append(p["id"])
            if len(ok_skel) < best:
                continue                      # cannot reach the incumbent
            for tc in itertools.product(*(list(GRID[f]) for f in TRIM)):
                seen += 1
                p_full = Params(**dict(mid, **dict(zip(TRIM, tc))))
                agree = sum(1 for pid in ok_skel
                            if solve.dress(p_full, pid, walks[pid])
                            == want[pid])
                if agree > best:
                    best, winners = agree, [p_full]
                elif agree == best:
                    winners.append(p_full)

    print("swept the grid in %.0fs (%d settings scored past the prune)"
          % (time.time() - t0, seen))
    print("best agreement %d; settings achieving it: %d" % (best, len(winners)))
    for w in winners:
        print("   ", w)
    if len(winners) != 1 or winners[0] != TRUE:
        print("NOT WELL POSED -- the audit does not single out one setting")
        return 1
    print("exactly one setting explains the most audit entries, and it is the "
          "generating one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
