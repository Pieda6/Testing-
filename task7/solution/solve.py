"""Reference solver for dynamo/hai-surveillance-adjudication.

Reads /app/data/manual.md, /app/data/audited.json and /app/data/records.json,
writes /app/answer.json. Pure standard library, no randomness, no network.

The manual gives the SHAPE of the surveillance definitions and withholds every
constant in them. Twelve values are missing: how far the infection window
reaches back and forward, how long a repeat infection timeframe runs, which
admission day separates present-on-admission from healthcare-associated, which
infection type is adjudicated first, where a secondary attribution period opens
and how long it runs, how many days a central line must be in place, how long
after removal still counts, how close a ward transfer sends an event to the
transferring ward, how far apart two commensal cultures may be drawn, and
whether an event is dated by its earliest element or by its culture.

They are recovered from audited.json -- a prior state audit. Build the procedure
with the constants left free, find the setting the audit supports, apply it to
the held-out quarter.

Three things carry the work.

0. The audit is not clean. A handful of its entries were mis-adjudicated by the
   auditor and which ones is not recorded, so no setting reproduces all of it
   and a search that demands one finds nothing at all. Worse is the search that
   keeps relaxing a constant until the last stubborn entry fits: that lands on
   a setting which explains somebody's slip and is wrong about every held-out
   patient it touches. What is wanted is the setting with the highest
   agreement, plus a check that it wins outright rather than ties.

1. The fit has to be joint, and the audit gives no way to make it separable. No
   two audit patients differ in a single element; each sits on several
   boundaries at once, so widening the window moves the date of event, which
   moves the admission-day test, the transfer test and the timeframe test with
   it. A mismatch says one of several constants is wrong and does not say which,
   so there is no pair to read a value off and no order in which the twelve can
   be settled one at a time. It also means a mistake in this procedure looks
   exactly like a mistake in a constant.

2. The audit has to be read for what it excludes, not only for what it
   contains. A validated adjudication reporting NO event for a patient who has
   a positive culture is what pins the admission-day cut and the edges of the
   window; the patients that do report an event pin far less on their own.

3. Nothing checks the fit on the held-out quarter. A setting that reproduces
   the entire audit and is still wrong -- the timeframe a day long, the window
   a day narrow, the attribution period opening in the wrong place -- produces
   a complete, coherent, plausible adjudication that nothing in the data
   contradicts. That is where this task is decided.

The search is exhaustive over a generous grid, but the grid holds 148,500,000
settings and walking it patient by patient is far outside the budget, so it is
staged and the expensive part is not repeated. Only five of the constants change
which candidates exist at all, so the candidate pools are built once per setting
of those five. Three more affect only the ward and the line flag of an event
that is already decided, so they are tried last and only for settings whose
reported events already match. The adjudication walk is what is left in the
middle. That collapses the work to 1,188,000 pool-and-walk settings, of which
the bound below leaves only a few thousand to score in full.
"""
import collections
import datetime as dt
import itertools
import json
import os

DATA_DIR = "/app/data"
AUDIT_PATH = os.path.join(DATA_DIR, "audited.json")
RECORDS_PATH = os.path.join(DATA_DIR, "records.json")
RESULT_PATH = "/app/answer.json"

Params = collections.namedtuple("Params", [
    "iwp_before", "iwp_after", "commensal_gap", "doe_rule", "hai_day",
    "order", "rit_days", "sec_start", "sec_len",
    "line_min_days", "line_grace", "transfer_window",
])

POOL_FIELDS = ("iwp_before", "iwp_after", "commensal_gap", "doe_rule",
               "hai_day")
WALK_FIELDS = ("order", "rit_days", "sec_start", "sec_len")
TRIM_FIELDS = ("line_min_days", "line_grace", "transfer_window")

GRID = {
    "iwp_before": range(1, 7),
    "iwp_after": range(1, 7),
    "commensal_gap": range(0, 5),
    "doe_rule": ["earliest", "culture"],
    "hai_day": range(2, 7),
    "order": ["UTI", "BSI"],
    "rit_days": range(9, 20),
    "sec_start": ["iwp", "doe"],
    "sec_len": range(10, 25),
    "line_min_days": range(2, 7),
    "line_grace": range(0, 5),
    "transfer_window": range(0, 5),
}

COMMENSALS = frozenset([
    "Bacillus species", "Corynebacterium species", "Cutibacterium acnes",
    "Micrococcus species", "Staphylococcus epidermidis",
])
YEASTS = frozenset(["Candida albicans", "Candida glabrata"])
CONTAM_MIN = 3          # a blood culture growing this many names is disregarded
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


def candidates(p, adm):
    """(type, anchor, date of event, organisms) for one admission."""
    out = []
    before = dt.timedelta(days=p.iwp_before)
    after = dt.timedelta(days=p.iwp_after)
    for date, source, orgs in adm.cultures:
        if source == "blood" and len(set(orgs)) >= CONTAM_MIN:
            continue                      # disregarded as contamination
        found = pathogens(orgs)
        if source == "urine":
            found = [o for o in found if o not in YEASTS]
        if not found:
            continue
        if source == "blood":
            out.append(("BSI", date, date, found))
        else:
            signs = adm.sign_dates(UTI_SIGNS, date - before, date + after)
            if signs:
                doe = date if p.doe_rule == "culture" else min(date, signs[0])
                out.append(("UTI", date, doe, found))

    blood = [(t, commensals(o)) for t, s, o in adm.cultures
             if s == "blood" and len(set(o)) < CONTAM_MIN]
    seen = set()
    for i, (t1, c1) in enumerate(blood):
        for t2, c2 in blood[i + 1:]:
            if abs((t2 - t1).days) > p.commensal_gap:
                continue
            for org in sorted(set(c1) & set(c2)):
                anchor = min(t1, t2)
                if (anchor, org) in seen:
                    continue
                signs = adm.sign_dates(BSI_SIGNS, anchor - before,
                                       anchor + after)
                if signs:
                    seen.add((anchor, org))
                    doe = anchor if p.doe_rule == "culture" \
                        else min(anchor, signs[0])
                    out.append(("BSI", anchor, doe, [org]))
    return out


def build_pool(p, admissions):
    """Candidates surviving the admission-day cut, in adjudication order."""
    pool = []
    for adm in admissions:
        for kind, anchor, doe, orgs in candidates(p, adm):
            if doe < adm.admit or (doe - adm.admit).days + 1 < p.hai_day:
                continue
            pool.append({"kind": kind, "anchor": anchor, "doe": doe,
                         "organisms": list(orgs), "adm": adm})
    pool.sort(key=lambda c: (c["doe"], c["anchor"], c["organisms"][0]))
    return pool


def secondary_host(p, utis, cand):
    for uti in utis:
        start = uti["sec0"] if p.sec_start == "iwp" else uti["doe"]
        end = start + dt.timedelta(days=p.sec_len - 1)
        if start <= cand["anchor"] <= end and \
                set(cand["organisms"]) & set(uti["organisms"]):
            return uti
    return None


def walk(p, pool):
    """Which candidates are reported, and with which organisms."""
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
            ev = {"doe": cand["doe"], "adm": cand["adm"],
                  "organisms": sorted(set(cand["organisms"])),
                  "sec0": cand["anchor"] - dt.timedelta(days=p.iwp_before)}
            reported[kind].append(ev)
            open_rit[kind] = (ev, cand["doe"] +
                              dt.timedelta(days=p.rit_days - 1))
    for kind in ("UTI", "BSI"):
        reported[kind].sort(key=lambda e: e["doe"])
    return reported


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


def dress(p, pid, reported):
    """The reported events in the shipped answer shape."""
    return {
        "id": pid,
        "uti": [{"date_of_event": iso(e["doe"]),
                 "ward": attribute(p, e["adm"], e["doe"]),
                 "organisms": e["organisms"]} for e in reported["UTI"]],
        "bsi": [{"date_of_event": iso(e["doe"]),
                 "ward": attribute(p, e["adm"], e["doe"]),
                 "organisms": e["organisms"],
                 "central_line_associated":
                     line_associated(p, e["adm"], e["doe"])}
                for e in reported["BSI"]],
    }


def report(p, patient):
    admissions = [Admission(a) for a in patient["admissions"]]
    return dress(p, patient["id"], walk(p, build_pool(p, admissions)))


def skeleton(reported):
    """Dates and organisms only -- everything the last three constants cannot
    change. Comparing these first is what keeps the search cheap."""
    return tuple((kind, tuple((iso(e["doe"]), tuple(e["organisms"]))
                              for e in reported[kind]))
                 for kind in ("UTI", "BSI"))


def want_skeleton(a):
    return tuple((kind.upper(),
                  tuple((e["date_of_event"], tuple(e["organisms"]))
                        for e in a[kind]))
                 for kind in ("uti", "bsi"))


def months_of(doc):
    lo, hi = d(doc["period_start"]), d(doc["period_end"])
    out, cur = [], lo.replace(day=1)
    while cur < hi:
        out.append("%04d-%02d" % (cur.year, cur.month))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def tally(reports):
    """(ward, month) -> [urinary events, bloodstream events, of which line-
    associated]. This is all the audit publishes: no patient, no date, no
    organism, only how many of each fell in each ward in each month."""
    cells = {}
    for r in reports:
        for kind in ("uti", "bsi"):
            for e in r[kind]:
                cell = cells.setdefault((e["ward"], e["date_of_event"][:7]),
                                        [0, 0, 0])
                cell[0 if kind == "uti" else 1] += 1
                if kind == "bsi" and e["central_line_associated"]:
                    cell[2] += 1
    return cells


def summary(doc, reports):
    cells = tally(reports)
    return [{"ward": w, "month": m,
             "uti_events": cells.get((w, m), (0, 0, 0))[0],
             "bsi_events": cells.get((w, m), (0, 0, 0))[1],
             "central_line_associated": cells.get((w, m), (0, 0, 0))[2]}
            for w in doc["wards"] for m in months_of(doc)]


def recover(audit, max_wrong=4):
    """The setting of the constants that explains the most of the published
    summary.

    The audit does not publish adjudications. It publishes what a surveillance
    programme publishes: for each ward and each month, how many urinary events,
    how many bloodstream events, and how many of those were line-associated.
    Sixty admissions collapse into forty-five numbers, and that changes the
    problem in two ways.

    A mismatch no longer points anywhere. There is no patient to open, no date
    to compare, no organism list to diff: a cell that is one too high says only
    that something, somewhere in that ward and month, was adjudicated
    differently -- by a wrong constant, or by a rule of this procedure being
    read wrongly, and nothing distinguishes those two. Fitting cannot be turned
    into debugging.

    And a few of the published numbers are wrong. No setting reproduces the
    whole table, so a search demanding one finds nothing; what is wanted is the
    setting matching the most cells, and a check that it wins outright.

    The staging survives because of what each constant can reach. Five decide
    which candidates exist, so pools are built once per setting of those five.
    Four more decide which are reported and when, which fixes the month totals.
    The last three decide only ward and line association, so they cannot change
    a month total -- which gives the bound: a setting whose month totals already
    disagree with the published ones in k places can match at most k fewer
    cells, however its last three constants are chosen, and is skipped whole.
    """
    published = {(c["ward"], c["month"]):
                 (c["uti_events"], c["bsi_events"],
                  c["central_line_associated"]) for c in audit["summary"]}
    keys = sorted(published)
    total = 3 * len(keys)
    months = months_of(audit)
    pub_month = {}
    for i, kind in enumerate(("uti", "bsi")):
        for m in months:
            pub_month[(kind, m)] = sum(v[i] for k, v in published.items()
                                       if k[1] == m)

    order = list(audit["patients"])
    admissions = {pt["id"]: [Admission(a) for a in pt["admissions"]]
                  for pt in order}
    floor = total - max_wrong

    best, found = floor, []
    for pool_combo in itertools.product(*(list(GRID[f]) for f in POOL_FIELDS)):
        base = dict(zip(POOL_FIELDS, pool_combo))
        stub = Params(order="UTI", rit_days=min(GRID["rit_days"]),
                      sec_start="iwp", sec_len=min(GRID["sec_len"]),
                      line_min_days=min(GRID["line_min_days"]), line_grace=0,
                      transfer_window=0, **base)
        pools = {pt["id"]: build_pool(stub, admissions[pt["id"]])
                 for pt in order}

        for walk_combo in itertools.product(*(list(GRID[f])
                                              for f in WALK_FIELDS)):
            mid = dict(base, **dict(zip(WALK_FIELDS, walk_combo)))
            stub2 = Params(line_min_days=min(GRID["line_min_days"]),
                           line_grace=0, transfer_window=0, **mid)
            events, got = [], {}
            for pt in order:
                w = walk(stub2, pools[pt["id"]])
                for kind in ("UTI", "BSI"):
                    for e in w[kind]:
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
                        p = Params(line_min_days=lm, line_grace=lg,
                                   transfer_window=tw, **mid)
                        if agree > best:
                            best, found = agree, [p]
                        elif found:
                            found.append(p)
    assert found, ("no setting matches at least %d of the %d published cells"
                   % (floor, total))
    assert len(found) == 1, ("%d settings each match %d cells; the summary does "
                             "not single one out" % (len(found), best))
    return found[0]


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


def main():
    with open(AUDIT_PATH) as f:
        audit = json.load(f)
    with open(RECORDS_PATH) as f:
        records = json.load(f)

    p = recover(audit)
    counts = line_days(p, records, records["patients"])
    answer = {
        "patients": [report(p, patient) for patient in records["patients"]],
        "central_line_days": [{"ward": w, "days": counts[w]}
                              for w in records["wards"]],
    }
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(answer, f)
        f.write("\n")
    os.replace(tmp, RESULT_PATH)


if __name__ == "__main__":
    main()
