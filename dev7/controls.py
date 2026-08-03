"""How far each plausible misreading of the manual gets, on the shipped data.

Grading is all-or-nothing across all 36 patients, so anything short of 36/36
scores zero. The per-patient numbers are what goes in difficulty_explanation.

There is no "does it still fit the source data" column here, unlike a task
where a recovered model can be replayed. An adjudication has no self-consistency
test: every one of these produces a coherent, plausible, internally consistent
answer set, and nothing in the records contradicts any of them. That is the
point -- all of these errors are silent.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import solve as ref                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ref.RECORDS_PATH = os.path.join(HERE, "records.json")
DOC = json.load(open(os.path.join(HERE, "records.json")))
TRUE = ref.solve(DOC)
TRUE_BY_ID = {p["id"]: p for p in TRUE["patients"]}


def score(label, patch):
    saved = {name: getattr(ref, name) for name in patch}
    try:
        for name, fn in patch.items():
            setattr(ref, name, fn)
        got = ref.solve(DOC)
    finally:
        for name, fn in saved.items():
            setattr(ref, name, fn)
    ok = sum(1 for p in got["patients"] if p == TRUE_BY_ID[p["id"]])
    days = "same" if got["central_line_days"] == TRUE["central_line_days"] \
        else "wrong"
    print("  %-52s %2d / %d   ward line-days: %s"
          % (label, ok, len(TRUE["patients"]), days))


# --- individual misreadings ----------------------------------------------

def no_secondary_rule(utis, cand):
    """Every positive blood culture treated as a primary bloodstream infection."""
    return None


def secondary_period_long(utis, cand):
    """Attribution period run to day 15 of the timeframe instead of day 14."""
    for uti in utis:
        end = uti["date_of_event"] + dt.timedelta(days=ref.RIT_DAYS)
        if uti["iwp_start"] <= cand["anchor"] <= end and \
                set(cand["organisms"]) & set(uti["organisms"]):
            return uti
    return None


def secondary_ignores_merges(utis, cand):
    """Matched only against the organisms the UTI's own culture grew."""
    for uti in utis:
        end = uti["date_of_event"] + dt.timedelta(days=ref.RIT_DAYS - 1)
        if uti["iwp_start"] <= cand["anchor"] <= end and \
                set(cand["organisms"]) & set(uti["seed"]):
            return uti
    return None


def doe_is_culture_date(adm):
    """Signs ignored when dating an event; the culture date is used."""
    out = []
    for kind, anchor, doe, orgs in _orig_candidates(adm):
        out.append((kind, anchor, anchor, orgs))
    return out


def single_commensal_counts(adm):
    """A lone blood culture growing a commensal treated as an event."""
    out = list(_orig_candidates(adm))
    for date, source, orgs in adm.cultures:
        if source != "blood":
            continue
        for org in ref.commensals(orgs):
            if not any(k == "BSI" and o == [org] for k, _a, _d, o in out):
                out.append(("BSI", date, date, [org]))
    return out


def commensal_pair_unmatched(adm):
    """Two commensal cultures a day apart accepted without matching by name."""
    out = list(_orig_candidates(adm))
    blood = [(t, ref.commensals(o)) for t, s, o in adm.cultures if s == "blood"]
    for i, (t1, c1) in enumerate(blood):
        for t2, c2 in blood[i + 1:]:
            if abs((t2 - t1).days) > 1 or not c1 or not c2:
                continue
            anchor = min(t1, t2)
            lo = anchor - dt.timedelta(days=ref.IWP_RADIUS)
            hi = anchor + dt.timedelta(days=ref.IWP_RADIUS)
            if adm.sign_dates(ref.BSI_SIGNS, lo, hi):
                org = sorted(set(c1) | set(c2))[0]
                if not any(k == "BSI" and a == anchor for k, a, _d, _o in out):
                    out.append(("BSI", anchor, anchor, [org]))
    return out


def commensal_pair_two_days(adm):
    """Cultures up to two days apart accepted as a pair."""
    out = list(_orig_candidates(adm))
    blood = [(t, ref.commensals(o)) for t, s, o in adm.cultures if s == "blood"]
    for i, (t1, c1) in enumerate(blood):
        for t2, c2 in blood[i + 1:]:
            if not 1 < abs((t2 - t1).days) <= 2:
                continue
            for org in sorted(set(c1) & set(c2)):
                anchor = min(t1, t2)
                lo = anchor - dt.timedelta(days=ref.IWP_RADIUS)
                hi = anchor + dt.timedelta(days=ref.IWP_RADIUS)
                signs = adm.sign_dates(ref.BSI_SIGNS, lo, hi)
                if signs:
                    out.append(("BSI", anchor, min(anchor, signs[0]), [org]))
    return out


def line_days_exclusive(doc):
    """Removal day not counted as a line day."""
    counts = dict((w, 0) for w in doc["wards"])
    lo, hi = ref.d(doc["period_start"]), ref.d(doc["period_end"])
    for patient in doc["patients"]:
        for raw in patient["admissions"]:
            adm = ref.Admission(raw)
            day = adm.admit
            while day <= adm.discharge:
                inside = any(i <= day < r for i, r in adm.lines)
                if lo <= day < hi and inside:
                    _a, ward = adm.ward_on(day)
                    if ward:
                        counts[ward] += 1
                day += dt.timedelta(days=1)
    return counts


def line_days_no_period_clip(doc):
    """Days outside the reporting period counted."""
    counts = dict((w, 0) for w in doc["wards"])
    for patient in doc["patients"]:
        for raw in patient["admissions"]:
            adm = ref.Admission(raw)
            day = adm.admit
            while day <= adm.discharge:
                if adm.line_on(day):
                    _a, ward = adm.ward_on(day)
                    if ward:
                        counts[ward] += 1
                day += dt.timedelta(days=1)
    return counts


def line_needs_three_full_days(adm, doe):
    """Line days counted as elapsed 24-hour periods rather than calendar days."""
    for insert, remove in adm.lines:
        if doe >= insert + dt.timedelta(days=3) and \
                doe <= remove + dt.timedelta(days=1):
            return True
    return False


def line_removal_day_only(adm, doe):
    """The day after removal not counted."""
    for insert, remove in adm.lines:
        if doe >= insert + dt.timedelta(days=2) and doe <= remove:
            return True
    return False


def attribute_receiving_ward(adm, doe):
    """The transfer rule dropped: the ward occupied on the date of event."""
    _arrive, ward = adm.ward_on(doe)
    return ward


def attribute_only_same_day(adm, doe):
    """Transfer rule applied on the day of transfer but not the day after."""
    arrive, ward = adm.ward_on(doe)
    if ward is None:
        return None
    if arrive == doe:
        _pa, prev = adm.ward_on(arrive - dt.timedelta(days=1))
        if prev is not None:
            return prev
    return ward


_orig_candidates = ref.candidates
_orig_adjudicate = ref.adjudicate


def make_adjudicate(rit_days=None, hai_day=None, merge_suppressed=True):
    """Variants that need the walk itself changed rather than one helper."""
    def wrapped(patient):
        old_rit, old_hai, old_merge = ref.RIT_DAYS, ref.HAI_DAY, ref.merge
        try:
            if rit_days is not None:
                ref.RIT_DAYS = rit_days
            if hai_day is not None:
                ref.HAI_DAY = hai_day
            if not merge_suppressed:
                ref.merge = lambda event, organisms: None
            return _orig_adjudicate(patient)
        finally:
            ref.RIT_DAYS, ref.HAI_DAY, ref.merge = old_rit, old_hai, old_merge
    return wrapped


def main():
    print("reference")
    score("reference", {})

    print("dating the event")
    score("signs ignored; the culture date used as date of event",
          {"candidates": doe_is_culture_date})

    print("healthcare association")
    score("admission day 2 treated as reportable",
          {"adjudicate": make_adjudicate(hai_day=2)})
    score("admission day 4 required",
          {"adjudicate": make_adjudicate(hai_day=4)})

    print("repeat infection timeframe")
    score("timeframe ignored; every candidate reported",
          {"adjudicate": make_adjudicate(rit_days=0)})
    score("timeframe run to 15 days",
          {"adjudicate": make_adjudicate(rit_days=15)})
    score("timeframe counted from the day after the date of event",
          {"adjudicate": make_adjudicate(rit_days=13)})
    score("suppressed candidates dropped instead of merged",
          {"adjudicate": make_adjudicate(merge_suppressed=False)})

    print("secondary bloodstream infections")
    score("secondary rule not applied at all",
          {"secondary_host": no_secondary_rule})
    score("attribution period one day too long",
          {"secondary_host": secondary_period_long})
    score("matched against the UTI culture only, not merged organisms",
          {"secondary_host": secondary_ignores_merges})

    print("commensals")
    score("a lone commensal culture counted",
          {"candidates": single_commensal_counts})
    score("commensal pair accepted without matching by name",
          {"candidates": commensal_pair_unmatched})
    score("commensal pair accepted two days apart",
          {"candidates": commensal_pair_two_days})

    print("central line association")
    score("line days counted as elapsed 24-hour periods",
          {"line_associated": line_needs_three_full_days})
    score("the day after removal not counted",
          {"line_associated": line_removal_day_only})

    print("ward attribution")
    score("transfer rule dropped; the receiving ward charged",
          {"attribute": attribute_receiving_ward})
    score("transfer rule applied on the day of transfer only",
          {"attribute": attribute_only_same_day})

    print("ward line-day denominators")
    score("removal day not counted as a line day",
          {"line_days": line_days_exclusive})
    score("days outside the reporting period counted",
          {"line_days": line_days_no_period_clip})


if __name__ == "__main__":
    main()
