"""Independent adjudicator, written to disagree if either of us is wrong.

Shares no code with task7/solution/solve.py and is built the other way round:
where the reference works with date intervals and a candidate pool, this one
expands every admission into explicit per-calendar-day tables (which ward, is a
line in place, which signs) and then walks days. The rules were re-derived from
manual.md rather than transcribed from the reference.

If both agree on all 36 patients, the answer key is worth trusting. If they
disagree, at least one is wrong and the manual gets re-read.
"""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

COMMENSAL_LIST = ["Bacillus species", "Corynebacterium species",
                  "Cutibacterium acnes", "Micrococcus species",
                  "Staphylococcus epidermidis"]
SIGNS_FOR_BLOOD = ["chills", "fever", "hypotension"]
SIGNS_FOR_URINE = ["costovertebral_tenderness", "dysuria", "fever",
                   "suprapubic_tenderness", "urgency"]


def dd(s):
    y, m, day = (int(x) for x in s.split("-"))
    return dt.date(y, m, day)


def span(a, b):
    """Every calendar day from a to b inclusive."""
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def expand(raw):
    """Per-day tables for one admission."""
    admit, disch = dd(raw["admit"]), dd(raw["discharge"])
    allday = span(admit, disch)

    arrivals = sorted((dd(w["arrive"]), w["ward"]) for w in raw["wards"])
    ward_of, arrived_on, cur, cur_arr = {}, {}, None, None
    for day in allday:
        for a, w in arrivals:
            if a == day:
                cur, cur_arr = w, a
        if cur is None and arrivals:
            cur, cur_arr = arrivals[0][1], arrivals[0][0]
        ward_of[day] = cur
        arrived_on[day] = cur_arr

    lined = set()
    for l in raw["central_lines"]:
        for day in span(dd(l["insert"]), dd(l["remove"])):
            lined.add(day)

    sign_on = {}
    for s in raw["signs"]:
        sign_on.setdefault(dd(s["date"]), set()).update(s["elements"])

    return {"admit": admit, "discharge": disch, "days": allday,
            "ward_of": ward_of, "arrived_on": arrived_on, "lined": lined,
            "sign_on": sign_on, "lines": [(dd(l["insert"]), dd(l["remove"]))
                                          for l in raw["central_lines"]],
            "cultures": raw["cultures"]}


def window(anchor):
    return span(anchor - dt.timedelta(days=3), anchor + dt.timedelta(days=3))


def earliest_sign(tab, anchor, wanted):
    hits = [day for day in window(anchor)
            if wanted & tab["sign_on"].get(day, set())]
    return min(hits) if hits else None


def gather(tab):
    """Candidates as dicts; deliberately built by scanning, not by pairing."""
    out = []
    commensal = set(COMMENSAL_LIST)
    blood_sign = set(SIGNS_FOR_BLOOD)
    urine_sign = set(SIGNS_FOR_URINE)

    for c in tab["cultures"]:
        day, src = dd(c["date"]), c["source"]
        real = sorted(o for o in c["organisms"] if o not in commensal)
        if src == "blood" and real:
            out.append({"kind": "BSI", "anchor": day, "doe": day,
                        "organisms": real})
        if src == "urine" and real:
            first = earliest_sign(tab, day, urine_sign)
            if first is not None:
                out.append({"kind": "UTI", "anchor": day,
                            "doe": min(day, first), "organisms": real})

    # every ordered pair of blood cultures at most one day apart, by commensal
    bloods = [(dd(c["date"]), set(o for o in c["organisms"] if o in commensal))
              for c in tab["cultures"] if c["source"] == "blood"]
    made = set()
    for a in range(len(bloods)):
        for b in range(len(bloods)):
            if a == b:
                continue
            t1, o1 = bloods[a]
            t2, o2 = bloods[b]
            if abs((t2 - t1).days) > 1:
                continue
            anchor = t1 if t1 <= t2 else t2
            for org in sorted(o1 & o2):
                if (anchor, org) in made:
                    continue
                first = earliest_sign(tab, anchor, blood_sign)
                if first is None:
                    continue
                made.add((anchor, org))
                out.append({"kind": "BSI", "anchor": anchor,
                            "doe": min(anchor, first), "organisms": [org]})
    return out


def charged_ward(tab, doe):
    arrived = tab["arrived_on"].get(doe)
    if arrived is None:
        return None
    if (doe - arrived).days <= 1:
        before = arrived - dt.timedelta(days=1)
        if before in tab["ward_of"]:
            return tab["ward_of"][before]
    return tab["ward_of"][doe]


def clabsi(tab, doe):
    for insert, remove in tab["lines"]:
        line_day = (doe - insert).days + 1
        if line_day >= 3 and doe <= remove + dt.timedelta(days=1):
            return True
    return False


def one_patient(patient):
    tabs = [expand(a) for a in patient["admissions"]]
    pool = []
    for tab in tabs:
        for cand in gather(tab):
            admday = (cand["doe"] - tab["admit"]).days + 1
            if admday < 3:
                continue
            cand["tab"] = tab
            pool.append(cand)
    pool.sort(key=lambda c: (c["doe"], c["anchor"], c["organisms"][0]))

    utis, bsis = [], []
    rit = {"UTI": None, "BSI": None}

    for kind, sink in (("UTI", utis), ("BSI", bsis)):
        for cand in [c for c in pool if c["kind"] == kind]:
            if kind == "BSI":
                host = None
                for u in utis:
                    start = u["iwp0"]
                    stop = u["doe"] + dt.timedelta(days=13)
                    if start <= cand["anchor"] <= stop and \
                            set(cand["organisms"]) & set(u["organisms"]):
                        host = u
                        break
                if host is not None:
                    host["organisms"] = sorted(set(host["organisms"]) |
                                               set(cand["organisms"]))
                    continue
            if rit[kind] is not None and \
                    cand["doe"] <= rit[kind]["doe"] + dt.timedelta(days=13):
                held = rit[kind]
                held["organisms"] = sorted(set(held["organisms"]) |
                                           set(cand["organisms"]))
                continue
            ev = {"doe": cand["doe"], "organisms": sorted(set(cand["organisms"])),
                  "ward": charged_ward(cand["tab"], cand["doe"]),
                  "iwp0": cand["anchor"] - dt.timedelta(days=3)}
            if kind == "BSI":
                ev["cla"] = clabsi(cand["tab"], cand["doe"])
            sink.append(ev)
            rit[kind] = ev
    return utis, bsis


def solve(doc):
    lo, hi = dd(doc["period_start"]), dd(doc["period_end"])
    tally = dict((w, 0) for w in doc["wards"])
    patients = []
    for patient in doc["patients"]:
        utis, bsis = one_patient(patient)
        patients.append({
            "id": patient["id"],
            "uti": [{"date_of_event": e["doe"].isoformat(), "ward": e["ward"],
                     "organisms": e["organisms"]} for e in utis],
            "bsi": [{"date_of_event": e["doe"].isoformat(), "ward": e["ward"],
                     "organisms": e["organisms"],
                     "central_line_associated": e["cla"]} for e in bsis],
        })
        for raw in patient["admissions"]:
            tab = expand(raw)
            for day in tab["days"]:
                if lo <= day < hi and day in tab["lined"] \
                        and tab["ward_of"][day]:
                    tally[tab["ward_of"][day]] += 1
    return {"patients": patients,
            "central_line_days": [{"ward": w, "days": tally[w]}
                                  for w in doc["wards"]]}


if __name__ == "__main__":
    with open(os.path.join(HERE, "records.json")) as f:
        print(json.dumps(solve(json.load(f))))
