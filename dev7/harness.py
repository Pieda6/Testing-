"""Run the real verifier against the oracle and against wrong submissions.

Mirrors the container layout in a temp tree: /app/data from environment/,
/app/answer.json written by whatever is under test, and tests/test_outputs.py
imported with RESULT_PATH repointed. Nothing here ships.
"""
import copy
import importlib.util
import json
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(ROOT, "task7")


def load(name, path, result_path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RESULT_PATH = result_path
    return mod


def grade(tests, label):
    for fn in (tests.test_output_schema, tests.test_adjudication_is_correct):
        try:
            fn()
        except Exception as exc:
            print("  %-50s 0   (%s)" % (label, str(exc).splitlines()[0][:92]))
            return 0
    print("  %-50s 1" % label)
    return 1


def main():
    tmp = tempfile.mkdtemp()
    result = os.path.join(tmp, "answer.json")
    tests = load("t7tests", os.path.join(TASK, "tests", "test_outputs.py"),
                 result)
    solver = load("t7solve", os.path.join(TASK, "solution", "solve.py"), result)
    solver.RECORDS_PATH = os.path.join(TASK, "environment", "data",
                                       "records.json")

    def write(obj):
        with open(result, "w") as f:
            json.dump(obj, f)

    print("oracle")
    solver.main()
    with open(result) as f:
        oracle = json.load(f)
    grade(tests, "reference adjudicator")
    solver.main()
    with open(result) as f:
        again = json.load(f)
    print("  %-50s %s" % ("re-run is byte-identical", again == oracle))

    def run(label, mutate):
        obj = mutate(copy.deepcopy(oracle))
        if obj is None:
            if os.path.exists(result):
                os.remove(result)
        else:
            write(obj)
        return grade(tests, label)

    print("empty / adversarial")
    run("no file at all", lambda o: None)
    run("empty object", lambda o: {})
    run("no events reported for anyone",
        lambda o: {"patients": [{"id": p["id"], "uti": [], "bsi": []}
                                for p in o["patients"]],
                   "central_line_days": o["central_line_days"]})
    run("all central line days zero",
        lambda o: {"patients": o["patients"],
                   "central_line_days": [{"ward": r["ward"], "days": 0}
                                         for r in o["central_line_days"]]})

    os.remove(result)
    other = os.path.join(tmp, "elsewhere.json")
    with open(other, "w") as f:
        json.dump(oracle, f)
    os.symlink(other, result)
    grade(tests, "correct answer behind a symlink")
    os.remove(result)

    def first_with(obj, kind):
        for p in obj["patients"]:
            if p[kind]:
                return p
        raise AssertionError("no %s events" % kind)

    print("wrong answers")
    run("one bloodstream event dropped",
        lambda o: (first_with(o, "bsi")["bsi"].pop(0), o)[1])
    run("one urinary event dropped",
        lambda o: (first_with(o, "uti")["uti"].pop(0), o)[1])
    run("one event dated a day late",
        lambda o: (first_with(o, "bsi")["bsi"][0].__setitem__(
            "date_of_event",
            _bump(first_with(o, "bsi")["bsi"][0]["date_of_event"])), o)[1])
    run("one line association flipped",
        lambda o: (first_with(o, "bsi")["bsi"][0].__setitem__(
            "central_line_associated",
            not first_with(o, "bsi")["bsi"][0]["central_line_associated"]),
            o)[1])
    run("one event charged to the wrong ward",
        lambda o: (first_with(o, "bsi")["bsi"][0].__setitem__(
            "ward", _other_ward(o, first_with(o, "bsi")["bsi"][0]["ward"])),
            o)[1])
    run("one organism dropped from a merged list",
        lambda o: _drop_organism(o))
    run("one ward's line days off by one",
        lambda o: (o["central_line_days"][0].__setitem__(
            "days", o["central_line_days"][0]["days"] + 1), o)[1])
    run("patients returned in reverse order",
        lambda o: {"patients": list(reversed(o["patients"])),
                   "central_line_days": o["central_line_days"]})
    run("wards returned in reverse order",
        lambda o: {"patients": o["patients"],
                   "central_line_days": list(reversed(o["central_line_days"]))})
    run("organisms unsorted", _unsort_organisms)
    run("line association sent as 0/1",
        lambda o: {"patients": [dict(p, bsi=[dict(e, central_line_associated=int(
            e["central_line_associated"])) for e in p["bsi"]])
            for p in o["patients"]],
            "central_line_days": o["central_line_days"]})
    run("an extra field on every patient",
        lambda o: {"patients": [dict(p, note="") for p in o["patients"]],
                   "central_line_days": o["central_line_days"]})
    shutil.rmtree(tmp)


def _bump(date):
    import datetime as dt
    return (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()


def _other_ward(obj, ward):
    for row in obj["central_line_days"]:
        if row["ward"] != ward:
            return row["ward"]
    return ward


def _unsort_organisms(obj):
    for p in obj["patients"]:
        for ev in p["uti"] + p["bsi"]:
            if len(ev["organisms"]) > 1:
                ev["organisms"] = list(reversed(ev["organisms"]))
                return obj
    raise AssertionError("no multi-organism event in the key")


def _drop_organism(obj):
    for p in obj["patients"]:
        for ev in p["uti"] + p["bsi"]:
            if len(ev["organisms"]) > 1:
                ev["organisms"] = ev["organisms"][:-1]
                return obj
    raise AssertionError("no merged organism list in the key")


if __name__ == "__main__":
    main()
