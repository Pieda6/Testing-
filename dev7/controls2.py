"""What a wrong recovery costs on the held-out quarter.

Two columns. "audit" says whether the setting still reproduces the prior audit
-- by construction of the data it never does, since dev7/fit.py proved the audit
pins one setting, so a solver that fits properly and checks its fit will catch
every row here. "held-out" is the number of the 30 held-out patients still
fully right, and it is what a solver that fits sloppily actually scores.

The last row is the one to watch: a solver that recognises the domain and fills
in the values it remembers, rather than recovering them, gets most of them right
and two of them wrong.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve as S                                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = json.load(open(os.path.join(HERE, "audited.json")))
RECORDS = json.load(open(os.path.join(HERE, "records.json")))
TRUE = S.recover(AUDIT)
WANT = {p["id"]: p for p in
        [S.report(TRUE, x) for x in RECORDS["patients"]]}
TRUE_DAYS = S.line_days(TRUE, RECORDS, RECORDS["patients"])


def fits_audit(p):
    want = {a["id"]: a for a in AUDIT["adjudications"]}
    return all(S.report(p, pt) == want[pt["id"]] for pt in AUDIT["patients"])


def score(label, p):
    ok = sum(1 for x in RECORDS["patients"]
             if S.report(p, x) == WANT[x["id"]])
    days = S.line_days(p, RECORDS, RECORDS["patients"])
    tag = "" if days == TRUE_DAYS else "  (+ ward days wrong)"
    print("  %-46s audit %-3s   held-out %2d / %d%s"
          % (label, "yes" if fits_audit(p) else "no", ok,
             len(RECORDS["patients"]), tag))


def bump(**kw):
    return TRUE._replace(**kw)


def main():
    print("the recovered setting")
    score("reference", TRUE)

    print("one constant off")
    score("window reaches one day less far back", bump(iwp_before=2))
    score("window reaches one day further back", bump(iwp_before=4))
    score("window reaches one day less far forward", bump(iwp_after=2))
    score("window reaches one day further forward", bump(iwp_after=4))
    score("commensal cultures allowed two days apart", bump(commensal_gap=2))
    score("commensal cultures required on the same day", bump(commensal_gap=0))
    score("events dated by their culture", bump(doe_rule="culture"))
    score("admission day 2 counts as healthcare-associated", bump(hai_day=2))
    score("admission day 4 required", bump(hai_day=4))
    score("bloodstream adjudicated first", bump(order="BSI"))
    score("timeframe one day short", bump(rit_days=13))
    score("timeframe one day long", bump(rit_days=15))
    score("attribution period opens at the date of event",
          bump(sec_start="doe"))
    score("attribution period three days short", bump(sec_len=14))
    score("attribution period one day long", bump(sec_len=18))
    score("line required in place a day longer", bump(line_min_days=4))
    score("line required in place a day less", bump(line_min_days=2))
    score("day after removal not counted", bump(line_grace=0))
    score("two days after removal counted", bump(line_grace=2))
    score("transfer rule on the day of transfer only", bump(transfer_window=0))
    score("transfer rule stretched to two days", bump(transfer_window=2))

    print("filled in from memory instead of recovered")
    score("the familiar values, not these ones",
          bump(sec_start="doe", sec_len=14))


if __name__ == "__main__":
    main()
