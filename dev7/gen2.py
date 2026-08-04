"""Deterministic generator for the redacted-manual version of the task.

Emits two files. audited.json is a prior state audit: patients WITH their
validated adjudications, from which the manual's withheld constants have to be
recovered. records.json is the held-out quarter to adjudicate with them.

Every audit patient below exists to pin one parameter, and is built as a pair
that straddles its boundary -- a sign exactly at the edge of the window and one
a day outside it, a repeat on the last day of the timeframe and one a day past,
a line in place two days and one in place three. dev7/fit.py then proves by
exhaustion that the whole audit set leaves exactly one setting standing.

All patients are synthetic. Nothing here comes from a real person.
"""
import datetime as dt
import hashlib
import json
import os

import params
from params import Params

SEED = b"dynamo/hai-surveillance/v2"
HERE = os.path.dirname(os.path.abspath(__file__))

PERIOD_START = dt.date(2026, 1, 1)
PERIOD_END = dt.date(2026, 4, 1)
WARDS = ["MICU", "SICU", "W3B", "W5A", "W7C"]
PATHOGENS = ["Candida albicans", "Enterobacter cloacae", "Enterococcus faecalis",
             "Escherichia coli", "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
             "Serratia marcescens", "Staphylococcus aureus"]
COMMENSALS = sorted(params.COMMENSALS)


def det_int(counter, nbits=32):
    b = hashlib.sha256(SEED + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def d(s):
    return dt.date.fromisoformat(s)


def iso(x):
    return x.isoformat()


class Adm(object):
    def __init__(self, admit, discharge):
        self.admit, self.discharge = d(admit), d(discharge)
        self.wards, self.lines, self.cultures, self.signs = [], [], [], []

    def w(self, ward, arrive):
        self.wards.append((ward, d(arrive)))
        return self

    def line(self, insert, remove):
        self.lines.append((d(insert), d(remove)))
        return self

    def blood(self, date, *organisms):
        self.cultures.append((d(date), "blood", list(organisms)))
        return self

    def urine(self, date, *organisms):
        self.cultures.append((d(date), "urine", list(organisms)))
        return self

    def sign(self, date, *elements):
        self.signs.append((d(date), list(elements)))
        return self

    def dump(self):
        wards = self.wards or [(WARDS[0], self.admit)]
        return {
            "admit": iso(self.admit), "discharge": iso(self.discharge),
            "wards": [{"ward": w, "arrive": iso(a)}
                      for w, a in sorted(wards, key=lambda x: x[1])],
            "central_lines": [{"insert": iso(i), "remove": iso(r)}
                              for i, r in sorted(self.lines)],
            "cultures": [{"date": iso(t), "source": s, "organisms": sorted(o)}
                         for t, s, o in sorted(self.cultures,
                                               key=lambda x: (x[0], x[1],
                                                              sorted(x[2])))],
            "signs": [{"date": iso(t), "elements": sorted(e)}
                      for t, e in sorted(self.signs)],
        }


def audit_patients():
    """Each entry pins a parameter by straddling its boundary."""
    P = []

    def add(*adms):
        P.append(list(adms))

    # --- the admission-day cut ------------------------------------------
    # event on day 2 (not reported) and, next patient, on day 3 (reported)
    add(Adm("2026-01-05", "2026-01-20").w("W5A", "2026-01-05")
        .blood("2026-01-06", "Escherichia coli"))
    add(Adm("2026-01-05", "2026-01-20").w("W5A", "2026-01-05")
        .blood("2026-01-07", "Escherichia coli"))
    add(Adm("2026-01-05", "2026-01-20").w("W5A", "2026-01-05")
        .blood("2026-01-08", "Klebsiella pneumoniae"))

    # --- how far the window reaches BACK from the culture ---------------
    # sign 3 days before the urine culture qualifies; 4 days before does not
    add(Adm("2026-01-04", "2026-01-24").w("W3B", "2026-01-04")
        .urine("2026-01-14", "Escherichia coli").sign("2026-01-11", "dysuria"))
    add(Adm("2026-01-04", "2026-01-24").w("W3B", "2026-01-04")
        .urine("2026-01-14", "Klebsiella pneumoniae")
        .sign("2026-01-10", "dysuria"))

    # --- and FORWARD -----------------------------------------------------
    add(Adm("2026-01-04", "2026-01-24").w("W5A", "2026-01-04")
        .urine("2026-01-14", "Enterobacter cloacae")
        .sign("2026-01-17", "urgency"))
    add(Adm("2026-01-04", "2026-01-24").w("W5A", "2026-01-04")
        .urine("2026-01-14", "Serratia marcescens")
        .sign("2026-01-18", "urgency"))

    # --- what dates an event: its earliest element, or its culture -------
    add(Adm("2026-01-04", "2026-01-24").w("W7C", "2026-01-04")
        .urine("2026-01-15", "Pseudomonas aeruginosa")
        .sign("2026-01-13", "suprapubic_tenderness"))

    # --- the repeat timeframe, both sides --------------------------------
    add(Adm("2026-01-02", "2026-02-15").w("W5A", "2026-01-02")
        .blood("2026-01-06", "Escherichia coli")
        .blood("2026-01-19", "Candida albicans"))
    add(Adm("2026-01-02", "2026-02-15").w("W5A", "2026-01-02")
        .blood("2026-01-06", "Escherichia coli")
        .blood("2026-01-20", "Candida albicans"))

    # --- which type is adjudicated first ---------------------------------
    # UTI first: the blood culture is secondary and nothing is reported for it.
    # BSI first: no UTI exists yet, so a bloodstream event is reported.
    add(Adm("2026-01-03", "2026-02-03").w("W3B", "2026-01-03")
        .urine("2026-01-16", "Escherichia coli").sign("2026-01-16", "fever")
        .blood("2026-01-12", "Escherichia coli"))

    # --- where the attribution period opens ------------------------------
    # the sign sits two days before the culture, so the window opens one day
    # earlier than the date of event does, and a blood culture drawn in that
    # one-day gap tells the two apart
    add(Adm("2026-01-03", "2026-02-03").w("W5A", "2026-01-03")
        .urine("2026-01-20", "Pseudomonas aeruginosa")
        .sign("2026-01-18", "dysuria")
        .blood("2026-01-17", "Pseudomonas aeruginosa"))

    # --- and how long it runs --------------------------------------------
    add(Adm("2026-01-03", "2026-02-03").w("W3B", "2026-01-03")
        .urine("2026-01-20", "Klebsiella pneumoniae")
        .sign("2026-01-17", "dysuria")
        .blood("2026-02-02", "Klebsiella pneumoniae"))
    add(Adm("2026-01-03", "2026-02-06").w("W3B", "2026-01-03")
        .urine("2026-01-20", "Enterococcus faecalis")
        .sign("2026-01-17", "dysuria")
        .blood("2026-02-03", "Enterococcus faecalis"))

    # --- how long a line must be in place --------------------------------
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .line("2026-01-10", "2026-01-18")
        .blood("2026-01-11", "Staphylococcus aureus"))
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .line("2026-01-10", "2026-01-18")
        .blood("2026-01-12", "Staphylococcus aureus"))

    # --- and how long after removal still counts -------------------------
    add(Adm("2026-01-05", "2026-01-28").w("SICU", "2026-01-05")
        .line("2026-01-08", "2026-01-16")
        .blood("2026-01-17", "Serratia marcescens"))
    add(Adm("2026-01-05", "2026-01-28").w("SICU", "2026-01-05")
        .line("2026-01-08", "2026-01-16")
        .blood("2026-01-18", "Serratia marcescens"))

    # --- how close a transfer sends the event to the other ward ----------
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-14").blood("2026-01-14", "Enterobacter cloacae"))
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-14").blood("2026-01-15", "Enterobacter cloacae"))
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-14").blood("2026-01-16", "Enterobacter cloacae"))

    # --- how far apart two commensal cultures may be drawn ---------------
    add(Adm("2026-01-05", "2026-01-25").w("W7C", "2026-01-05")
        .blood("2026-01-12", "Staphylococcus epidermidis")
        .blood("2026-01-13", "Staphylococcus epidermidis")
        .sign("2026-01-12", "chills"))
    add(Adm("2026-01-05", "2026-01-25").w("W7C", "2026-01-05")
        .blood("2026-01-12", "Micrococcus species")
        .blood("2026-01-14", "Micrococcus species")
        .sign("2026-01-12", "chills"))
    add(Adm("2026-01-05", "2026-01-25").w("W7C", "2026-01-05")
        .blood("2026-01-12", "Corynebacterium species")
        .sign("2026-01-12", "chills"))

    # --- a commensal alongside a pathogen, and a commensal-only urine ----
    add(Adm("2026-01-06", "2026-01-26").w("MICU", "2026-01-06")
        .line("2026-01-06", "2026-01-24")
        .blood("2026-01-12", "Staphylococcus aureus",
               "Staphylococcus epidermidis"))
    add(Adm("2026-01-06", "2026-01-26").w("W3B", "2026-01-06")
        .urine("2026-01-12", "Cutibacterium acnes").sign("2026-01-12", "fever"))

    # --- organisms merging, and a merge that creates a secondary ---------
    add(Adm("2026-01-04", "2026-02-14").w("W3B", "2026-01-04")
        .urine("2026-01-10", "Escherichia coli").sign("2026-01-10", "fever")
        .urine("2026-01-18", "Klebsiella pneumoniae").sign("2026-01-18", "fever")
        .blood("2026-01-19", "Klebsiella pneumoniae"))

    # --- a sign that drags the date of event below the admission cut -----
    add(Adm("2026-01-10", "2026-01-30").w("W5A", "2026-01-10")
        .urine("2026-01-14", "Escherichia coli").sign("2026-01-11", "dysuria"))

    return P


def held_out():
    """The quarter to be adjudicated. Ordinary shapes plus the boundaries the
    recovered constants decide, so a wrong fit is wrong here."""
    P = []

    def add(*adms):
        P.append(list(adms))

    add(Adm("2026-02-02", "2026-02-22").w("MICU", "2026-02-02")
        .line("2026-02-02", "2026-02-14")
        .blood("2026-02-06", "Klebsiella pneumoniae"))
    add(Adm("2026-02-03", "2026-02-18").w("W5A", "2026-02-03")
        .blood("2026-02-04", "Escherichia coli"))
    add(Adm("2026-02-03", "2026-02-18").w("W5A", "2026-02-03")
        .blood("2026-02-05", "Staphylococcus aureus"))
    add(Adm("2026-02-01", "2026-02-26").w("W3B", "2026-02-01")
        .urine("2026-02-12", "Escherichia coli").sign("2026-02-09", "dysuria"))
    add(Adm("2026-02-01", "2026-02-26").w("W3B", "2026-02-01")
        .urine("2026-02-12", "Serratia marcescens")
        .sign("2026-02-08", "dysuria"))
    add(Adm("2026-02-01", "2026-03-14").w("MICU", "2026-02-01")
        .line("2026-02-01", "2026-03-10")
        .blood("2026-02-05", "Escherichia coli")
        .blood("2026-02-18", "Pseudomonas aeruginosa")
        .blood("2026-02-19", "Serratia marcescens"))
    add(Adm("2026-02-02", "2026-03-06").w("W3B", "2026-02-02")
        .urine("2026-02-10", "Escherichia coli").sign("2026-02-09", "dysuria")
        .blood("2026-02-16", "Escherichia coli", "Klebsiella pneumoniae"))
    add(Adm("2026-02-02", "2026-03-06").w("W5A", "2026-02-02")
        .urine("2026-02-11", "Klebsiella pneumoniae")
        .sign("2026-02-11", "fever")
        .blood("2026-02-17", "Staphylococcus aureus"))
    add(Adm("2026-02-04", "2026-02-24").w("MICU", "2026-02-04")
        .w("W7C", "2026-02-13").blood("2026-02-13", "Enterobacter cloacae"))
    add(Adm("2026-02-04", "2026-02-24").w("MICU", "2026-02-04")
        .w("W7C", "2026-02-13").blood("2026-02-14", "Candida albicans"))
    add(Adm("2026-02-04", "2026-02-24").w("MICU", "2026-02-04")
        .w("W7C", "2026-02-13").blood("2026-02-15", "Enterococcus faecalis"))
    add(Adm("2026-02-05", "2026-02-20").w("SICU", "2026-02-05")
        .line("2026-02-08", "2026-02-09")
        .blood("2026-02-09", "Staphylococcus aureus"),
        Adm("2026-03-01", "2026-03-16").w("W5A", "2026-03-01")
        .line("2026-03-01", "2026-03-03")
        .blood("2026-03-03", "Escherichia coli"))
    add(Adm("2026-02-06", "2026-03-10").w("MICU", "2026-02-06")
        .line("2026-02-06", "2026-02-16")
        .blood("2026-02-17", "Klebsiella pneumoniae")
        .blood("2026-03-04", "Serratia marcescens"))
    add(Adm("2026-02-07", "2026-02-27").w("W7C", "2026-02-07")
        .blood("2026-02-14", "Staphylococcus epidermidis")
        .blood("2026-02-15", "Staphylococcus epidermidis")
        .sign("2026-02-12", "fever"))
    add(Adm("2026-02-07", "2026-02-27").w("W7C", "2026-02-07")
        .blood("2026-02-14", "Corynebacterium species")
        .blood("2026-02-16", "Corynebacterium species")
        .sign("2026-02-14", "fever"))
    add(Adm("2026-02-08", "2026-03-18").w("W3B", "2026-02-08")
        .urine("2026-02-14", "Escherichia coli").sign("2026-02-14", "fever")
        .urine("2026-02-22", "Klebsiella pneumoniae")
        .sign("2026-02-22", "fever")
        .blood("2026-02-24", "Klebsiella pneumoniae"))
    add(Adm("2026-02-09", "2026-02-28").w("MICU", "2026-02-09")
        .line("2026-02-09", "2026-02-26")
        .blood("2026-02-15", "Staphylococcus aureus",
               "Staphylococcus epidermidis"))
    add(Adm("2026-02-10", "2026-03-02").w("W5A", "2026-02-10")
        .urine("2026-02-13", "Escherichia coli").sign("2026-02-11", "dysuria"))
    add(Adm("2026-03-20", "2026-04-08").w("W7C", "2026-03-20")
        .line("2026-03-21", "2026-04-06")
        .blood("2026-03-25", "Staphylococcus aureus"))
    add(Adm("2025-12-28", "2026-01-12").w("SICU", "2025-12-28")
        .line("2025-12-29", "2026-01-06")
        .blood("2026-01-02", "Escherichia coli"))

    # deterministic filler for volume
    i = 0
    while len(P) < 30:
        tag = "h%d" % i
        start = dt.date(2026, 2, 1) + dt.timedelta(days=det_int(tag + "s") % 40)
        stay = 10 + det_int(tag + "l") % 20
        a = Adm(iso(start), iso(min(start + dt.timedelta(days=stay),
                                    dt.date(2026, 3, 30))))
        a.w(WARDS[det_int(tag + "w") % len(WARDS)], iso(start))
        if det_int(tag + "c") % 3 != 2:
            ins = start + dt.timedelta(days=det_int(tag + "ci") % 4)
            rem = min(ins + dt.timedelta(days=2 + det_int(tag + "cr") % 12),
                      a.discharge)
            a.line(iso(ins), iso(rem))
        for j in range(1 + det_int(tag + "n") % 2):
            off = 2 + det_int(tag + "d%d" % j) % max(3, stay - 3)
            when = start + dt.timedelta(days=off)
            if when > a.discharge:
                continue
            org = PATHOGENS[det_int(tag + "o%d" % j) % len(PATHOGENS)]
            if det_int(tag + "s%d" % j) % 3 == 0:
                a.urine(iso(when), org)
                a.sign(iso(when - dt.timedelta(days=det_int(tag + "g%d" % j) % 3)),
                       "dysuria")
            else:
                a.blood(iso(when), org)
                a.sign(iso(when), "fever")
        P.append([a])
        i += 1
    return P


def document(patients, prefix):
    return [{"id": "%s-%03d" % (prefix, i + 1),
             "admissions": [a.dump() for a in adms]}
            for i, adms in enumerate(patients)]


def main():
    audit = document(audit_patients(), "AUD")
    heldout = document(held_out(), "PT")

    audit_doc = {
        "period_start": iso(PERIOD_START), "period_end": iso(PERIOD_END),
        "wards": WARDS, "patients": audit,
        "adjudications": [params.report(params.TRUE, p) for p in audit],
    }
    records_doc = {
        "period_start": iso(PERIOD_START), "period_end": iso(PERIOD_END),
        "wards": WARDS, "patients": heldout,
    }
    for name, doc in (("audited.json", audit_doc),
                      ("records.json", records_doc)):
        with open(os.path.join(HERE, name), "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")

    n_ev = sum(len(a["uti"]) + len(a["bsi"])
               for a in audit_doc["adjudications"])
    print("audit patients %d (%d validated events) | held-out patients %d"
          % (len(audit), n_ev, len(heldout)))


if __name__ == "__main__":
    main()
