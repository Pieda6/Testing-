"""The adjudication procedure, with every decisive constant left as a parameter.

v1 of this task shipped the manual complete and asked the agent to execute it.
Pass@2 solved it twice at reward 1.0. The two tasks in this repo that cleared
every gate -- dynamo/legacy-tag-forge and dynamo/headerless-pcm-normalize --
share a different shape: the rule itself is withheld, has to be recovered from
examples, and is then applied to held-out cases where nothing can check it.

So the manual now discloses the STRUCTURE of the definitions and withholds the
map. This module is that structure. Everything a surveyor would have to look up
-- how wide the infection window is, how long a repeat timeframe runs, which
admission day separates present-on-admission from healthcare-associated, which
infection type is adjudicated first, how far a secondary attribution period
reaches, how many days a line must be in place, how long after removal still
counts, how close a transfer has to be to send an event to the other ward, how
far apart two commensal cultures may be drawn, and whether an event is dated by
its earliest element or by its culture -- is a free parameter here.

The shipped audit set pins exactly one setting. dev7/fit.py proves that by
exhausting the grid.
"""
import collections
import datetime as dt

Params = collections.namedtuple("Params", [
    "iwp_before",        # days of window before the anchor
    "iwp_after",         # days of window after the anchor
    "rit_days",          # length of the repeat infection timeframe
    "hai_day",           # first admission day that counts as healthcare-associated
    "order",             # "UTI" or "BSI" -- which type is adjudicated first
    "sec_start",         # "iwp" or "doe" -- where the attribution period opens
    "sec_len",           # length of the attribution period from its start
    "line_min_days",     # line day on which association becomes possible
    "line_grace",        # days after removal that still count
    "transfer_window",   # arrival within this many days sends it to the old ward
    "commensal_gap",     # greatest gap between two matching commensal cultures
    "doe_rule",          # "earliest" element, or "culture" date
])

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


def d(s):
    return dt.date.fromisoformat(s)


def iso(x):
    return x.isoformat()


class Admission(object):
    def __init__(self, raw):
        self.admit, self.discharge = d(raw["admit"]), d(raw["discharge"])
        self.wards = sorted((d(w["arrive"]), w["ward"]) for w in raw["wards"])
        self.lines = [(d(l["insert"]), d(l["remove"]))
                      for l in raw["central_lines"]]
        self.cultures = [(d(c["date"]), c["source"], list(c["organisms"]))
                         for c in raw["cultures"]]
        self.signs = {}
        for s in raw["signs"]:
            self.signs.setdefault(d(s["date"]), set()).update(s["elements"])

    def ward_on(self, day):
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
        return sorted(t for t, els in self.signs.items()
                      if lo <= t <= hi and (els & allowed))


def pathogens(organisms):
    return sorted(o for o in organisms if o not in COMMENSALS)


def commensals(organisms):
    return sorted(o for o in organisms if o in COMMENSALS)


def window(p, anchor):
    return (anchor - dt.timedelta(days=p.iwp_before),
            anchor + dt.timedelta(days=p.iwp_after))


def candidates(p, adm):
    """(type, anchor, date of event, organisms) for one admission."""
    out = []
    for date, source, orgs in adm.cultures:
        lo, hi = window(p, date)
        found = pathogens(orgs)
        if not found:
            continue
        if source == "blood":
            out.append(("BSI", date, date, found))
        else:
            signs = adm.sign_dates(UTI_SIGNS, lo, hi)
            if signs:
                doe = date if p.doe_rule == "culture" else min(date, signs[0])
                out.append(("UTI", date, doe, found))

    blood = [(t, commensals(o)) for t, s, o in adm.cultures if s == "blood"]
    seen = set()
    for i, (t1, c1) in enumerate(blood):
        for t2, c2 in blood[i + 1:]:
            if abs((t2 - t1).days) > p.commensal_gap:
                continue
            for org in sorted(set(c1) & set(c2)):
                anchor = min(t1, t2)
                if (anchor, org) in seen:
                    continue
                lo, hi = window(p, anchor)
                signs = adm.sign_dates(BSI_SIGNS, lo, hi)
                if signs:
                    seen.add((anchor, org))
                    doe = anchor if p.doe_rule == "culture" \
                        else min(anchor, signs[0])
                    out.append(("BSI", anchor, doe, [org]))
    return out


def line_associated(p, adm, doe):
    for insert, remove in adm.lines:
        if doe >= insert + dt.timedelta(days=p.line_min_days - 1) and \
                doe <= remove + dt.timedelta(days=p.line_grace):
            return True
    return False


def attribute(p, adm, doe):
    arrive, ward = adm.ward_on(doe)
    if ward is None:
        return None
    if arrive is not None and (doe - arrive).days <= p.transfer_window:
        _pa, prev = adm.ward_on(arrive - dt.timedelta(days=1))
        if prev is not None:
            return prev
    return ward


def adjudicate(p, patient):
    admissions = [Admission(a) for a in patient["admissions"]]
    pool = []
    for adm in admissions:
        for kind, anchor, doe, orgs in candidates(p, adm):
            if doe < adm.admit or (doe - adm.admit).days + 1 < p.hai_day:
                continue
            pool.append({"kind": kind, "anchor": anchor, "doe": doe,
                         "organisms": list(orgs), "adm": adm})
    pool.sort(key=lambda c: (c["doe"], c["anchor"], c["organisms"][0]))

    first = p.order
    second = "BSI" if first == "UTI" else "UTI"
    reported = {"UTI": [], "BSI": []}
    open_rit = {"UTI": None, "BSI": None}

    for kind in (first, second):
        for cand in [c for c in pool if c["kind"] == kind]:
            if kind == "BSI":
                host = secondary_host(p, reported["UTI"], cand)
                if host is not None:
                    host["organisms"] = sorted(set(host["organisms"]) |
                                               set(cand["organisms"]))
                    continue
            rit = open_rit[kind]
            if rit is not None and cand["doe"] <= rit[1]:
                rit[0]["organisms"] = sorted(set(rit[0]["organisms"]) |
                                             set(cand["organisms"]))
                continue
            ev = {"date_of_event": cand["doe"],
                  "ward": attribute(p, cand["adm"], cand["doe"]),
                  "organisms": sorted(set(cand["organisms"])),
                  "sec0": cand["anchor"] - dt.timedelta(days=p.iwp_before)}
            if kind == "BSI":
                ev["central_line_associated"] = \
                    line_associated(p, cand["adm"], cand["doe"])
            reported[kind].append(ev)
            open_rit[kind] = (ev, cand["doe"] +
                              dt.timedelta(days=p.rit_days - 1))
    for kind in ("UTI", "BSI"):
        reported[kind].sort(key=lambda e: e["date_of_event"])
    return reported


def secondary_host(p, utis, cand):
    for uti in utis:
        start = uti["sec0"] if p.sec_start == "iwp" else uti["date_of_event"]
        end = start + dt.timedelta(days=p.sec_len - 1)
        if start <= cand["anchor"] <= end and \
                set(cand["organisms"]) & set(uti["organisms"]):
            return uti
    return None


def line_days(p, doc, patients):
    counts = dict((w, 0) for w in doc["wards"])
    lo, hi = d(doc["period_start"]), d(doc["period_end"])
    for patient in patients:
        for raw in patient["admissions"]:
            adm = Admission(raw)
            day = adm.admit
            while day <= adm.discharge:
                if lo <= day < hi and adm.line_on(day):
                    _a, ward = adm.ward_on(day)
                    if ward:
                        counts[ward] = counts.get(ward, 0) + 1
                day += dt.timedelta(days=1)
    return counts


def report(p, patient):
    """One patient's adjudication in the shipped answer shape."""
    rep = adjudicate(p, patient)
    return {
        "id": patient["id"],
        "uti": [{"date_of_event": iso(e["date_of_event"]), "ward": e["ward"],
                 "organisms": e["organisms"]} for e in rep["UTI"]],
        "bsi": [{"date_of_event": iso(e["date_of_event"]), "ward": e["ward"],
                 "organisms": e["organisms"],
                 "central_line_associated": e["central_line_associated"]}
                for e in rep["BSI"]],
    }


TRUE = Params(iwp_before=3, iwp_after=3, rit_days=14, hai_day=3, order="UTI",
              sec_start="iwp", sec_len=17, line_min_days=3, line_grace=1,
              transfer_window=1, commensal_gap=1, doe_rule="earliest")
