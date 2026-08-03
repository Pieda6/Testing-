"""Reference adjudicator for dynamo/hai-surveillance-adjudication.

Reads /app/data/records.json, applies /app/data/manual.md, writes
/app/answer.json. Pure standard library, no randomness, no network.

The manual specifies a deterministic procedure, so the answer is a function of
the records. What makes it hard is that the procedure's steps are coupled, and
every way of getting them wrong produces a coherent, plausible, wrong answer
set. There is nothing to check the result against -- an adjudication has no
self-consistency test the way a recovered model replayed against a log does.

The shape of a correct implementation:

1. Build candidates. A blood culture with a recognised pathogen is a candidate
   on its own. A blood culture growing only commensals is not -- that needs a
   second culture of the same admission, on the same or the next calendar day,
   growing the same commensal, plus a qualifying sign inside the window. A urine
   culture with a recognised pathogen needs a qualifying sign too.

2. Date the candidates. This is where the first silent error lives: the date of
   event is the earliest ELEMENT used to meet the definition, which is often a
   sign preceding the culture, not the culture date. It decides healthcare
   association, ward attribution and line association, so getting it wrong
   moves three answers at once, and can drag an event onto admission day 2 where
   it stops being reportable at all.

3. Adjudicate urinary tract infections first, then bloodstream infections, each
   in date-of-event order. The order is not cosmetic: a reported urinary tract
   infection can demote a later blood culture to secondary, and organism lists
   grow as suppressions merge into them -- so a blood culture can be secondary
   only because of an organism a previous suppression added.

4. Keep one open repeat infection timeframe per type per patient. Inside it a
   same-type candidate is not a new event; its organisms join the event that
   opened the timeframe. The timeframe is 14 days counting the date of event as
   day 1, so day 14 is still inside and day 15 is not, and it carries across
   admissions.

5. Only then work out line association and ward attribution, both of which are
   calendar-day arithmetic with an off-by-one waiting: a line must be in place
   more than two days, and the day after removal still counts; a ward arrival on
   the date of event or the day before sends the event to the transferring ward.
"""
import datetime as dt
import json
import os

DATA_DIR = "/app/data"
RECORDS_PATH = os.path.join(DATA_DIR, "records.json")
RESULT_PATH = "/app/answer.json"

COMMENSALS = frozenset([
    "Bacillus species",
    "Corynebacterium species",
    "Cutibacterium acnes",
    "Micrococcus species",
    "Staphylococcus epidermidis",
])
BSI_SIGNS = frozenset(["fever", "chills", "hypotension"])
UTI_SIGNS = frozenset(["fever", "dysuria", "urgency", "suprapubic_tenderness",
                       "costovertebral_tenderness"])
IWP_RADIUS = 3
RIT_DAYS = 14
HAI_DAY = 3


def d(s):
    return dt.date.fromisoformat(s)


def iso(x):
    return x.isoformat()


def days(a, b):
    return (b - a).days


class Admission(object):
    def __init__(self, raw):
        self.admit, self.discharge = d(raw["admit"]), d(raw["discharge"])
        self.wards = [(d(w["arrive"]), w["ward"]) for w in raw["wards"]]
        self.wards.sort()
        self.lines = [(d(l["insert"]), d(l["remove"]))
                      for l in raw["central_lines"]]
        self.cultures = [(d(c["date"]), c["source"], list(c["organisms"]))
                         for c in raw["cultures"]]
        self.signs = {}
        for s in raw["signs"]:
            self.signs.setdefault(d(s["date"]), set()).update(s["elements"])

    def ward_on(self, day):
        """The ward occupied on `day`, with its arrival date, or (None, None)."""
        if not (self.admit <= day <= self.discharge):
            return None, None
        cur = None
        for arrive, ward in self.wards:
            if arrive <= day:
                cur = (arrive, ward)
        return cur if cur else (None, None)

    def line_on(self, day):
        return any(i <= day <= r for i, r in self.lines)

    def sign_dates(self, allowed, lo, hi):
        """Dates in [lo, hi] carrying at least one of `allowed`."""
        return sorted(t for t, els in self.signs.items()
                      if lo <= t <= hi and (els & allowed))


def pathogens(organisms):
    return sorted(o for o in organisms if o not in COMMENSALS)


def commensals(organisms):
    return sorted(o for o in organisms if o in COMMENSALS)


def candidates(adm):
    """Every candidate of one admission: (type, anchor, doe, organisms)."""
    out = []

    for date, source, orgs in adm.cultures:
        lo, hi = date - dt.timedelta(days=IWP_RADIUS), \
            date + dt.timedelta(days=IWP_RADIUS)
        if source == "blood":
            found = pathogens(orgs)
            if found:
                out.append(("BSI", date, date, found))
        else:
            found = pathogens(orgs)
            if not found:
                continue
            signs = adm.sign_dates(UTI_SIGNS, lo, hi)
            if signs:
                out.append(("UTI", date, min(date, signs[0]), found))

    # BSI-C: a matching commensal on two cultures a day apart at most
    blood = [(t, commensals(o)) for t, s, o in adm.cultures if s == "blood"]
    seen = set()
    for i, (t1, c1) in enumerate(blood):
        for t2, c2 in blood[i + 1:]:
            if abs(days(t1, t2)) > 1:
                continue
            for org in sorted(set(c1) & set(c2)):
                anchor = min(t1, t2)
                if (anchor, org) in seen:
                    continue
                lo = anchor - dt.timedelta(days=IWP_RADIUS)
                hi = anchor + dt.timedelta(days=IWP_RADIUS)
                signs = adm.sign_dates(BSI_SIGNS, lo, hi)
                if signs:
                    seen.add((anchor, org))
                    out.append(("BSI", anchor, min(anchor, signs[0]), [org]))
    return out


def line_associated(adm, doe):
    for insert, remove in adm.lines:
        if doe >= insert + dt.timedelta(days=2) and \
                doe <= remove + dt.timedelta(days=1):
            return True
    return False


def attribute(adm, doe):
    """The ward the event is charged to, applying the transfer rule."""
    arrive, ward = adm.ward_on(doe)
    if ward is None:
        return None
    if arrive == doe or arrive == doe - dt.timedelta(days=1):
        prev_arrive, prev_ward = adm.ward_on(arrive - dt.timedelta(days=1))
        if prev_ward is not None:
            return prev_ward
    return ward


def adjudicate(patient):
    """The reportable events of one patient, in the manual's order."""
    admissions = [Admission(a) for a in patient["admissions"]]

    pool = []
    for adm in admissions:
        for kind, anchor, doe, orgs in candidates(adm):
            if doe < adm.admit:
                continue                        # present on admission
            if days(adm.admit, doe) + 1 < HAI_DAY:
                continue                        # admission day 1 or 2
            pool.append({"kind": kind, "anchor": anchor, "doe": doe,
                         "organisms": list(orgs), "adm": adm})

    pool.sort(key=lambda c: (c["doe"], c["anchor"],
                             c["organisms"][0] if c["organisms"] else ""))

    reported = {"UTI": [], "BSI": []}
    open_rit = {"UTI": None, "BSI": None}       # (event, last day inside)

    for kind in ("UTI", "BSI"):
        for cand in [c for c in pool if c["kind"] == kind]:
            if kind == "BSI":
                host = secondary_host(reported["UTI"], cand)
                if host is not None:
                    merge(host, cand["organisms"])
                    continue
            rit = open_rit[kind]
            if rit is not None and cand["doe"] <= rit[1]:
                merge(rit[0], cand["organisms"])
                continue
            event = {"date_of_event": cand["doe"],
                     "ward": attribute(cand["adm"], cand["doe"]),
                     "organisms": sorted(set(cand["organisms"])),
                     # kept for the secondary test: the attribution period runs
                     # from the first day of the candidate's own window
                     "iwp_start": cand["anchor"] - dt.timedelta(days=IWP_RADIUS),
                     # the organisms this event was opened with, before any
                     # merge -- §10 matches against the CURRENT list, not this,
                     # and the difference decides real cases
                     "seed": sorted(set(cand["organisms"]))}
            if kind == "BSI":
                event["central_line_associated"] = \
                    line_associated(cand["adm"], cand["doe"])
            reported[kind].append(event)
            open_rit[kind] = (event,
                              cand["doe"] + dt.timedelta(days=RIT_DAYS - 1))
    return reported


def merge(event, organisms):
    event["organisms"] = sorted(set(event["organisms"]) | set(organisms))


def secondary_host(utis, cand):
    """The reported UTI that demotes this candidate, or None."""
    for uti in utis:
        end = uti["date_of_event"] + dt.timedelta(days=RIT_DAYS - 1)
        if not (uti["iwp_start"] <= cand["anchor"] <= end):
            continue
        if set(cand["organisms"]) & set(uti["organisms"]):
            return uti
    return None


def line_days(doc):
    counts = {w: 0 for w in doc["wards"]}
    lo, hi = d(doc["period_start"]), d(doc["period_end"])
    for patient in doc["patients"]:
        for raw in patient["admissions"]:
            adm = Admission(raw)
            day = adm.admit
            while day <= adm.discharge:
                if lo <= day < hi and adm.line_on(day):
                    _arrive, ward = adm.ward_on(day)
                    if ward is not None:
                        counts[ward] = counts.get(ward, 0) + 1
                day += dt.timedelta(days=1)
    return counts


def solve(doc):
    patients = []
    for patient in doc["patients"]:
        rep = adjudicate(patient)
        patients.append({
            "id": patient["id"],
            "uti": [{"date_of_event": iso(e["date_of_event"]),
                     "ward": e["ward"], "organisms": e["organisms"]}
                    for e in rep["UTI"]],
            "bsi": [{"date_of_event": iso(e["date_of_event"]),
                     "ward": e["ward"], "organisms": e["organisms"],
                     "central_line_associated": e["central_line_associated"]}
                    for e in rep["BSI"]],
        })
    counts = line_days(doc)
    return {"patients": patients,
            "central_line_days": [{"ward": w, "days": counts[w]}
                                  for w in doc["wards"]]}


def main():
    with open(RECORDS_PATH) as f:
        doc = json.load(f)
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(solve(doc), f)
        f.write("\n")
    os.replace(tmp, RESULT_PATH)


if __name__ == "__main__":
    main()
