"""The shipped data: audit, held-out quarter, answer key.

Two things changed here and the second is the important one.

1. The audit is conjunctive (this came in with dev7/gen4.py). It is not built
   as contrastive twins -- two patients identical but for one element, so a
   constant can be read straight off one pair -- and it is not randomised
   either, because charts placed away from a boundary pin nothing at all
   (dev7/gen3.py: 168 to 792 settings tied). Every chart sits on SEVERAL
   boundaries at once, so a mismatch says one of five or six constants is wrong
   and does not say which.

2. The constants are no longer the familiar ones. That was the real defect. Ten
   of the twelve now differ from what the well-known surveillance definitions
   use -- the window is asymmetric rather than three days either side, two
   commensal cultures may be drawn two days apart rather than one, the
   admission-day cut is a day later, the repeat timeframe is shorter, the
   secondary attribution period opens at the date of event rather than at the
   start of the window and runs longer, a line must be in place a day longer,
   two days after removal still count, and the transfer rule reaches two days.
   Every offset in the charts below is expressed as a delta from a constant, so
   the whole design moves with it: change TRUE and the boundaries follow.

The two remaining familiar values are not a choice. Dating by the earliest
element keeps the date of event moving when the window moves, which is what
makes the charts conjunctive at all; and adjudicating urinary infections first
is what makes a bloodstream culture capable of being secondary, without which
the two attribution constants are unrecoverable and the task is not well posed.

Three checks gate the output and all three have rejected a design:

    uniqueness       exactly one setting explains the most audit entries
    conjunctivity    every boundary-bearing chart is changed by >= 3 constants
    held-out reach   every single-constant error changes >= 1 held-out patient
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
DATA = os.path.join(HERE, "..", "task7", "environment", "data")
TESTS = os.path.join(HERE, "..", "task7", "tests")

TRUE = Params(iwp_before=4, iwp_after=2, commensal_gap=2, doe_rule="earliest",
              hai_day=4, order="UTI", rit_days=11, sec_start="doe", sec_len=20,
              line_min_days=4, line_grace=2, transfer_window=2)

GRID = dict(solve.GRID)
POOL, WALK, TRIM = solve.POOL_FIELDS, solve.WALK_FIELDS, solve.TRIM_FIELDS

B = TRUE.iwp_before          # a sign this far before the culture still counts
F = TRUE.iwp_after           # and this far after
G = TRUE.commensal_gap       # two commensal draws this far apart still pair
H = TRUE.hai_day             # this admission day is the first that counts
R = TRUE.rit_days            # a repeat inside this many days is absorbed
SL = TRUE.sec_len            # the attribution period runs this long
LM = TRUE.line_min_days      # a line must have been in this many days
LG = TRUE.line_grace         # and this many days after removal still count
TW = TRUE.transfer_window    # an event this soon after arrival goes back

UTI_SIGN = ["dysuria", "urgency", "suprapubic_tenderness",
            "costovertebral_tenderness"]
BSI_SIGN = ["chills", "hypotension"]


def day(base, n):
    return base + dt.timedelta(days=n)


def doe_of(adm, kind, fallback):
    """Date of event the true constants give the first candidate of a kind.

    Some charts are placed so that under the true constants there is no
    candidate -- a sign a day outside the window, a commensal pair drawn a day
    too far apart. Reporting nothing is what makes those charts informative, so
    the rest of the chart hangs off `fallback` instead."""
    cands = [c for c in solve.candidates(TRUE, solve.Admission(adm.dump()))
             if c[0] == kind]
    return min(c[2] for c in cands) if cands else fallback


# --- the three chart shapes -------------------------------------------------

def tpl_uti(admit, doe_off, back, fwd, tw_off, rep_off, o1, o2, w1, w2,
            tw_from="doe"):
    """A urinary event dragged to `doe_off` by its sign, sitting on the
    admission cut, inside a transfer window, with a repeat at the edge of the
    timeframe. Touches both window widths, the dating rule, the admission cut,
    the transfer window and the timeframe: six constants, one outcome."""
    A = d(admit)
    m = doe_off + (back if (back is not None and back <= B) else 0)
    c = day(A, m)
    a = Adm(iso(A), iso(day(A, m + max(rep_off or 0, 0) + 8)))
    a.w(w1, iso(A))
    a.urine(iso(c), o1)
    if back is not None:
        a.sign(iso(day(c, -back)), UTI_SIGN[back % len(UTI_SIGN)])
    if fwd is not None:
        a.sign(iso(day(c, fwd)), UTI_SIGN[(fwd + 1) % len(UTI_SIGN)])
    doe = doe_of(a, "UTI", c)
    assert doe == day(A, doe_off), "the chart did not land where it was placed"

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
    """A urinary event and a bloodstream culture of the same organism at an edge
    of the attribution period, over a line whose insertion and removal both sit
    on their own edges, inside a transfer window, with a repeat at the edge of
    the timeframe. Touches the adjudication order, where the period opens and
    how long it runs, both line constants, the transfer window, the timeframe
    and the window reaching back."""
    A = d(admit)
    c = day(A, m)
    a = Adm(iso(A), iso(day(A, m + max(blood_off, rep_off or 0, 0) + 8)))
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
    """A commensal pair at the edge of the drawing gap, signs at both edges of
    the window, on the admission cut, over a boundary line, inside a transfer
    window, trailed by a pathogen culture at the edge of the timeframe.

    The trailing culture is what keeps the charts whose pair does NOT qualify
    informative about anything else: they report that one event instead, and
    where it lands turns on the same constants."""
    A = d(admit)
    anchor = day(A, m)
    a = Adm(iso(A), iso(day(A, m + tail_off + 6)))
    a.w(w1, iso(A))
    a.blood(iso(anchor), org)
    a.blood(iso(day(anchor, gap)), org)
    if back is not None:
        a.sign(iso(day(anchor, -back)), BSI_SIGN[back % len(BSI_SIGN)])
    if fwd is not None:
        a.sign(iso(day(anchor, fwd)), "fever")
    doe = doe_of(a, "BSI", anchor)
    tail = day(doe, tail_off)
    a.blood(iso(tail), o_tail)
    # Where the pair does not qualify the line and the transfer hang off the
    # trailing culture instead; otherwise the only event on the chart sits on no
    # boundary and the chart says one thing about one constant.
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
    """A chart on no boundary at all: it adjudicates the same way whatever the
    constants are, which is what makes it the only safe place for an error."""
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

def audit_charts():
    P, W, C = PATHOGENS, WARDS, COMMENSALS
    out = []

    # the window back edge x dating x the cut x the transfer x the timeframe
    out.append(tpl_uti("2026-01-04", H - 1, B, None, TW, R - 1,
                       P[3], P[4], W[2], W[3]))
    out.append(tpl_uti("2026-01-05", H + 2, B + 1, F, TW, R,
                       P[4], P[0], W[3], W[2]))
    out.append(tpl_uti("2026-01-06", H, B, F + 1, TW + 1, R,
                       P[1], P[6], W[0], W[4]))
    out.append(tpl_uti("2026-01-07", H - 1, B - 2, None, TW, R - 1,
                       P[6], P[3], W[4], W[1]))
    out.append(tpl_uti("2026-01-08", H + 1, B, F - 1, TW + 1, R - 1,
                       P[7], P[5], W[1], W[0]))
    out.append(tpl_uti("2026-01-09", H + 2, None, F, TW, R,
                       P[5], P[1], W[2], W[4]))
    out.append(tpl_uti("2026-01-10", H + 1, None, F, TW + 1, R - 1,
                       P[0], P[7], W[3], W[0]))
    out.append(tpl_uti("2026-01-11", H + 3, B + 1, F - 1, TW, R,
                       P[2], P[4], W[4], W[3]))
    out.append(tpl_uti("2026-01-12", H - 1, B - 2, F, TW, R - 1,
                       P[3], P[6], W[0], W[1]))
    out.append(tpl_uti("2026-01-13", H, B, F, TW + 1, R,
                       P[4], P[2], W[1], W[2]))
    out.append(tpl_uti("2026-01-14", H, B, None, TW + 1, R - 1,
                       P[6], P[0], W[2], W[0]))
    out.append(tpl_uti("2026-01-15", H + 2, B + 2, F, TW, R,
                       P[1], P[5], W[3], W[4]))
    # one day BELOW the cut, so its first culture is not reportable at all and
    # the repeat becomes the only event -- what excludes the lower cut
    out.append(tpl_uti("2026-01-24", H - 2, B, None, TW, R - 1,
                       P[2], P[5], W[1], W[3], tw_from="repeat"))

    # order x where the period opens x how long it runs x both line edges
    out.append(tpl_sec("2026-01-03", H + 2, SL - 1, LM - 1, LG, TW, R - 1,
                       P[3], P[1], W[2], W[3]))
    out.append(tpl_sec("2026-01-04", H + 1, SL, LM - 1, LG, TW + 1, R,
                       P[4], P[6], W[3], W[0]))
    out.append(tpl_sec("2026-01-05", H + 2, -2, LM - 2, LG, TW, R - 1,
                       P[0], P[2], W[0], W[1]))
    out.append(tpl_sec("2026-01-06", H + 3, SL + 1, LM - 1, LG + 1, TW + 1, R,
                       P[6], P[3], W[4], W[2]))
    out.append(tpl_sec("2026-01-07", H + 1, SL - 5, LM - 1, LG, TW, R - 1,
                       P[7], P[4], W[1], W[4]))
    out.append(tpl_sec("2026-01-08", H + 2, SL - 4, LM - 1, LG + 1, TW + 1, R,
                       P[5], P[0], W[2], W[3]))
    out.append(tpl_sec("2026-01-09", H + 3, -3, LM - 2, LG, TW, R - 1,
                       P[2], P[7], W[3], W[1]))
    out.append(tpl_sec("2026-01-10", H + 1, SL - 1, LM - 1, LG + 1, TW + 1, R,
                       P[1], P[5], W[0], W[4]))
    out.append(tpl_sec("2026-01-11", H + 2, SL + 2, LM - 1, LG, TW, R - 1,
                       P[3], P[6], W[4], W[0]))
    out.append(tpl_sec("2026-01-12", H + 1, SL - 6, LM - 2, LG, TW + 1, R,
                       P[7], P[1], W[1], W[2]))

    # the drawing gap x both widths x dating x cut x line x transfer x timeframe
    out.append(tpl_com("2026-01-03", H - 1 + B, G, B, None, TW,
                       LM - 1, LG, R - 1, C[4], P[0], W[4], W[2]))
    out.append(tpl_com("2026-01-04", H + 2, G, None, F, TW + 1,
                       LM - 1, LG, R, C[1], P[3], W[0], W[3]))
    out.append(tpl_com("2026-01-05", H + 1, G + 1, B, F, TW,
                       LM - 1, LG, R - 1, C[3], P[6], W[1], W[0],
                       hang="tail"))
    out.append(tpl_com("2026-01-06", H - 1 + B, G, B + 1, F, TW + 1,
                       LM - 1, LG + 1, R, C[0], P[4], W[2], W[4]))
    out.append(tpl_com("2026-01-07", H + 2, G, None, F + 1, TW,
                       LM - 2, LG, R - 1, C[2], P[7], W[3], W[1],
                       hang="tail"))
    out.append(tpl_com("2026-01-08", H - 1 + B, G - 1, B, F - 1, TW,
                       LM - 1, LG + 1, R, C[4], P[5], W[4], W[0]))
    out.append(tpl_com("2026-01-09", H + 2, G + 1, B - 2, F, TW + 1,
                       LM - 1, LG, R - 1, C[1], P[2], W[0], W[2],
                       hang="tail"))
    out.append(tpl_com("2026-01-10", H + 1 + B, G, B, F + 1, TW,
                       LM - 2, LG, R, C[3], P[1], W[1], W[4]))

    # on no boundary: the only charts the auditor's errors may fall on
    out.append(tpl_plain("2026-01-16", 24, 10, P[6], "blood", W[0]))
    out.append(tpl_plain("2026-01-17", 24, 11, P[0], "blood", W[1]))
    out.append(tpl_plain("2026-01-18", 24, 10, P[3], "urine", W[2]))
    out.append(tpl_plain("2026-01-19", 24, 11, P[2], "blood", W[3]))
    out.append(tpl_plain("2026-01-20", 24, 10, P[4], "blood", W[4]))
    out.append(tpl_plain("2026-01-21", 24, 11, P[3], "urine", W[0]))
    out.append(tpl_plain("2026-01-22", 24, 10, P[5], "blood", W[1]))
    out.append(tpl_plain("2026-01-23", 24, 11, P[7], "blood", W[2]))
    return out


CORRUPT = {
    0: ("flag", "bsi", True),                      # no line was ever in place
    2: ("ward", "uti", "MICU"),                    # a ward never occupied
    4: ("organism", "bsi", "Proteus mirabilis"),   # an organism never cultured
    6: ("shift", "bsi", 5),                        # a date no window can reach
}


def corruptions(plain, clean):
    """Four of the boundary-free entries, wrong in ways no setting predicts, so
    the error is noise the recovery has to survive rather than evidence for some
    other setting."""
    out = {}
    for i, pid in enumerate(plain):
        rule = CORRUPT.get(i)
        if rule is None:
            continue
        entry = json.loads(json.dumps(clean[pid]))
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
        out[pid] = entry
    return out


# --- the held-out quarter ----------------------------------------------------

def held_out_charts():
    """The 36 ordinary admissions, plus boundaries placed against these
    constants so that no recovered value is decorative."""
    P, W, C = PATHOGENS, WARDS, COMMENSALS
    out = list(gen2.held_out())
    out.append(tpl_uti("2026-03-01", H - 1, B, None, TW, R - 1,
                       P[0], P[2], W[1], W[4]))
    out.append(tpl_uti("2026-03-02", H + 1, B + 1, F, TW + 1, R,
                       P[5], P[3], W[4], W[0]))
    out.append(tpl_uti("2026-03-03", H + 2, None, F, TW, R - 1,
                       P[2], P[7], W[0], W[2]))
    out.append(tpl_uti("2026-03-04", H - 2, B, None, TW, R - 1,
                       P[7], P[1], W[2], W[3], tw_from="repeat"))
    out.append(tpl_sec("2026-03-01", H + 2, SL - 1, LM - 1, LG, TW, R - 1,
                       P[1], P[4], W[3], W[1]))
    out.append(tpl_sec("2026-03-02", H + 1, SL, LM - 1, LG + 1, TW + 1, R,
                       P[6], P[0], W[0], W[4]))
    out.append(tpl_sec("2026-03-03", H + 2, -2, LM - 1, LG + 1, TW, R - 1,
                       P[4], P[5], W[2], W[0]))
    out.append(tpl_com("2026-03-01", H - 1 + B, G, B, None, TW,
                       LM - 1, LG, R - 1, C[0], P[6], W[1], W[2]))
    out.append(tpl_com("2026-03-02", H - 1 + B, G + 1, B, F, TW + 1,
                       LM - 1, LG, R, C[2], P[3], W[3], W[4],
                       hang="tail"))
    out.append(tpl_com("2026-03-03", H + 1, G, B + 1, F, TW,
                       LM - 2, LG, R - 1, C[4], P[0], W[4], W[1]))
    out.append(tpl_com("2026-03-04", H - 1 + B, G, B, F + 1, TW,
                       LM - 1, LG + 1, R, C[1], P[7], W[0], W[3]))
    return out


# --- the checks --------------------------------------------------------------

def alternatives():
    for field, values in sorted(GRID.items()):
        for v in values:
            if v != getattr(TRUE, field):
                yield field, TRUE._replace(**{field: v})


def touch(pts):
    """For each chart, the constants that can change its adjudication."""
    base = {p["id"]: solve.report(TRUE, p) for p in pts}
    hit = dict((p["id"], set()) for p in pts)
    for field, alt in alternatives():
        for p in pts:
            if solve.report(alt, p) != base[p["id"]]:
                hit[p["id"]].add(field)
    return hit


def reach(pts):
    """For each single-constant error, how many held-out patients it changes."""
    base = {p["id"]: solve.report(TRUE, p) for p in pts}
    out = {}
    for field, alt in alternatives():
        n = sum(1 for p in pts if solve.report(alt, p) != base[p["id"]])
        key = "%s=%s" % (field, getattr(alt, field))
        out[key] = n
    return out


def sweep(pts, want, floor):
    want_skel = {k: solve.want_skeleton(v) for k, v in want.items()}
    adms = {p["id"]: [solve.Admission(x) for x in p["admissions"]]
            for p in pts}
    best, winners, scored = floor, [], 0
    for pc in itertools.product(*(list(GRID[f]) for f in POOL)):
        base = dict(zip(POOL, pc))
        stub = Params(order="UTI", rit_days=min(GRID["rit_days"]),
                      sec_start="iwp", sec_len=min(GRID["sec_len"]),
                      line_min_days=min(GRID["line_min_days"]), line_grace=0,
                      transfer_window=0, **base)
        pools = {p["id"]: solve.build_pool(stub, adms[p["id"]]) for p in pts}
        for wc in itertools.product(*(list(GRID[f]) for f in WALK)):
            mid = dict(base, **dict(zip(WALK, wc)))
            s2 = Params(line_min_days=min(GRID["line_min_days"]), line_grace=0,
                        transfer_window=0, **mid)
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


def document(charts, prefix):
    return [{"id": "%s-%03d" % (prefix, i + 1),
             "admissions": [a.dump() for a in adms]}
            for i, adms in enumerate(charts)]


def main():
    size = 1
    for f in GRID:
        size *= len(list(GRID[f]))
    print("grid: %d settings" % size)

    audit = document(audit_charts(), "AUD")
    n = len(audit)
    hit = touch(audit)
    plain = [p["id"] for p in audit if not hit[p["id"]]]
    thin = sorted(pid for pid, h in hit.items() if 0 < len(h) < 3)
    widths = [len(h) for h in hit.values() if h]
    print("audit: %d charts, %d conjunctive (touched by %d..%d constants, mean "
          "%.1f), %d on no boundary"
          % (n, len(widths), min(widths), max(widths),
             sum(widths) / float(len(widths)), len(plain)))
    if thin:
        print("REJECTED -- a single comparison isolates a constant on: %s"
              % ", ".join(thin))
        return 1
    if len(plain) < 4:
        print("REJECTED -- fewer than four boundary-free charts to corrupt")
        return 1

    clean = {p["id"]: solve.report(TRUE, p) for p in audit}
    want = dict(clean)
    want.update(corruptions(plain, clean))
    wrong = sum(1 for p in audit if want[p["id"]] != clean[p["id"]])

    t0 = time.time()
    if os.environ.get("SKIP_SWEEP"):
        print("SKIP_SWEEP set: not re-proving uniqueness (dev iteration only)")
        best, winners, scored = n - wrong, [TRUE], 0
    else:
        best, winners, scored = sweep(audit, want, n - 5)
    print("swept in %.0fs (%d settings scored past the prune); best agreement "
          "%d of %d; settings achieving it: %d"
          % (time.time() - t0, scored, best, n, len(winners)))
    for w in winners[:4]:
        print("   ", w)
    if len(winners) != 1 or winners[0] != TRUE:
        print("REJECTED -- the audit does not single out one setting")
        return 1

    heldout = document(held_out_charts(), "PT")
    got = reach(heldout)
    inert = sorted(k for k, v in got.items() if v == 0)
    if inert:
        print("REJECTED -- these single-constant errors change no held-out "
              "patient: %s" % ", ".join(inert))
        return 1
    print("held-out: %d patients; every one of the %d single-constant errors "
          "changes %d..%d of them"
          % (len(heldout), len(got), min(got.values()), max(got.values())))

    period = {"period_start": iso(gen2.PERIOD_START),
              "period_end": iso(gen2.PERIOD_END), "wards": WARDS}
    audit_doc = dict(period, patients=audit,
                     adjudications=[want[p["id"]] for p in audit])
    records_doc = dict(period, patients=heldout)
    counts = solve.line_days(TRUE, records_doc, heldout)
    expected = {
        "patient_ids": [p["id"] for p in heldout],
        "wards": WARDS,
        "patients": [solve.report(TRUE, p) for p in heldout],
        "central_line_days": [{"ward": w, "days": counts[w]} for w in WARDS],
    }
    for path, doc in ((os.path.join(DATA, "audited.json"), audit_doc),
                      (os.path.join(DATA, "records.json"), records_doc),
                      (os.path.join(TESTS, "expected.json"), expected)):
        with open(path, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
        print("wrote %s" % os.path.relpath(path, os.path.dirname(HERE)))

    print("audit %d patients, %d entries, %d wrong | held-out %d patients, "
          "%d events"
          % (n, sum(len(want[p["id"]]["uti"]) + len(want[p["id"]]["bsi"])
                    for p in audit), wrong, len(heldout),
             sum(len(e["uti"]) + len(e["bsi"]) for e in expected["patients"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
