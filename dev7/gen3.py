"""Entangled audit generator.

The previous audit was built as contrastive twins: two charts identical but for
one element, so each constant could be read straight off one pair. That makes
the audit pin the constants uniquely -- which is necessary -- but it also makes
the recovery separable, which is fatal, because a solver can deduce twelve
constants one at a time and never search jointly at all.

Uniqueness and separability are different properties. What is wanted is a
system with exactly one solution that is not triangular: every chart's outcome
depends on several constants at once, so no comparison of two charts isolates
any single one, and the only way through is to search the space.

So the charts here are generated with every offset varying independently -- the
admit date, the culture date, how far each sign sits from its culture and on
which side, the line's insert and removal, the ward arrival. Nothing is a twin
of anything. Uniqueness is then not designed in, it is searched for: charts are
added until an exhaustive sweep says one setting explains strictly more of the
audit than any other, and the sweep is the arbiter.
"""
import datetime as dt
import hashlib
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve                                       # noqa: E402
from solve import Params                           # noqa: E402

import gen2                                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = b"dynamo/hai-surveillance/v3"

TRUE = Params(iwp_before=3, iwp_after=3, commensal_gap=1, doe_rule="earliest",
              hai_day=3, order="UTI", rit_days=14, sec_start="iwp", sec_len=17,
              line_min_days=3, line_grace=1, transfer_window=1)

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

PATHOGENS = gen2.PATHOGENS
COMMENSALS = gen2.COMMENSALS
WARDS = gen2.WARDS
BSI_SIGNS = ["chills", "fever", "hypotension"]
UTI_SIGNS = ["costovertebral_tenderness", "dysuria", "fever",
             "suprapubic_tenderness", "urgency"]


def det(tag, n):
    b = hashlib.sha256(SEED + tag.encode()).digest()
    return int.from_bytes(b[:8], "big") % n


# Offsets are drawn from pools that STRADDLE the boundaries -- a sign exactly at
# the window edge and one a day past it, a line in place two days and one three,
# an event on the admission-day cut and one either side. Random offsets probe
# nothing: away from a boundary many settings agree, which is why a purely
# random audit pins nothing at all. But each chart also carries two or three
# signs at different offsets, so which one qualified depends on the window width,
# what the event is dated depends on that, and whether it is reportable depends
# on the admission-day cut applied to that date. One chart, several constants,
# nothing to read off.
SIGN_OFFSETS = (-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5)
FIRST_EVENT = (1, 2, 3, 4, 5, 7, 9)
LINE_LEN = (1, 2, 3, 4, 6, 9, 13)
AFTER_REMOVAL = (0, 1, 2, 3)


def chart(i):
    """One entangled chart. Every offset moves independently of every other."""
    t = "c%d" % i
    admit = dt.date(2026, 1, 1) + dt.timedelta(days=det(t + "ad", 24))
    stay = 14 + det(t + "st", 26)
    a = gen2.Adm(admit.isoformat(),
                 (admit + dt.timedelta(days=stay)).isoformat())

    a.w(WARDS[det(t + "w0", len(WARDS))], admit.isoformat())
    if det(t + "w?", 3) != 0:                       # a second ward, or not
        mv = admit + dt.timedelta(days=1 + det(t + "wm", min(stay - 1, 12)))
        a.w(WARDS[det(t + "w1", len(WARDS))], mv.isoformat())
    if det(t + "l?", 3) != 0:                       # a line, or not
        ins = admit + dt.timedelta(days=det(t + "li", 6))
        rem = min(ins + dt.timedelta(days=LINE_LEN[det(t + "lr",
                                                      len(LINE_LEN))]),
                  a.discharge)
        a.line(ins.isoformat(), rem.isoformat())

    for j in range(1 + det(t + "n", 3)):
        u = t + "k%d" % j
        if det(u + "near", 2):
            when = admit + dt.timedelta(days=FIRST_EVENT[det(u + "fe",
                                                            len(FIRST_EVENT))])
        else:
            when = admit + dt.timedelta(days=1 + det(u + "d", max(2, stay - 2)))
        if when > a.discharge:
            continue
        if det(u + "s", 3) == 0:                     # a commensal pair
            org = COMMENSALS[det(u + "o", len(COMMENSALS))]
            gap = det(u + "g", 3)
            second = when + dt.timedelta(days=gap)
            if second <= a.discharge:
                a.blood(when.isoformat(), org)
                a.blood(second.isoformat(), org)
                for k in range(2 + det(u + "ns", 2)):
                    off = SIGN_OFFSETS[det(u + "so%d" % k, len(SIGN_OFFSETS))]
                    sd = when + dt.timedelta(days=off)
                    if admit <= sd <= a.discharge:
                        pool = BSI_SIGNS if det(u + "sp%d" % k, 4) else UTI_SIGNS
                        a.sign(sd.isoformat(),
                               pool[det(u + "se%d" % k, len(pool))])
            continue
        org = PATHOGENS[det(u + "o", len(PATHOGENS))]
        if det(u + "b", 3) == 0:                     # urine: needs a sign
            a.urine(when.isoformat(), org)
        else:
            a.blood(when.isoformat(), org)
            if det(u + "x", 4) == 0:                 # sometimes a commensal too
                a.blood(when.isoformat(), org,
                        COMMENSALS[det(u + "c", len(COMMENSALS))])
        for k in range(2 + det(u + "ns", 2)):
            off = SIGN_OFFSETS[det(u + "so%d" % k, len(SIGN_OFFSETS))]
            sd = when + dt.timedelta(days=off)
            if admit <= sd <= a.discharge:
                pool = UTI_SIGNS if det(u + "sp%d" % k, 3) else BSI_SIGNS
                a.sign(sd.isoformat(), pool[det(u + "se%d" % k, len(pool))])
    return [a]


def audit(n):
    return [{"id": "AUD-%03d" % (i + 1), "admissions": [x.dump() for x in chart(i)]}
            for i in range(n)]


def sweep(pts, want, floor):
    """Every setting explaining at least `floor` entries, and the best score."""
    want_skel = {k: solve.want_skeleton(v) for k, v in want.items()}
    adms = {p["id"]: [solve.Admission(x) for x in p["admissions"]] for p in pts}
    best, winners = -1, []
    for pc in itertools.product(*(list(GRID[f]) for f in POOL)):
        base = dict(zip(POOL, pc))
        stub = Params(order="UTI", rit_days=10, sec_start="iwp", sec_len=10,
                      line_min_days=2, line_grace=0, transfer_window=0, **base)
        pools = {p["id"]: solve.build_pool(stub, adms[p["id"]]) for p in pts}
        for wc in itertools.product(*(list(GRID[f]) for f in WALK)):
            mid = dict(base, **dict(zip(WALK, wc)))
            s2 = Params(line_min_days=2, line_grace=0, transfer_window=0, **mid)
            walks, fits = {}, []
            for p in pts:
                w = solve.walk(s2, pools[p["id"]])
                walks[p["id"]] = w
                if solve.skeleton(w) == want_skel[p["id"]]:
                    fits.append(p["id"])
            if len(fits) < max(best, floor):
                continue
            for tc in itertools.product(*(list(GRID[f]) for f in TRIM)):
                p_full = Params(**dict(mid, **dict(zip(TRIM, tc))))
                agree = sum(1 for pid in fits
                            if solve.dress(p_full, pid, walks[pid]) == want[pid])
                if agree > best:
                    best, winners = agree, [p_full]
                elif agree == best:
                    winners.append(p_full)
    return best, winners


def main():
    for n in (30, 40, 50, 60):
        pts = audit(n)
        want = {p["id"]: solve.report(TRUE, p) for p in pts}
        best, winners = sweep(pts, want, n)
        uniq = len(winners) == 1 and winners[0] == TRUE
        print("%d charts -> best %d, %d setting(s) tie%s"
              % (n, best, len(winners), "  UNIQUE" if uniq else ""))
        if uniq:
            with open(os.path.join(HERE, "audit_n.txt"), "w") as f:
                f.write(str(n))
            return 0
    print("no chart count in the range gave a unique fit")
    return 1


if __name__ == "__main__":
    sys.exit(main())
