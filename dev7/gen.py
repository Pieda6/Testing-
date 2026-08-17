"""Deterministic input generator for the HAI-surveillance-adjudication task.

Fixed seed => byte-identical output on every run and platform. All randomness
comes from SHA-256 of a fixed seed plus a counter; no PRNG library is involved.

Every patient is synthetic. There are no real records, no real identifiers and
nothing derived from a real person.

Unlike a task where the answer is under-determined and has to be shown unique,
the manual in task7/environment/data/manual.md specifies a deterministic
procedure, so the answer is a function of this data. What has to be established
is that the function is implemented right, which is why there are two
independent adjudicators (task7/solution/solve.py and dev7/brute.py) and
dev7/validate.py compares them.

The first twenty-one patients are hand-placed so that every boundary in the
manual is actually exercised -- the day-3 cut, both sides of the 14-day
timeframe, a line in place exactly two days versus three, the day after
removal, all three transfer positions, a date of event dragged before the admit
date by a sign, a secondary bloodstream infection that is only secondary
because of an organism merged in by an earlier suppression. The rest are filled
in deterministically to add volume and incidental interaction.
"""
import datetime as dt
import hashlib
import json
import os

SEED = b"dynamo/hai-surveillance/v1"
HERE = os.path.dirname(os.path.abspath(__file__))

PERIOD_START = dt.date(2026, 1, 1)
PERIOD_END = dt.date(2026, 4, 1)                 # exclusive

WARDS = ["MICU", "SICU", "W3B", "W5A", "W7C"]

COMMENSALS = [
    "Bacillus species",
    "Corynebacterium species",
    "Cutibacterium acnes",
    "Micrococcus species",
    "Staphylococcus epidermidis",
]
PATHOGENS = [
    "Candida albicans",
    "Enterobacter cloacae",
    "Enterococcus faecalis",
    "Escherichia coli",
    "Klebsiella pneumoniae",
    "Pseudomonas aeruginosa",
    "Serratia marcescens",
    "Staphylococcus aureus",
]
BSI_SIGNS = ["fever", "chills", "hypotension"]
UTI_SIGNS = ["fever", "dysuria", "urgency", "suprapubic_tenderness",
             "costovertebral_tenderness"]


def det_int(counter, nbits=32):
    b = hashlib.sha256(SEED + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def d(s):
    return dt.date.fromisoformat(s)


def iso(x):
    return x.isoformat()


class Adm(object):
    """One admission, built up with a tiny DSL so the scenarios stay readable."""

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
            "admit": iso(self.admit),
            "discharge": iso(self.discharge),
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


def scenarios():
    """(patient id, [Adm, ...]) with every manual boundary represented."""
    P = []

    def add(*adms):
        P.append(list(adms))

    # 1  plain healthcare-associated BSI-P on day 5, line covers it -> CLABSI
    add(Adm("2026-01-05", "2026-01-20").w("MICU", "2026-01-05")
        .line("2026-01-05", "2026-01-14")
        .blood("2026-01-09", "Klebsiella pneumoniae"))

    # 2  date of event on admission day 2 -> present on admission, not reported
    add(Adm("2026-01-06", "2026-01-18").w("W5A", "2026-01-06")
        .blood("2026-01-07", "Escherichia coli"))

    # 3  day-3 boundary: reportable, and no line at all
    add(Adm("2026-01-10", "2026-01-25").w("W5A", "2026-01-10")
        .blood("2026-01-12", "Staphylococcus aureus"))

    # 4  a lone commensal, and a commensal pair two days apart -> nothing
    add(Adm("2026-01-04", "2026-01-24").w("W3B", "2026-01-04")
        .blood("2026-01-08", "Staphylococcus epidermidis")
        .blood("2026-01-14", "Micrococcus species")
        .blood("2026-01-16", "Micrococcus species")
        .sign("2026-01-08", "fever").sign("2026-01-14", "fever"))

    # 5  commensal pair on consecutive days; the sign drags the date of event
    #    earlier than either culture
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .line("2026-01-06", "2026-01-20")
        .blood("2026-01-12", "Staphylococcus epidermidis")
        .blood("2026-01-13", "Staphylococcus epidermidis")
        .sign("2026-01-10", "fever"))

    # 6  commensal pair, qualifying sign outside the infection window period
    add(Adm("2026-01-07", "2026-01-27").w("W5A", "2026-01-07")
        .blood("2026-01-14", "Corynebacterium species")
        .blood("2026-01-15", "Corynebacterium species")
        .sign("2026-01-09", "fever"))

    # 7  two consecutive commensal cultures that do not match by name
    add(Adm("2026-01-08", "2026-01-26").w("W7C", "2026-01-08")
        .blood("2026-01-12", "Staphylococcus epidermidis")
        .blood("2026-01-13", "Micrococcus species")
        .sign("2026-01-12", "fever"))

    # 8  timeframe merge, then a new event one day after it closes
    add(Adm("2026-01-05", "2026-02-05").w("MICU", "2026-01-05")
        .line("2026-01-05", "2026-02-01")
        .blood("2026-01-08", "Escherichia coli")
        .blood("2026-01-14", "Pseudomonas aeruginosa")
        .blood("2026-01-22", "Serratia marcescens"))

    # 9  the other side of the same boundary: day 14 is still inside
    add(Adm("2026-01-06", "2026-02-10").w("W5A", "2026-01-06")
        .blood("2026-01-10", "Enterococcus faecalis")
        .blood("2026-01-23", "Candida albicans"))

    # 10 secondary bloodstream infection; its second organism joins the UTI
    add(Adm("2026-01-08", "2026-02-08").w("W3B", "2026-01-08")
        .urine("2026-01-14", "Escherichia coli").sign("2026-01-13", "dysuria")
        .blood("2026-01-20", "Escherichia coli", "Klebsiella pneumoniae"))

    # 11 inside the attribution period but no organism in common -> primary
    add(Adm("2026-01-09", "2026-02-09").w("W5A", "2026-01-09")
        .urine("2026-01-15", "Klebsiella pneumoniae").sign("2026-01-15", "fever")
        .blood("2026-01-20", "Staphylococcus aureus"))

    # 12 organism matches but the anchor is one day past the attribution period
    add(Adm("2026-01-10", "2026-02-20").w("W3B", "2026-01-10")
        .urine("2026-01-16", "Enterobacter cloacae").sign("2026-01-16", "urgency")
        .blood("2026-01-30", "Enterobacter cloacae"))

    # 13 transfer on the date of event -> the transferring ward
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-12").blood("2026-01-12", "Klebsiella pneumoniae"))

    # 14 transfer the day before the date of event -> still the transferring ward
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-12").blood("2026-01-13", "Pseudomonas aeruginosa"))

    # 15 transfer two days before -> the ward occupied on the date of event
    add(Adm("2026-01-05", "2026-01-25").w("MICU", "2026-01-05")
        .w("W5A", "2026-01-12").blood("2026-01-14", "Serratia marcescens"))

    # 16 a line in place exactly two days, then a second admission with three
    add(Adm("2026-01-05", "2026-01-15").w("MICU", "2026-01-05")
        .line("2026-01-08", "2026-01-09")
        .blood("2026-01-09", "Staphylococcus aureus"),
        Adm("2026-02-01", "2026-02-15").w("W5A", "2026-02-01")
        .line("2026-02-01", "2026-02-03")
        .blood("2026-02-03", "Escherichia coli"))

    # 17 the day after removal counts; two days after does not
    add(Adm("2026-01-05", "2026-02-10").w("MICU", "2026-01-05")
        .line("2026-01-05", "2026-01-15")
        .blood("2026-01-16", "Klebsiella pneumoniae")
        .blood("2026-01-31", "Serratia marcescens"))

    # 18 a sign inside the window drags the date of event onto admission day 2
    add(Adm("2026-01-10", "2026-01-30").w("W5A", "2026-01-10")
        .urine("2026-01-13", "Escherichia coli").sign("2026-01-11", "dysuria"))

    # 19 a suppressed UTI adds an organism, and that organism is what makes a
    #    later blood culture secondary
    add(Adm("2026-01-06", "2026-02-16").w("W3B", "2026-01-06")
        .urine("2026-01-12", "Escherichia coli").sign("2026-01-12", "fever")
        .urine("2026-01-20", "Klebsiella pneumoniae").sign("2026-01-20", "fever")
        .blood("2026-01-22", "Klebsiella pneumoniae"))

    # 20 a commensal riding along on a pathogen culture is not an organism of
    #    the bloodstream event
    add(Adm("2026-01-08", "2026-01-28").w("MICU", "2026-01-08")
        .line("2026-01-08", "2026-01-25")
        .blood("2026-01-13", "Staphylococcus aureus",
               "Staphylococcus epidermidis"))

    # 21 a urine culture growing only a commensal is not a candidate
    add(Adm("2026-01-09", "2026-01-29").w("W7C", "2026-01-09")
        .urine("2026-01-14", "Corynebacterium species")
        .sign("2026-01-14", "fever"))

    # 22 an admission running past the end of the reporting period: the line
    #    days after it are not counted, though the event itself is reportable
    add(Adm("2026-03-25", "2026-04-10").w("W7C", "2026-03-25")
        .line("2026-03-26", "2026-04-08")
        .blood("2026-03-29", "Staphylococcus aureus"))

    # 23 and one that began before it, for the other side of the same clip
    add(Adm("2025-12-28", "2026-01-10").w("SICU", "2025-12-28")
        .line("2025-12-29", "2026-01-05")
        .blood("2026-01-02", "Escherichia coli"))

    return P


def filler(n_from, n_to):
    """Extra patients from the same vocabulary, for volume and incidental
    interaction. Shapes are ordinary; the boundaries live in scenarios()."""
    out = []
    for k in range(n_from, n_to + 1):
        tag = "f%d" % k
        start = PERIOD_START + dt.timedelta(days=det_int(tag + "s") % 40)
        stay = 12 + det_int(tag + "l") % 30
        a = Adm(iso(start), iso(min(start + dt.timedelta(days=stay),
                                    PERIOD_END - dt.timedelta(days=1))))
        a.w(WARDS[det_int(tag + "w") % len(WARDS)], iso(start))
        if det_int(tag + "w2") % 3 == 0:
            mid = start + dt.timedelta(days=3 + det_int(tag + "wm") % 8)
            if mid < a.discharge:
                a.w(WARDS[det_int(tag + "w3") % len(WARDS)], iso(mid))
        if det_int(tag + "c") % 3 != 2:
            ins = start + dt.timedelta(days=det_int(tag + "ci") % 5)
            rem = min(ins + dt.timedelta(days=2 + det_int(tag + "cr") % 14),
                      a.discharge)
            a.line(iso(ins), iso(rem))
        for j in range(1 + det_int(tag + "n") % 3):
            off = 2 + det_int(tag + "d%d" % j) % max(3, stay - 3)
            when = start + dt.timedelta(days=off)
            if when > a.discharge:
                continue
            src = "urine" if det_int(tag + "s%d" % j) % 3 == 0 else "blood"
            org = PATHOGENS[det_int(tag + "o%d" % j) % len(PATHOGENS)]
            if src == "blood" and det_int(tag + "cm%d" % j) % 5 == 0:
                com = COMMENSALS[det_int(tag + "k%d" % j) % len(COMMENSALS)]
                a.blood(iso(when), com)
                a.blood(iso(when + dt.timedelta(days=1)), com)
            else:
                if src == "blood":
                    a.blood(iso(when), org)
                else:
                    a.urine(iso(when), org)
            pool = UTI_SIGNS if src == "urine" else BSI_SIGNS
            sd = when - dt.timedelta(days=det_int(tag + "g%d" % j) % 3)
            a.sign(iso(sd), pool[det_int(tag + "e%d" % j) % len(pool)])
        out.append([a])
    return out


def main():
    patients = scenarios() + filler(24, 36)
    doc = {
        "period_start": iso(PERIOD_START),
        "period_end": iso(PERIOD_END),
        "wards": WARDS,
        "patients": [{"id": "PT-%03d" % (i + 1),
                      "admissions": [a.dump() for a in adms]}
                     for i, adms in enumerate(patients)],
    }
    path = os.path.join(HERE, "records.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")

    n_cx = sum(len(a["cultures"]) for p in doc["patients"]
               for a in p["admissions"])
    n_adm = sum(len(p["admissions"]) for p in doc["patients"])
    print("patients %d | admissions %d | cultures %d | bytes %d"
          % (len(doc["patients"]), n_adm, n_cx, os.path.getsize(path)))


if __name__ == "__main__":
    main()
