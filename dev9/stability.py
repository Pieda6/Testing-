"""Does the reference solution pass every time, including on a busy machine?

The gates in the harness are timed waits, so the honest worry about a task like
this one is not whether a correct answer passes but whether it passes on a CI
runner with other work on it. A verifier that fails its own oracle now and then
turns valid trials into invalid ones and fails the difficulty gate for a reason
that has nothing to do with difficulty.

Each scenario is compiled once, exactly as the shipped verifier compiles it, and
then run many times: first on an idle machine, then against a load generator
that keeps every core busy.

    python3 dev9/stability.py [repeats]
"""
import importlib.util
import os
import subprocess
import sys
import time

import runner

SCENARIOS = ["s%d" % n for n in range(11)]
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C", "LC_ALL": "C",
       "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}


def verifier_module():
    """Import the shipped verifier so its own header and harness are used."""
    path = os.path.join(runner.TASK, "tests", "test_outputs.py")
    spec = importlib.util.spec_from_file_location("shipped_verifier", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["shipped_verifier"] = module
    spec.loader.exec_module(module)
    return module


def build(source, where):
    module = verifier_module()
    os.makedirs(where, exist_ok=True)
    for name, text in (("mpmc_ring.cpp", source),
                       ("mpmc_ring.h", module.TRUSTED_HEADER),
                       ("harness.cpp", module.HARNESS)):
        with open(os.path.join(where, name), "w", encoding="utf-8") as handle:
            handle.write(text)
    binary = os.path.join(where, "mpmc_harness")
    result = subprocess.run(
        ["/usr/bin/g++", "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
         "-Wpedantic", "-Werror", "-pthread", "-fsanitize=undefined",
         "-fno-sanitize-recover=undefined", "-I", where,
         os.path.join(where, "mpmc_ring.cpp"),
         os.path.join(where, "harness.cpp"), "-o", binary],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-3000:]
    return binary


def sweep(binary, repeats, label):
    worst = {}
    failures = []
    for _ in range(repeats):
        for scenario in SCENARIOS:
            start = time.time()
            try:
                proc = subprocess.run([binary, scenario, "token"],
                                      capture_output=True, text=True,
                                      cwd=os.path.dirname(binary), env=ENV,
                                      timeout=8)
                code, detail = proc.returncode, (proc.stderr or "").strip()
                if code == 0 and "token %s completed" % scenario \
                        not in proc.stdout:
                    code, detail = -2, "exited without completing"
            except subprocess.TimeoutExpired:
                code, detail = -1, "timed out at the 8s deadlock guard"
            spent = time.time() - start
            worst[scenario] = max(worst.get(scenario, 0.0), spent)
            if code != 0:
                failures.append((scenario, detail.splitlines()[-1:] or [""]))
    order = sorted(worst, key=lambda s: -worst[s])
    print("  %-14s %d runs of each scenario, slowest: %s"
          % (label, repeats, ", ".join("%s %.2fs" % (s, worst[s])
                                       for s in order[:4])))
    print("  %-14s total of the slowest observations: %.1fs"
          % ("", sum(worst.values())))
    if failures:
        for scenario, detail in failures[:6]:
            print("      FAILED %s: %s" % (scenario, detail[0] if detail else ""))
    return failures


def main():
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    binary = build(runner.read(runner.REFERENCE), "/tmp/mpmc-stability")

    failures = sweep(binary, repeats, "idle:")

    load = [subprocess.Popen(["python3", "-c", "while True: pass"])
            for _ in range(2 * (os.cpu_count() or 4))]
    try:
        time.sleep(1)
        failures += sweep(binary, repeats, "under load:")
    finally:
        for proc in load:
            proc.kill()
        for proc in load:
            proc.wait()

    print()
    if failures:
        print("the reference solution failed %d of %d runs"
              % (len(failures), 2 * repeats * len(SCENARIOS)))
        return 1
    print("the reference solution passed all %d runs, idle and loaded"
          % (2 * repeats * len(SCENARIOS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
