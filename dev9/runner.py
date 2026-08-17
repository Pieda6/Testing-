"""Stage a candidate mpmc_ring.cpp the way the container does and grade it.

The layout is the container's: /app is the agent's tree, /tests is the overlay
mounted at verify time, /logs/verifier is where the reward lands. The entrypoint
under test is the one that ships, so what is measured here is exactly what the
Dynamo validate and trial stages measure.
"""
import io
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.join(HERE, "..", "task9")
REFERENCE = os.path.join(TASK, "solution", "mpmc_ring.cpp")
SHIPPED = os.path.join(TASK, "environment", "app", "src", "mpmc_ring.cpp")

_FAILED = re.compile(r"^FAILED .*test_mpmc_behavior\[(s\d+)-", re.M)
_PASSED = re.compile(r"^PASSED .*test_mpmc_behavior\[(s\d+)-", re.M)


def read(path):
    return io.open(path, encoding="utf-8").read()


def stage(source):
    """Lay down /app and /tests, with `source` as the graded artifact."""
    for path in ("/app", "/tests"):
        if os.path.exists(path):
            shutil.rmtree(path)
    os.makedirs("/app/src")
    os.makedirs("/app/include")
    os.makedirs("/tests")
    shutil.copy2(os.path.join(TASK, "environment", "app", "MPMC_SPEC.md"),
                 "/app/MPMC_SPEC.md")
    shutil.copy2(os.path.join(TASK, "environment", "app", "include",
                              "mpmc_ring.h"), "/app/include/mpmc_ring.h")
    io.open("/app/src/mpmc_ring.cpp", "w", encoding="utf-8").write(source)
    for name in ("test.sh", "pytest.ini", "test_outputs.py"):
        src = os.path.join(TASK, "tests", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join("/tests", name))
    os.chmod("/tests/test.sh", 0o755)


def grade(source):
    """Return (reward, passed scenarios, failed scenarios, raw output)."""
    stage(source)
    if os.path.exists("/logs/verifier/reward.txt"):
        os.remove("/logs/verifier/reward.txt")
    proc = subprocess.run(["bash", "/tests/test.sh"], cwd="/app",
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    try:
        reward = read("/logs/verifier/reward.txt").strip()
    except OSError:
        reward = "NONE"
    return (reward, _PASSED.findall(out), _FAILED.findall(out), out)
