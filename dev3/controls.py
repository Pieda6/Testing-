"""Control battery for dynamo/exec-calendar-triage.

Runs the REAL verifier (task4/tests/test_outputs.py, via pytest) against a set of
deliberately wrong submissions, so the reward numbers quoted in task.toml are
measured rather than assumed.

The first control is the oracle itself. If that does not score 1.0 the harness is
broken and every other number it prints is meaningless, so it is checked first
and hard-fails the run.
"""
import json
import os
import shutil
import subprocess
import sys

TESTS = "/home/user/Testing-/task4/tests"
DATA = "/home/user/Testing-/task4/environment/data"
OUT = "/app/schedule.json"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutations as M  # noqa: E402


def expected():
    with open(os.path.join(TESTS, "expected.json")) as f:
        return json.load(f)["schedule"]


def reward(rows, symlink=False, missing=False):
    """Write rows to /app/schedule.json and return the verifier's reward."""
    os.makedirs("/app", exist_ok=True)
    for p in (OUT, OUT + ".real"):
        if os.path.islink(p) or os.path.exists(p):
            os.remove(p)
    if not missing:
        if symlink:
            with open(OUT + ".real", "w") as f:
                json.dump({"schedule": rows}, f)
            os.symlink(OUT + ".real", OUT)
        else:
            with open(OUT, "w") as f:
                json.dump({"schedule": rows}, f)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", os.path.join(TESTS, "test_outputs.py"),
         "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True)
    return 1 if r.returncode == 0 else 0


def controls():
    exp = expected()
    out = [("oracle", exp)]

    base, _ = None, None
    for name, kw in M.MUTATIONS:
        greedy = kw.pop("_greedy", False)
        rows = M.run(DATA, candidates=1) if greedy else M.run(DATA, **kw)
        out.append(("policy: " + name, rows))
    for name, order in M.ORDER_MUTATIONS:
        out.append(("policy: " + name, M.run(DATA, order=order)))

    # Near misses and schema abuse.
    one = [dict(r) for r in exp]
    for r in one:
        if r["status"] == "scheduled":
            r["start_utc"] = r["start_utc"].replace("T", "T", 1)
            hh = int(r["start_utc"][11:13])
            r["start_utc"] = "%s%02d%s" % (r["start_utc"][:11], (hh + 1) % 24,
                                           r["start_utc"][13:])
            break
    out.append(("one request shifted an hour", one))

    rev_att = [dict(r, attendees=list(reversed(r["attendees"]))) for r in exp]
    out.append(("attendee lists reversed", rev_att))
    out.append(("array reversed", list(reversed([dict(r) for r in exp]))))
    out.append(("one entry dropped", [dict(r) for r in exp[:-1]]))
    out.append(("+00:00 instead of Z",
                [dict(r, start_utc=r["start_utc"].replace("Z", "+00:00"))
                 for r in exp]))
    out.append(("everything declined",
                [{"id": r["id"], "status": "declined", "day": "",
                  "start_utc": "", "attendees": []} for r in exp]))
    return out


def main():
    rows = controls()
    print("%-40s %s" % ("CONTROL", "REWARD"))
    ok = True
    for i, (name, sched) in enumerate(rows):
        r = reward(sched)
        if i == 0:
            if r != 1:
                print("%-40s %d   <-- ORACLE FAILED, numbers below are void"
                      % (name, r))
                return 1
        elif r != 0:
            ok = False
            print("%-40s %d   <-- SHOULD BE 0" % (name, r))
            continue
        print("%-40s %d" % (name, r))

    print("%-40s %d" % ("symlinked output path", reward(expected(), symlink=True)))
    print("%-40s %d" % ("nop (no file written)", reward([], missing=True)))
    print("%-40s %d" % ("oracle again (stability)", reward(expected())))
    shutil.rmtree("/app", ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
