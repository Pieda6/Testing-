"""Conjunctive audit generator.

The audit this replaces was built as contrastive twins: two charts identical but
for one element, so each constant could be read straight off one pair. That
pins the constants uniquely -- which is necessary -- but it also makes the
recovery separable, and separable is fatal: twelve constants deduced one at a
time is twelve easy problems, not one hard one.

The opposite extreme does not work either. Charts with every offset randomised
(dev7/gen3.py) pin nothing at all: away from a boundary most settings agree, so
a random chart carries no information and hundreds of settings tie.

What is wanted is both properties at once, and they are not in conflict once
stated properly:

  * informative  -- every chart sits ON a boundary, so some perturbation of the
    constants changes its adjudication;
  * conjunctive  -- every chart sits on SEVERAL boundaries at once, so at least
    three different constants change it, and its outcome is one bit about the
    combination rather than about any one value.

So each chart here stacks boundaries. A urinary culture whose date of event is
dragged backwards by a sign exactly at the edge of the window, landing exactly
on the admission-day cut, with a ward transfer exactly at the edge of the
transfer window measured from that date of event, and a repeat culture exactly
at the edge of the timeframe measured from it too. Widen the window and the date
of event moves, which moves the admission-day test, the transfer test and the
timeframe test with it. A mismatch says one of six constants is wrong and does
not say which.

`touch()` below is the check: for every chart, how many constants have some
value that changes its adjudication. Charts touched by fewer than three are
rejected -- except the deliberate fillers, which are touched by none and are
therefore the only ones safe to corrupt.
"""
import datetime as dt
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve                                       # noqa: E402
from solve import Params                           # noqa: E402

import gen2                                        # noqa: E402
from gen2 import Adm, WARDS, PATHOGENS, COMMENSALS, iso, d   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

TRUE = Params(iwp_before=3, iwp_after=3, commensal_gap=1, doe_rule="earliest",
              hai_day=3, order="UTI", rit_days=14, sec_start="iwp", sec_len=17,
              line_min_days=3, line_grace=1, transfer_window=1)

GRID = dict(solve.GRID)
POOL, WALK, TRIM = solve.POOL_FIELDS, solve.WALK_FIELDS, solve.TRIM_FIELDS

UTI_SIGN = ["dysuria", "urgency", "suprapubic_tenderness",
            "costovertebral_tenderness"]
BSI_SIGN = ["chills", "hypotension"]


def day(base, n):
    return base + dt.timedelta(days=n)


def as_patient(pid, adms):
    return {"id": pid, "admissions": [a.dump() for a in adms]}


def doe_of(adm, kind, fallback):
    """Date of event the true constants give the first candidate of a kind.

    Some charts are placed so that under the true constants there is no
    candidate at all -- a sign a day outside the window, a commensal pair drawn
    a day too far apart. Reporting nothing is exactly what makes those charts
    informative, so the rest of the chart hangs off `fallback` instead."""
    cands = [c for c in solve.candidates(TRUE, solve.Admission(adm.dump()))
             if c[0] == kind]
    return min(c[2] for c in cands) if cands else fallback


# --- the three chart shapes -------------------------------------------------

def tpl_uti(admit, m, back, fwd, tw_off, rep_off, o1, o2, w1, w2,
            tw_from="doe"):
    """A urinary event whose date is dragged back by its sign, sitting on the
    admission cut, inside a transfer window, with a repeat at the timeframe
    edge. Touches the two window widths, the dating rule, the admission cut,
    the transfer window and the timeframe -- six constants, one outcome."""
    A = d(admit)
    c = day(A, m)
    a = Adm(iso(A), iso(day(A, m + max(rep_off, 0) + 8)))
    a.w(w1, iso(A))
    a.urine(iso(c), o1)
    if back is not None:
        a.sign(iso(day(c, -back)), UTI_SIGN[back % len(UTI_SIGN)])
    if fwd is not None:
        a.sign(iso(day(c, fwd)), UTI_SIGN[(fwd + 1) % len(UTI_SIGN)])
    doe = doe_of(a, "UTI", c)
    second = day(doe, rep_off) if rep_off is not None else None
    if second is not None:
        a.urine(iso(second), o2)
        a.sign(iso(second), "dysuria")
    if tw_off is not None:
        arrive = day(second if tw_from == "repeat" else doe, -tw_off)
        assert arrive > A, "the transfer has to land inside the stay"
        a.w(w2, iso(arrive))
    return [a]


def tpl_sec(admit, m, blood_off, line_ins, line_rem, tw_off, rep_off,
            o1, o2, w1, w2):
    """A urinary event and a bloodstream culture of the same organism placed at
    an edge of the attribution period, over a line whose insert and removal both
    sit on their own edges, inside a transfer window, with a repeat at the
    timeframe edge. Touches the adjudication order, where the period opens and
    how long it runs, both line constants, the transfer window, the timeframe
    and the window reaching back."""
    A = d(admit)
    c = day(A, m)
    a = Adm(iso(A), iso(day(A, m + max(blood_off, rep_off, 0) + 8)))
    a.w(w1, iso(A))
    a.urine(iso(c), o1)
    a.sign(iso(c), "dysuria")
    b = day(c, blood_off)
    a.blood(iso(b), o1)
    if line_ins is not None:
        ins, rem = day(b, -line_ins), day(b, -line_rem)
        assert A <= ins <= rem, "the line has to lie inside the stay"
        a.line(iso(ins), iso(rem))
    if tw_off is not None:
        arrive = day(c, -tw_off)
        assert arrive > A, "the transfer has to land inside the stay"
        a.w(w2, iso(arrive))
    if rep_off is not None:
        second = day(c, rep_off)
        a.urine(iso(second), o2)
        a.sign(iso(second), "urgency")
    return [a]


def tpl_com(admit, m, gap, back, fwd, tw_off, line_ins, line_rem, tail_off,
            org, o_tail, w1, w2, hang="doe"):
    """A commensal pair at the edge of the drawing gap, with signs at the edges
    of the window either side, on the admission cut, over a boundary line, in a
    transfer window, trailed by a pathogen blood culture at the edge of the
    timeframe. Touches the gap, both window widths, the dating rule, the
    admission cut, both line constants, the transfer window and the timeframe.

    The trailing culture is what keeps the charts where the pair does NOT
    qualify informative about anything else: they report that one event instead,
    and where it lands depends on the same constants."""
    A = d(admit)
    anchor = day(A, m)
    a = Adm(iso(A), iso(day(A, m + 16)))
    a.w(w1, iso(A))
    a.blood(iso(anchor), org)
    a.blood(iso(day(anchor, gap)), org)
    if back is not None:
        a.sign(iso(day(anchor, -back)), BSI_SIGN[back % len(BSI_SIGN)])
    if fwd is not None:
        a.sign(iso(day(anchor, fwd)), "fever")
    doe = doe_of(a, "BSI", anchor)
    tail = day(doe, tail_off) if tail_off is not None else None
    if tail is not None:
        a.blood(iso(tail), o_tail)
    # On the charts where the pair does not qualify, the line and the transfer
    # hang off the trailing culture instead -- otherwise the only event on the
    # chart sits on no boundary and the chart says one thing about one constant.
    base = tail if hang == "tail" else doe
    if line_ins is not None:
        ins, rem = day(base, -line_ins), day(base, -line_rem)
        assert A <= ins <= rem, "the line has to lie inside the stay"
        a.line(iso(ins), iso(rem))
    if tw_off is not None:
        arrive = day(base, -tw_off)
        assert arrive > A, "the transfer has to land inside the stay"
        a.w(w2, iso(arrive))
    return [a]


def tpl_plain(admit, stay, off, org, source, w1):
    """A chart on no boundary at all: whatever the constants are, it adjudicates
    the same way. Touched by nothing, which is what makes it the only safe place
    to put an auditor's error."""
    A = d(admit)
    a = Adm(iso(A), iso(day(A, stay)))
    a.w(w1, iso(A))
    when = day(A, off)
    if source == "blood":
        a.blood(iso(when), org)
    else:
        a.urine(iso(when), org)
        a.sign(iso(when), "dysuria")
    return [a]


# --- the audit ---------------------------------------------------------------
# Every entry is a stack of boundaries. The comment on each says which
# boundaries, not which constant -- because no chart belongs to one constant.

def charts():
    P = PATHOGENS
    W = WARDS
    out = []

    # window back edge x dating rule x admission cut x transfer x timeframe
    out.append(tpl_uti("2026-01-04", 5, 3, None, 1, 13, P[3], P[4], W[2], W[3]))
    out.append(tpl_uti("2026-01-05", 6, 4, 3, 1, 14, P[4], P[0], W[3], W[2]))
    out.append(tpl_uti("2026-01-06", 6, 3, 4, 2, 14, P[1], P[6], W[0], W[4]))
    out.append(tpl_uti("2026-01-07", 4, 2, None, 1, 13, P[6], P[3], W[4], W[1]))
    out.append(tpl_uti("2026-01-08", 7, 3, 2, 2, 13, P[7], P[5], W[1], W[0]))
    out.append(tpl_uti("2026-01-09", 6, None, 3, 1, 14, P[5], P[1], W[2], W[4]))
    out.append(tpl_uti("2026-01-10", 5, None, 2, 2, 13, P[0], P[7], W[3], W[0]))
    out.append(tpl_uti("2026-01-11", 8, 4, 2, 1, 14, P[2], P[4], W[4], W[3]))
    out.append(tpl_uti("2026-01-12", 4, 2, 3, 1, 13, P[3], P[6], W[0], W[1]))
    out.append(tpl_uti("2026-01-13", 6, 3, 3, 2, 14, P[4], P[2], W[1], W[2]))
    out.append(tpl_uti("2026-01-14", 6, 3, None, 2, 13, P[6], P[0], W[2], W[0]))
    out.append(tpl_uti("2026-01-15", 7, 5, 3, 1, 14, P[1], P[5], W[3], W[4]))
    # the date of event one day BELOW the cut, so nothing is reported for it and
    # the repeat becomes the only event -- what excludes the lower cut
    out.append(tpl_uti("2026-01-24", 4, 3, None, 1, 13, P[2], P[5],
                       W[1], W[3], tw_from="repeat"))

    # order x where the period opens x how long it runs x both line edges
    out.append(tpl_sec("2026-01-03", 6, 13, 2, 1, 1, 13, P[3], P[1], W[2], W[3]))
    out.append(tpl_sec("2026-01-04", 5, 14, 2, 1, 2, 14, P[4], P[6], W[3], W[0]))
    out.append(tpl_sec("2026-01-05", 6, -2, 1, 1, 1, 13, P[0], P[2], W[0], W[1]))
    out.append(tpl_sec("2026-01-06", 7, 15, 2, 0, 2, 14, P[6], P[3], W[4], W[2]))
    out.append(tpl_sec("2026-01-07", 5, 16, 3, 1, 1, 13, P[7], P[4], W[1], W[4]))
    out.append(tpl_sec("2026-01-08", 6, 17, 2, 2, 2, 14, P[5], P[0], W[2], W[3]))
    out.append(tpl_sec("2026-01-09", 4, 12, 1, 0, 1, 13, P[2], P[7], W[3], W[1]))
    out.append(tpl_sec("2026-01-10", 5, 13, 3, 2, 2, 14, P[1], P[5], W[0], W[4]))
    out.append(tpl_sec("2026-01-11", 6, 18, 2, 1, 1, 13, P[3], P[6], W[4], W[0]))
    out.append(tpl_sec("2026-01-12", 5, 11, 2, 1, 2, 14, P[7], P[1], W[1], W[2]))

    # the drawing gap x both window widths x dating x cut x line x transfer x
    # timeframe
    C = COMMENSALS
    out.append(tpl_com("2026-01-03", 5, 1, 3, None, 1, 2, 1, 13,
                       C[4], P[0], W[4], W[2]))
    out.append(tpl_com("2026-01-04", 6, 1, None, 3, 2, 2, 1, 14,
                       C[1], P[3], W[0], W[3]))
    out.append(tpl_com("2026-01-05", 5, 2, 3, 3, 1, 3, 1, 13,
                       C[3], P[6], W[1], W[0], hang="tail"))
    out.append(tpl_com("2026-01-06", 7, 1, 4, 3, 2, 2, 0, 14,
                       C[0], P[4], W[2], W[4]))
    out.append(tpl_com("2026-01-07", 6, 1, None, 4, 1, 1, 1, 13,
                       C[2], P[7], W[3], W[1], hang="tail"))
    out.append(tpl_com("2026-01-08", 5, 0, 3, 2, 1, 2, 2, 14,
                       C[4], P[5], W[4], W[0]))
    out.append(tpl_com("2026-01-09", 6, 2, 2, 3, 2, 2, 1, 13,
                       C[1], P[2], W[0], W[2], hang="tail"))
    out.append(tpl_com("2026-01-10", 5, 1, 3, 4, 1, 1, 0, 14,
                       C[3], P[1], W[1], W[4]))

    # charts on no boundary: the only ones the auditor's errors may fall on
    out.append(tpl_plain("2026-01-16", 20, 8, P[6], "blood", W[0]))
    out.append(tpl_plain("2026-01-17", 20, 9, P[0], "blood", W[1]))
    out.append(tpl_plain("2026-01-18", 20, 8, P[3], "urine", W[2]))
    out.append(tpl_plain("2026-01-19", 20, 9, P[2], "blood", W[3]))
    out.append(tpl_plain("2026-01-20", 20, 8, P[4], "blood", W[4]))
    out.append(tpl_plain("2026-01-21", 20, 9, P[3], "urine", W[0]))
    out.append(tpl_plain("2026-01-22", 20, 8, P[5], "blood", W[1]))
    out.append(tpl_plain("2026-01-23", 20, 9, P[7], "blood", W[2]))
    return out


def audit_patients():
    return [as_patient("AUD-%03d" % (i + 1), adms)
            for i, adms in enumerate(charts())]


# --- the check that the audit is conjunctive ---------------------------------

def touch(pts):
    """For each chart, the constants that can change its adjudication."""
    base = {p["id"]: solve.report(TRUE, p) for p in pts}
    hit = dict((p["id"], set()) for p in pts)
    for field, values in GRID.items():
        for v in values:
            if v == getattr(TRUE, field):
                continue
            alt = TRUE._replace(**{field: v})
            for p in pts:
                if solve.report(alt, p) != base[p["id"]]:
                    hit[p["id"]].add(field)
    return hit


# --- the check that the audit pins one setting ------------------------------

def sweep(pts, want, floor):
    want_skel = {k: solve.want_skeleton(v) for k, v in want.items()}
    adms = {p["id"]: [solve.Admission(x) for x in p["admissions"]]
            for p in pts}
    best, winners, scored = floor, [], 0
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
            if len(fits) < best:
                continue
            for tc in itertools.product(*(list(GRID[f]) for f in TRIM)):
                scored += 1
                full = Params(**dict(mid, **dict(zip(TRIM, tc))))
                agree = sum(1 for pid in fits
                            if solve.dress(full, pid, walks[pid]) == want[pid])
                if agree > best:
                    best, winners = agree, [full]
                elif agree == best:
                    winners.append(full)
    return best, winners, scored


def main():
    pts = audit_patients()
    n = len(pts)
    hit = touch(pts)

    plain = [p["id"] for p in pts if not hit[p["id"]]]
    thin = sorted(pid for pid, h in hit.items() if 0 < len(h) < 3)
    widths = sorted(len(h) for h in hit.values() if h)
    print("%d charts: %d conjunctive (touched by %d..%d constants, mean %.1f), "
          "%d on no boundary" % (n, len(widths), min(widths), max(widths),
                                 sum(widths) / float(len(widths)), len(plain)))
    if thin:
        print("REJECTED -- these charts are touched by fewer than three "
              "constants, so a single comparison isolates one: %s"
              % ", ".join(thin))
        return 1

    cover = collections_counter(hit)
    missing = [f for f in GRID if cover.get(f, 0) == 0]
    if missing:
        print("no chart is sensitive to: %s" % ", ".join(missing))
        return 1
    print("each constant is exercised by %d..%d charts"
          % (min(cover.values()), max(cover.values())))

    print("safe to corrupt (touched by nothing): %s" % ", ".join(plain))

    clean = {p["id"]: solve.report(TRUE, p) for p in pts}
    want = dict(clean)
    for pid, entry in zip(plain, gen4_corruptions(plain, clean)):
        want[pid] = entry

    t0 = time.time()
    best, winners, scored = sweep(pts, want, n - 5)
    print("swept in %.0fs (%d settings scored past the prune)"
          % (time.time() - t0, scored))
    print("best agreement %d of %d; settings achieving it: %d"
          % (best, n, len(winners)))
    for w in winners[:6]:
        print("   ", w)
    if len(winners) != 1 or winners[0] != TRUE:
        print("NOT WELL POSED")
        return 1
    print("exactly one setting explains the most audit entries, and it is the "
          "generating one")

    doc = {
        "period_start": iso(gen2.PERIOD_START),
        "period_end": iso(gen2.PERIOD_END),
        "wards": WARDS,
        "patients": pts,
        "adjudications": [want[p["id"]] for p in pts],
    }
    out = os.path.join(HERE, "..", "task7", "environment", "data",
                       "audited.json")
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    wrong = sum(1 for p in pts if want[p["id"]] != clean[p["id"]])
    print("wrote %s: %d patients, %d entries, %d of them wrong"
          % (os.path.relpath(out, os.path.dirname(HERE)), len(pts),
             sum(len(want[p["id"]]["uti"]) + len(want[p["id"]]["bsi"])
                 for p in pts), wrong))
    return 0


def collections_counter(hit):
    out = {}
    for h in hit.values():
        for f in h:
            out[f] = out.get(f, 0) + 1
    return out


CORRUPT = {
    0: ("flag", "bsi", True),          # a line association where no line existed
    2: ("ward", "uti", "MICU"),        # a ward the patient never occupied
    4: ("organism", "bsi", "Proteus mirabilis"),   # an organism never cultured
    6: ("shift", "bsi", 5),            # a date no window can reach
}


def gen4_corruptions(plain, clean):
    """Four of the eight boundary-free charts, wrong in ways no setting of the
    constants predicts -- so the error is noise the recovery has to survive and
    not evidence for some other setting."""
    out = []
    for i, pid in enumerate(plain):
        entry = json.loads(json.dumps(clean[pid]))
        rule = CORRUPT.get(i)
        if rule is not None:
            kind, key, val = rule
            assert entry[key], "%s reports no %s to corrupt" % (pid, key)
            if kind == "flag":
                entry[key][0]["central_line_associated"] = val
            elif kind == "ward":
                entry[key][0]["ward"] = val
            elif kind == "organism":
                entry[key][0]["organisms"] = sorted(
                    entry[key][0]["organisms"] + [val])
            elif kind == "shift":
                entry[key][0]["date_of_event"] = iso(
                    day(d(entry[key][0]["date_of_event"]), val))
        out.append(entry)
    return out


if __name__ == "__main__":
    sys.exit(main())
