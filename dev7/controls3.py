"""What a wrong recovery costs on the held-out quarter.

Two questions per control. Does the audit catch it -- would a solver that scored
its fit have seen this setting lose? And if it did not, how many of the held-out
patients does it still get completely right? Grading is all-or-nothing across
every patient and every ward denominator, so anything short of all of them is
zero; the counts are here to show that no constant is decorative and that the
familiar values are not a shortcut.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve                                     # noqa: E402

import gen5                                      # noqa: E402

TRUE = gen5.TRUE

# The values the well-known national definitions use. Ten of the twelve differ
# from the ones this programme uses, so filling them in from memory is not a
# shortcut; this row measures exactly how far off it lands.
FAMILIAR = solve.Params(iwp_before=3, iwp_after=3, commensal_gap=1,
                        doe_rule="earliest", hai_day=3, order="UTI",
                        rit_days=14, sec_start="iwp", sec_len=17,
                        line_min_days=3, line_grace=1, transfer_window=1)

LABEL = {
    "iwp_before": "window reaches %s days back",
    "iwp_after": "window reaches %s days forward",
    "commensal_gap": "commensal draws allowed %s days apart",
    "doe_rule": "events dated by their %s",
    "hai_day": "admission day %s is the first that counts",
    "order": "%s adjudicated first",
    "rit_days": "timeframe runs %s days",
    "sec_start": "attribution period opens at the %s",
    "sec_len": "attribution period runs %s days",
    "line_min_days": "line required in place %s days",
    "line_grace": "%s days after removal still count",
    "transfer_window": "transfer rule reaches %s days",
}


def main():
    with open(os.path.join(gen5.DATA, "records.json")) as f:
        records = json.load(f)
    with open(os.path.join(gen5.DATA, "audited.json")) as f:
        audit = json.load(f)
    published = audit["summary"]
    fields = ("uti_events", "bsi_events", "central_line_associated")
    pts = records["patients"]
    n = len(pts)

    def audit_score(p):
        got = {(c["ward"], c["month"]): c for c in solve.summary(
            audit, [solve.report(p, a) for a in audit["patients"]])}
        return sum(1 for c in published for f in fields
                   if got[(c["ward"], c["month"])][f] == c[f])

    def held_score(p):
        right = sum(1 for a in pts if solve.report(p, a) == solve.report(TRUE, a))
        counts = solve.line_days(p, records, pts)
        true_counts = solve.line_days(TRUE, records, pts)
        return right, counts == true_counts

    base = audit_score(TRUE)
    print("the recovered setting matches %d of the %d published numbers\n"
          % (base, 3 * len(published)))
    print("  %-52s %-14s %s" % ("", "audit", "held-out"))
    r, dens = held_score(TRUE)
    print("  %-52s %-14s %d / %d%s"
          % ("reference", "%d" % base, r, n, "" if dens else "  DENOM WRONG"))

    rows = []
    for field, alt in gen5.alternatives():
        v = getattr(alt, field)
        label = LABEL[field] % v
        a = audit_score(alt)
        r, dens = held_score(alt)
        rows.append((r, label, a, dens))
    rows.sort()
    print("\none constant recovered wrongly")
    for r, label, a, dens in rows:
        print("  %-52s %-14s %d / %d%s"
              % (label, "loses by %d" % (base - a) if a < base else "TIES",
                 r, n, "" if dens else "  denominators wrong too"))

    a = audit_score(FAMILIAR)
    r, dens = held_score(FAMILIAR)
    print("\n  %-52s %-14s %d / %d%s"
          % ("the familiar values, filled in from memory",
             "loses by %d" % (base - a) if a < base else "TIES", r, n,
             "" if dens else "  denominators wrong too"))

    ties = [row for row in rows if row[2] >= base]
    if ties:
        print("\nNOT WELL POSED -- %d wrong setting(s) match the summary"
              % len(ties))
        return 1
    worst = max(r for r, _l, _a, _d in rows)
    print("\nevery single-constant error loses on the summary and costs at "
          "least "
          "%d of the %d held-out patients" % (n - worst, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
