"""Run the real verifier against the oracle and against wrong submissions.

Mirrors the container layout in a temp tree: /app/data/jobs.json from
environment/, /app/answer.json written by whatever is under test, and
tests/test_outputs.py imported with RESULT_PATH repointed. Nothing here ships.
"""
import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(ROOT, "task6")


def load(name, path, result_path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RESULT_PATH = result_path
    return mod


def grade(tests, label):
    for fn in (tests.test_output_schema, tests.test_predicted_firings_are_exact):
        try:
            fn()
        except Exception as exc:
            msg = str(exc).splitlines()[0][:96]
            print("  %-52s 0   (%s)" % (label, msg))
            return 0
    print("  %-52s 1" % label)
    return 1


def main():
    tmp = tempfile.mkdtemp()
    result = os.path.join(tmp, "answer.json")
    tests = load("t6tests", os.path.join(TASK, "tests", "test_outputs.py"), result)
    solver = load("t6solve", os.path.join(TASK, "solution", "solve.py"), result)
    solver.DATA_PATH = os.path.join(TASK, "environment", "data", "jobs.json")

    def write(obj):
        with open(result, "w") as f:
            json.dump(obj, f)

    def run(label, mutate=None):
        obj = copy.deepcopy(ORACLE)
        if mutate:
            obj = mutate(obj)
        if obj is None:
            if os.path.exists(result):
                os.remove(result)
        else:
            write(obj)
        return grade(tests, label)

    print("oracle")
    solver.main()
    with open(result) as f:
        ORACLE = json.load(f)
    grade(tests, "reference solver")
    solver.main()                                   # determinism: run it twice
    with open(result) as f:
        again = json.load(f)
    print("  %-52s %s" % ("re-run is byte-identical", again == ORACLE))

    print("empty / adversarial")
    run("no file at all", lambda o: None)
    run("empty object", lambda o: {})
    run("empty schedules array", lambda o: {"schedules": []})
    run("every job predicted silent",
        lambda o: {"schedules": [{"id": e["id"], "fires": []}
                                 for e in o["schedules"]]})

    os.remove(result)
    other = os.path.join(tmp, "elsewhere.json")
    write_target = {"schedules": ORACLE["schedules"]}
    with open(other, "w") as f:
        json.dump(write_target, f)
    os.symlink(other, result)
    grade(tests, "correct answer behind a symlink")
    os.remove(result)

    print("wrong answers")
    run("one instant dropped from one job",
        lambda o: (o["schedules"][7]["fires"].pop(3), o)[1])
    run("one instant added to one job",
        lambda o: (o["schedules"][2]["fires"].insert(0, "2026-02-01T00:00:00Z"),
                   o)[1])
    def bump(o, k, i, minutes):
        import datetime as dt
        f = o["schedules"][k]["fires"]
        t = dt.datetime.strptime(f[i], "%Y-%m-%dT%H:%M:%SZ")
        f[i] = (t + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        f.sort()
        return o

    run("one instant one minute late", lambda o: bump(o, 11, 0, 1))
    run("one instant an hour early", lambda o: bump(o, 4, 5, -60))
    run("one instant a day late", lambda o: bump(o, 20, 2, 1440))
    run("job order reversed",
        lambda o: {"schedules": list(reversed(o["schedules"]))})
    run("instants descending",
        lambda o: {"schedules": [{"id": e["id"],
                                  "fires": list(reversed(e["fires"]))}
                                 for e in o["schedules"]]})
    run("ids renumbered",
        lambda o: {"schedules": [{"id": "JOB-%03d" % (i + 1), "fires": e["fires"]}
                                 for i, e in enumerate(
                                     reversed(o["schedules"]))]})
    run("extra field per entry",
        lambda o: {"schedules": [dict(e, cron="* * * * *")
                                 for e in o["schedules"]]})
    run("instants without the trailing Z",
        lambda o: {"schedules": [{"id": e["id"],
                                  "fires": [t[:-1] for t in e["fires"]]}
                                 for e in o["schedules"]]})
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
