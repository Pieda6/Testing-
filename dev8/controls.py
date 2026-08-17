"""Run the real verifier against the oracle and against the ways of cheating.

Reproducibility is a property of the output, so byte equality on its own is
satisfied by any build that stops depending on its inputs -- freeze the
artifact, empty it, copy a pre-made one into place. Each of those is tried here
and has to score zero. So does every honest-but-incomplete fix, which the
mutation battery covers separately.

The layout is the container's: /app is the agent's tree, /tests is the overlay,
/logs/verifier is where the reward lands. The entrypoint under test is the one
that ships.
"""
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.join(HERE, "..", "task8")
SOLVE = os.path.join(TASK, "solution", "solve.sh")
PROJECT = os.path.join(TASK, "environment", "project")


def stage(fixed=True, edit=None):
    """Put a tree at /app, optionally solved, optionally then damaged."""
    if os.path.exists("/app"):
        shutil.rmtree("/app")
    shutil.copytree(PROJECT, "/app")
    if fixed:
        subprocess.run(["bash", SOLVE], check=True, capture_output=True)
    if edit:
        edit("/app")
    if os.path.exists("/tests"):
        shutil.rmtree("/tests")
    os.makedirs("/tests")
    for f in ("test.sh", "pytest.ini", "test_outputs.py"):
        shutil.copy2(os.path.join(TASK, "tests", f), os.path.join("/tests", f))
    os.chmod("/tests/test.sh", 0o755)


def reward():
    subprocess.run(["bash", "/tests/test.sh"], cwd="/app",
                   capture_output=True, text=True)
    try:
        with open("/logs/verifier/reward.txt") as f:
            return f.read().strip()
    except OSError:
        return "NONE"


def sub(path, old, new):
    s = io.open(path, encoding="utf-8").read()
    assert old in s, "pattern missing in %s: %r" % (path, old[:60])
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))


# --- the ways of getting byte equality without doing the work ---------------

def strip_debug(app):
    sub(app + "/Makefile", "-O2 -g -Wall", "-O2 -g0 -Wall")


def drop_docs(app):
    sub(app + "/Makefile", "\tcp docs/* $@/share/docs/\n", "")


def change_behaviour(app):
    sub(app + "/src/greet.c", '"Hello, %s!"', '"Hi there, %s!"')


def empty_bundle(app):
    sub(app + "/Makefile",
        "\tcd $(STAGE) && find $(PREFIX) | LC_ALL=C sort | \\",
        "\trm -rf $(STAGE)/$(PREFIX) && mkdir -p $(STAGE)/$(PREFIX)\n"
        "\tcd $(STAGE) && find $(PREFIX) | LC_ALL=C sort | \\")


def build_does_nothing(app):
    sub(app + "/Makefile", "all: $(DIST)/$(PREFIX).tar.gz",
        "all:\n\t@true\n\nunused: $(DIST)/$(PREFIX).tar.gz")


def prebaked(app):
    """The artifact is built once, committed, and copied into place from then
    on. Byte-identical everywhere, complete, and works -- and no longer a
    build."""
    subprocess.run(["make", "-s", "all"], cwd=app, check=True,
                   capture_output=True)
    os.makedirs(app + "/prebuilt", exist_ok=True)
    shutil.copy2(app + "/dist/greet-1.4.2.tar.gz",
                 app + "/prebuilt/greet-1.4.2.tar.gz")
    s = io.open(app + "/Makefile", encoding="utf-8").read()
    head, sep, _tail = s.partition("$(DIST)/$(PREFIX).tar.gz: $(STAGE)/$(PREFIX)")
    assert sep
    io.open(app + "/Makefile", "w", encoding="utf-8").write(
        head + "$(DIST)/$(PREFIX).tar.gz:\n"
        "\tmkdir -p $(DIST)\n"
        "\tcp prebuilt/$(PREFIX).tar.gz $@\n\n"
        "check: ;\nclean:\n\trm -rf $(BUILD) $(STAGE) $(DIST)\n")


CASES = [
    ("reference solution", True, None, "1"),
    ("the project as shipped", False, None, "0"),
    ("one fix missing: gzip -n", True,
     lambda a: sub(a + "/Makefile", "gzip -n -9", "gzip -9"), "0"),
    ("one fix missing: archive mtimes", True,
     lambda a: sub(a + "/Makefile",
                   "\t\t    --mtime=@$(SOURCE_DATE_EPOCH) \\\n", ""), "0"),
    ("debug information stripped", True, strip_debug, "0"),
    ("docs dropped from the bundle", True, drop_docs, "0"),
    ("the CLI's behaviour changed", True, change_behaviour, "0"),
    ("an empty bundle", True, empty_bundle, "0"),
    ("the build does nothing", True, build_does_nothing, "0"),
    ("the bundle pre-baked and copied into place", True, prebaked, "0"),
]


def main():
    bad = 0
    for label, fixed, edit, want in CASES:
        stage(fixed=fixed, edit=edit)
        got = reward()
        flag = "" if got == want else "   <-- expected %s" % want
        bad += got != want
        print("  %-46s reward=%s%s" % (label, got, flag))
    print()
    if bad:
        print("%d of %d controls came out wrong" % (bad, len(CASES)))
        return 1
    print("oracle scores 1; every degenerate and partial solution scores 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
