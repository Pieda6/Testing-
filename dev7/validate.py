"""Compare the two independent adjudicators, patient by patient.

The manual specifies a deterministic procedure, so there is no ambiguity to
prove away -- what has to be established is that the procedure is implemented
correctly. Two implementations written the other way round agreeing on every
patient is the evidence for that. Any disagreement means at least one is wrong
and the manual gets re-read; it is never resolved by picking a side.

Also reports how much of each boundary the shipped data actually exercises, so
the difficulty is measured rather than assumed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "task7", "solution"))
import brute                                     # noqa: E402
import solve as ref                              # noqa: E402

ref.RECORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "records.json")

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "records.json")) as f:
        doc = json.load(f)

    a = ref.solve(doc)
    b = brute.solve(doc)

    bad = 0
    for pa, pb in zip(a["patients"], b["patients"]):
        if pa != pb:
            print("DISAGREEMENT %s\n  reference %s\n  independent %s"
                  % (pa["id"], json.dumps(pa), json.dumps(pb)))
            bad += 1
    if a["central_line_days"] != b["central_line_days"]:
        print("DISAGREEMENT on central line days\n  reference %s\n  independent %s"
              % (a["central_line_days"], b["central_line_days"]))
        bad += 1

    n_uti = sum(len(p["uti"]) for p in a["patients"])
    n_bsi = sum(len(p["bsi"]) for p in a["patients"])
    n_cla = sum(1 for p in a["patients"] for e in p["bsi"]
                if e["central_line_associated"])
    silent = [p["id"] for p in a["patients"] if not p["uti"] and not p["bsi"]]
    multi = [p["id"] for p in a["patients"] if len(p["uti"]) + len(p["bsi"]) > 1]
    merged = [p["id"] for p in a["patients"]
              for e in p["uti"] + p["bsi"] if len(e["organisms"]) > 1]

    print("patients %d | UTI %d | BSI %d (line-associated %d) | line-days %d"
          % (len(a["patients"]), n_uti, n_bsi, n_cla,
             sum(x["days"] for x in a["central_line_days"])))
    print("patients with nothing reportable %d | with more than one event %d | "
          "events carrying a merged organism %d"
          % (len(silent), len(multi), len(merged)))
    print("disagreements: %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
