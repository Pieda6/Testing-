"""The shipped data, third design: the audit publishes a summary, not answers.

The two earlier audits both handed over worked adjudications -- one per patient,
in the shape the agent has to produce. That is what kept the task crackable, and
it had nothing to do with which constants were chosen or how the charts were
laid out. Thirty-nine worked examples are a test suite. Implement the procedure,
score it, see which patients disagree, open one, find the rule you read wrongly,
fix it, score again. Being wrong came with a map to the error, so the search
collapsed into ordinary debugging and a competent solver walked it inside the
hour whatever the constants were.

So this audit publishes what a surveillance programme actually publishes: for
each ward and each month of the quarter, how many urinary events, how many
bloodstream events, and how many of those were central-line-associated. Fifty-
odd admissions collapse into forty-five numbers. No patient, no date, no
organism, no ward attribution you can check one at a time.

The constants remain recoverable -- proved by exhaustion below -- but a mismatch
no longer points anywhere. A cell one too high says something in that ward that
month adjudicated differently, and says nothing about whether the cause was a
wrong constant or a misread rule. There is no patient to open. Fitting cannot be
turned into debugging, which is the property the two earlier designs lacked.

Three of the published numbers are wrong, as published numbers are, so the fit
has to be robust rather than exact.

Checks, all three of which have rejected a design:

    uniqueness   exactly one setting matches the most published cells
    reach        every single-constant error changes at least one cell, else it
                 is not recoverable from the summary at all
    held-out     every single-constant error changes at least one held-out
                 patient, else the recovered value is decorative
"""
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve                                       # noqa: E402
from solve import Params                           # noqa: E402

import datetime as dt                              # noqa: E402
import gen2                                        # noqa: E402
import gen5                                        # noqa: E402
from gen2 import WARDS, PATHOGENS, COMMENSALS, iso   # noqa: E402
from gen5 import (TRUE, tpl_uti, tpl_sec, tpl_com, tpl_plain,  # noqa: E402
                  B, F, G, H, R, SL, LM, LG, TW)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "task7", "environment", "data")
TESTS = os.path.join(HERE, "..", "task7", "tests")

GRID = dict(solve.GRID)
POOL, WALK, TRIM = solve.POOL_FIELDS, solve.WALK_FIELDS, solve.TRIM_FIELDS

P, C = PATHOGENS, COMMENSALS
W = WARDS


def block(month, k):
    """Sixteen boundary-bearing admissions, rotated by month so that every ward
    carries events in every month of the quarter."""
    def w(i):
        return W[(i + k) % len(W)]

    def p(i):
        return P[(i + 3 * k) % len(P)]

    def c(i):
        return C[(i + k) % len(C)]

    def dt_(day):
        return "2026-%02d-%02d" % (month, day)

    out = []
    out.append(tpl_uti(dt_(2), H - 1, B, None, TW, R - 1, p(3), p(4), w(2), w(3)))
    out.append(tpl_uti(dt_(3), H + 2, B + 1, F, TW, R, p(4), p(0), w(3), w(2)))
    out.append(tpl_uti(dt_(4), H, B, F + 1, TW + 1, R, p(1), p(6), w(0), w(4)))
    out.append(tpl_uti(dt_(5), H - 1, B - 2, None, TW, R - 1,
                       p(6), p(3), w(4), w(1)))
    out.append(tpl_uti(dt_(6), H + 1, B, F - 1, TW + 1, R - 1,
                       p(7), p(5), w(1), w(0)))
    out.append(tpl_uti(dt_(7), H + 2, None, F, TW, R, p(5), p(1), w(2), w(4)))
    out.append(tpl_uti(dt_(8), H + 3, B + 1, F - 1, TW, R, p(2), p(4), w(4), w(3)))
    out.append(tpl_uti(dt_(9), H - 2, B, None, TW + 1, R - 1,
                       p(2), p(5), w(1), w(3), tw_from="repeat"))

    out.append(tpl_sec(dt_(2), H + 2, SL - 1, LM - 1, LG, TW, R - 1,
                       p(3), p(1), w(2), w(3)))
    out.append(tpl_sec(dt_(3), H + 1, SL, LM - 1, LG, TW + 1, R,
                       p(4), p(6), w(3), w(0)))
    out.append(tpl_sec(dt_(4), H + 2, -2, LM - 2, LG, TW, R - 1,
                       p(0), p(2), w(0), w(1)))
    out.append(tpl_sec(dt_(5), H + 3, SL + 1, LM - 1, LG + 1, TW + 1, R,
                       p(6), p(3), w(4), w(2)))
    out.append(tpl_sec(dt_(6), H + 1, SL - 5, LM - 1, LG, TW, R - 1,
                       p(7), p(4), w(1), w(4)))

    out.append(tpl_com(dt_(2), H - 1 + B, G, B, None, TW,
                       LM - 1, LG, R - 1, c(4), p(0), w(4), w(2)))
    out.append(tpl_com(dt_(3), H + 2, G, None, F, TW + 1,
                       LM - 1, LG, R, c(1), p(3), w(0), w(3)))
    out.append(tpl_com(dt_(4), H + 1, G + 1, B, F, TW,
                       LM - 1, LG, R - 1, c(3), p(6), w(1), w(0),
                       hang="tail"))
    return out


def ladders():
    """Charts that separate values a single boundary cannot.

    A summary only shows counts, so two settings that report the same number of
    events in the same ward in the same month are indistinguishable however
    differently they got there. These charts make each value of the wider-
    reaching constants change a count, and change it by a different amount.
    """
    out = []

    # Four urine cultures a fortnight apart, each with one sign further beyond
    # its culture than the last. Nothing qualifies at the true width; each extra
    # day of forward reach turns exactly one more of them into an event.
    a = gen5.Adm("2026-01-05", "2026-02-26")
    a.w(W[3], "2026-01-05")
    for i, off in enumerate((F + 1, F + 2, F + 3, F + 4)):
        c = gen5.day(gen5.d("2026-01-05"), 6 + 12 * i)
        a.urine(iso(c), P[(i + 1) % len(P)])
        a.sign(iso(gen5.day(c, off)), "dysuria")
    out.append([a])

    # Two admissions whose only culture falls a day and two days below the cut:
    # nothing at the true cut, one more event for each day the cut drops.
    out.append(tpl_uti("2026-02-05", H - 2, B, None, None, None,
                       P[5], P[6], W[0], W[1]))
    out.append(tpl_uti("2026-03-06", H - 3, B, None, None, None,
                       P[6], P[7], W[2], W[3]))

    # Commensal pairs drawn a day and two days beyond the true gap, placed so a
    # pair that does qualify clears the admission cut and is reported.
    out.append(tpl_com("2026-02-07", H - 1 + B, G + 1, B, None, TW,
                       LM - 1, LG, R - 1, C[0], P[2], W[4], W[0]))
    out.append(tpl_com("2026-03-08", H - 1 + B, G + 2, B, None, TW,
                       LM - 1, LG, R - 1, C[3], P[4], W[1], W[2]))
    return out


def audit_charts():
    out = []
    for k, month in enumerate((1, 2, 3)):
        out.extend(block(month, k))
    out.extend(ladders())
    # ordinary admissions, and two blood cultures growing three names each,
    # which the contamination rule disregards entirely
    out.append(tpl_plain("2026-01-20", 24, 10, P[4], "blood", W[0]))
    out.append(tpl_plain("2026-02-20", 24, 11, P[3], "urine", W[1]))
    out.append(tpl_plain("2026-03-18", 24, 10, P[5], "blood", W[2]))
    a = tpl_plain("2026-01-22", 24, 9, P[6], "blood", W[3])
    a[0].blood("2026-02-01", P[1], P[2], C[0])
    out.append(a)
    a = tpl_plain("2026-02-22", 24, 9, P[0], "blood", W[4])
    a[0].blood("2026-03-04", P[3], P[5], C[2])
    out.append(a)
    # a urine culture growing only a yeast: not eligible for a urinary event
    a = tpl_plain("2026-03-05", 22, 8, P[2], "blood", W[1])
    a[0].urine("2026-03-16", P[0]).sign("2026-03-16", "dysuria")
    out.append(a)
    return out


FIELDS = ("uti_events", "bsi_events", "central_line_associated")


def numbers(cells):
    return [c[f] for c in cells for f in FIELDS]


def choose_corruptions(doc, patients, want=3):
    """Which published numbers to get wrong, and by how much.

    A corrupted number is only noise if no wrong setting can produce it. On a
    table of counts that is a sharper constraint than it was on worked
    adjudications: the truth matches every cell but the corrupted ones, so a
    wrong setting that happens to predict a corrupted value there -- and differs
    nowhere else -- ties or wins. Two conditions rule that out, and both are
    checked rather than assumed:

      * at the corrupted position, no single-constant error predicts the value
        published; and
      * no single-constant error confines all of its changes to the corrupted
        positions, so every one of them still loses somewhere else.
    """
    clean = numbers(solve.summary(doc, [solve.report(TRUE, p)
                                        for p in patients]))
    alts = []
    for field, alt in gen5.alternatives():
        n = numbers(solve.summary(doc, [solve.report(alt, p)
                                        for p in patients]))
        alts.append(("%s=%s" % (field, getattr(alt, field)),
                     frozenset(i for i in range(len(clean))
                               if n[i] != clean[i]), n))

    picks = []
    for i in range(len(clean)):
        for delta in (2, -2, 3):
            v = clean[i] + delta
            if v < 0:
                continue
            if any(n[i] == v for _l, _c, n in alts):
                continue
            picks.append((i, delta))
            break

    # one of each kind of number, and no two in the same ward or the same
    # month, so the errors read as three separate miscounts rather than one
    # mangled cell
    chosen, wards, months = [], set(), set()
    for field in range(3):
        for i, delta in picks:
            if i % 3 != field:
                continue
            cell = doc["wards"][(i // 3) // len(solve.months_of(doc))], \
                solve.months_of(doc)[(i // 3) % len(solve.months_of(doc))]
            if cell[0] in wards or cell[1] in months:
                continue
            trial = set(x for x, _ in chosen) | {i}
            if all(changed - trial for _l, changed, _n in alts):
                chosen.append((i, delta))
                wards.add(cell[0])
                months.add(cell[1])
                break
    assert len(chosen) == want, ("only %d publishable errors are inexplicable"
                                 % len(chosen))
    covered = set(x for x, _ in chosen)
    for label, changed, _n in alts:
        assert changed - covered, "%s changes nothing outside the errors" % label
    return chosen


def publish(doc, patients, reports):
    cells = solve.summary(doc, reports)
    out = []
    for i, delta in choose_corruptions(doc, patients):
        cells[i // 3][FIELDS[i % 3]] += delta
        out.append("%s %s %s %+d" % (cells[i // 3]["ward"],
                                     cells[i // 3]["month"],
                                     FIELDS[i % 3], delta))
    return cells, out


def sweep(doc, published_cells, floor):
    """Every setting matching at least `floor` cells, and the best score."""
    published = {(c["ward"], c["month"]):
                 (c["uti_events"], c["bsi_events"],
                  c["central_line_associated"]) for c in published_cells}
    keys = sorted(published)
    total = 3 * len(keys)
    months = solve.months_of(doc)
    pub_month = {}
    for i, kind in enumerate(("uti", "bsi")):
        for m in months:
            pub_month[(kind, m)] = sum(v[i] for k, v in published.items()
                                       if k[1] == m)
    order = list(doc["patients"])
    admissions = {pt["id"]: [solve.Admission(a) for a in pt["admissions"]]
                  for pt in order}

    # Seeded with the truth's own score. The bound below only bites once the
    # incumbent is high, and the truth is reached late in the iteration order,
    # so starting from it is the difference between minutes and hours. Nothing
    # is hidden by it: a setting that ties is still collected, and one that
    # beats it still replaces it.
    truth = [solve.report(TRUE, pt) for pt in order]
    seed = {(c["ward"], c["month"]): c for c in solve.summary(doc, truth)}
    best = sum(1 for k in keys for i, f in enumerate(
        ("uti_events", "bsi_events", "central_line_associated"))
        if seed[k][f] == published[k][i])
    winners, scored = [TRUE], 0
    print("   the generating setting matches %d of %d published numbers"
          % (best, total))
    for pc in itertools.product(*(list(GRID[f]) for f in POOL)):
        base = dict(zip(POOL, pc))
        stub = Params(order="UTI", rit_days=min(GRID["rit_days"]),
                      sec_start="iwp", sec_len=min(GRID["sec_len"]),
                      line_min_days=min(GRID["line_min_days"]), line_grace=0,
                      transfer_window=0, **base)
        pools = {pt["id"]: solve.build_pool(stub, admissions[pt["id"]])
                 for pt in order}
        for wc in itertools.product(*(list(GRID[f]) for f in WALK)):
            mid = dict(base, **dict(zip(WALK, wc)))
            s2 = Params(line_min_days=min(GRID["line_min_days"]), line_grace=0,
                        transfer_window=0, **mid)
            events, got = [], {}
            for pt in order:
                wk = solve.walk(s2, pools[pt["id"]])
                for kind in ("UTI", "BSI"):
                    for e in wk[kind]:
                        mon = iso(e["doe"])[:7]
                        events.append((kind, e["adm"], e["doe"], mon))
                        key = (kind.lower(), mon)
                        got[key] = got.get(key, 0) + 1
            miss = sum(1 for k, v in pub_month.items() if got.get(k, 0) != v)
            if total - miss < best:
                continue                    # cannot reach the incumbent

            # The last three constants only move an event between two known
            # wards and flip one boolean, so reduce every event to the integers
            # those two decisions turn on and let the loops below be
            # arithmetic. Without this the bound above is the only prune and it
            # is far too weak: there are just two trim-independent totals per
            # month, so almost nothing is skipped and the whole product gets
            # scored.
            table = []
            for kind, adm, doe, mon in events:
                arrive, ward = adm.ward_on(doe)
                prev = None
                if arrive is not None:
                    _a, prev = adm.ward_on(arrive - dt.timedelta(days=1))
                gap = (doe - arrive).days if arrive is not None else None
                table.append((kind == "BSI", mon, ward, prev, gap,
                              [((doe - i).days, (doe - r).days)
                               for i, r in adm.lines]))

            for tw in GRID["transfer_window"]:
                counts, wards = {}, []
                for is_bsi, mon, ward, prev, gap, _lines in table:
                    w = prev if (prev is not None and gap is not None
                                 and gap <= tw) else ward
                    wards.append(w)
                    cell = counts.setdefault((w, mon), [0, 0])
                    cell[1 if is_bsi else 0] += 1
                flat = 0
                for k in keys:
                    have = counts.get(k, (0, 0))
                    flat += sum(1 for i in (0, 1) if have[i] == published[k][i])
                if flat + len(keys) < best:
                    continue            # the line flags cannot make up the rest
                for lm in GRID["line_min_days"]:
                    for lg in GRID["line_grace"]:
                        assoc = {}
                        for j, row in enumerate(table):
                            if row[0] and any(di >= lm - 1 and dr <= lg
                                              for di, dr in row[5]):
                                key = (wards[j], row[1])
                                assoc[key] = assoc.get(key, 0) + 1
                        agree = flat + sum(
                            1 for k in keys
                            if assoc.get(k, 0) == published[k][2])
                        if agree < best:
                            continue
                        scored += 1
                        full = Params(line_min_days=lm, line_grace=lg,
                                   transfer_window=tw, **mid)
                        if agree > best:
                            best, winners = agree, [full]
                        elif winners:
                            winners.append(full)
    return best, winners, scored, total


def held_out_charts():
    """The held-out quarter, plus two admissions that exercise the two rules the
    audit needs but the ordinary records never happen to hit: a blood culture
    growing three names, which is disregarded in full, and a urine culture
    growing only a yeast, which is not a urinary candidate at all."""
    out = list(gen5.held_out_charts())
    a = tpl_plain("2026-03-05", 22, 8, P[2], "blood", W[3])
    a[0].blood("2026-03-17", P[1], P[4], C[1])
    out.append(a)
    a = tpl_plain("2026-03-06", 22, 9, P[5], "blood", W[2])
    a[0].urine("2026-03-18", P[0]).sign("2026-03-18", "dysuria")
    out.append(a)
    return out


def document(charts, prefix):
    return [{"id": "%s-%03d" % (prefix, i + 1),
             "admissions": [a.dump() for a in adms]}
            for i, adms in enumerate(charts)]


def main():
    period = {"period_start": iso(gen2.PERIOD_START),
              "period_end": iso(gen2.PERIOD_END), "wards": WARDS}
    audit = document(audit_charts(), "AUD")
    audit_doc = dict(period, patients=audit)
    reports = [solve.report(TRUE, p) for p in audit]
    cells, errors = publish(audit_doc, audit, reports)
    audit_doc["summary"] = cells
    audit_doc["central_line_days"] = [
        {"ward": w, "days": solve.line_days(TRUE, audit_doc, audit)[w]}
        for w in WARDS]
    total = 3 * len(cells)
    events = sum(len(r["uti"]) + len(r["bsi"]) for r in reports)
    print("audit: %d admissions, %d events, published as %d cells (%d numbers)"
          % (len(audit), events, len(cells), total))
    print("published wrong, and inexplicable under every single-constant "
          "error: %s" % "; ".join(errors))

    # reach: a constant the summary cannot see is not recoverable from it
    clean = {(c["ward"], c["month"]): c for c in solve.summary(audit_doc,
                                                              reports)}
    blind = []
    for field, alt in gen5.alternatives():
        alt_cells = solve.summary(audit_doc,
                                  [solve.report(alt, p) for p in audit])
        if all(c == clean[(c["ward"], c["month"])] for c in alt_cells):
            blind.append("%s=%s" % (field, getattr(alt, field)))
    if blind:
        print("REJECTED -- the summary cannot see: %s" % ", ".join(blind))
        return 1
    print("every single-constant error moves at least one published cell")

    t0 = time.time()
    best, winners, scored, total = sweep(audit_doc, cells, total - 8)
    winners = sorted(set(winners))          # the seed reappears when reached
    print("swept in %.0fs (%d settings scored past the bound); best %d of %d "
          "numbers; settings achieving it: %d"
          % (time.time() - t0, scored, best, total, len(winners)))
    for x in winners[:4]:
        print("   ", x)
    if len(winners) != 1 or winners[0] != TRUE:
        print("REJECTED -- the summary does not single out one setting")
        return 1

    heldout = document(held_out_charts(), "PT")
    got = gen5.reach(heldout)
    inert = sorted(k for k, v in got.items() if v == 0)
    if inert:
        print("REJECTED -- these single-constant errors change no held-out "
              "patient: %s" % ", ".join(inert))
        return 1
    print("held-out: %d patients; every one of the %d single-constant errors "
          "changes %d..%d of them"
          % (len(heldout), len(got), min(got.values()), max(got.values())))

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
            f.write("\\n")
        print("wrote %s" % os.path.relpath(path, os.path.dirname(HERE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
