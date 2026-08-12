"""Run the real entrypoint against the oracle, the shipped tree, and the ways of
scoring without doing the work.

Behavioural grading has its own failure mode: any implementation that quietly
stops doing the job can look calm from the outside. A ring that refuses every
push is never caught losing a value; one that never calls the hooks is never
caught holding a lock across one; one that serialises everything is correct in
every sense except the one that matters. Each of those is tried here and has to
score zero.

    python3 dev9/controls.py
"""
import io
import os
import subprocess
import sys

import mutations
import runner

STUB = r"""#include "mpmc_ring.h"

#include <memory>
#include <stdexcept>

namespace dynamo {

class MpmcRing::Impl {
public:
    Impl(
        std::size_t capacity,
        Ticket,
        ObservationHook
    )
        : capacity_(capacity) {
        if (
            capacity < 2
            || (capacity & (capacity - 1)) != 0
        ) {
            throw std::invalid_argument("capacity");
        }
    }

    std::size_t capacity_;
};

MpmcRing::MpmcRing(
    std::size_t capacity,
    Ticket initial_ticket,
    ObservationHook hook
)
    : impl_(
          std::make_unique<Impl>(
              capacity,
              initial_ticket,
              std::move(hook)
          )
      ) {}

MpmcRing::~MpmcRing() = default;

bool MpmcRing::try_push(Value) {
    return false;
}

bool MpmcRing::try_push_batch(
    const std::vector<Value>& values
) {
    if (
        values.empty()
        || values.size() > impl_->capacity_
    ) {
        throw std::invalid_argument("batch");
    }

    return false;
}

std::optional<Value>
MpmcRing::try_pop() {
    return std::nullopt;
}

std::optional<std::vector<Value>>
MpmcRing::try_pop_batch(
    std::size_t count
) {
    if (
        count == 0
        || count > impl_->capacity_
    ) {
        throw std::invalid_argument("batch");
    }

    return std::nullopt;
}

void MpmcRing::close() {}

bool MpmcRing::closed() const noexcept {
    return true;
}

std::size_t
MpmcRing::capacity() const noexcept {
    return impl_->capacity_;
}

}  // namespace dynamo
"""


def silent_hooks(src):
    """Correct in every respect except that the hooks are never called, so no
    schedule the verifier arranges can ever be entered."""
    return mutations.sub(src, """        if (!hook_) {
            return;
        }

        hook_(
            point,
            first_ticket,
            count
        );""", """        (void)point;
        (void)first_ticket;
        (void)count;""")


def exit_zero(src):
    """The submission is compiled into the harness process, so it tries to end
    that process successfully before any scenario can run."""
    return mutations.sub(src, "namespace dynamo {", """#include <cstdlib>

namespace {

struct QuietSuccess {
    QuietSuccess() {
        std::_Exit(0);
    }
};

QuietSuccess quiet_success;

}  // namespace

namespace dynamo {""")


def serialised(src):
    """One reservation transition per side, taken before the candidate hook and
    held across it: correct values, no independent progress."""
    return mutations.consumer_lock_across_hook(
        mutations.producer_lock_across_hook(src))


def grade_missing():
    """The graded artifact is not there at all."""
    runner.stage(runner.read(runner.REFERENCE))
    os.remove("/app/src/mpmc_ring.cpp")
    return _run_entrypoint()


def grade_symlink():
    """The graded path is a symlink pointing at a correct file elsewhere."""
    runner.stage(runner.read(runner.REFERENCE))
    io.open("/app/src/real.cpp", "w").write(runner.read(runner.REFERENCE))
    os.remove("/app/src/mpmc_ring.cpp")
    os.symlink("/app/src/real.cpp", "/app/src/mpmc_ring.cpp")
    return _run_entrypoint()


def grade_oversized():
    """The graded artifact is padded past the size the verifier will read."""
    src = runner.read(runner.REFERENCE)
    return ("// %s\n" % ("x" * (3 * 1024 * 1024))) + src


def _run_entrypoint():
    if os.path.exists("/logs/verifier/reward.txt"):
        os.remove("/logs/verifier/reward.txt")
    subprocess.run(["bash", "/tests/test.sh"], cwd="/app",
                   capture_output=True, text=True)
    try:
        return runner.read("/logs/verifier/reward.txt").strip()
    except OSError:
        return "NONE"


def main():
    reference = runner.read(runner.REFERENCE)

    cases = [
        ("the reference solution", lambda: reference, "1"),
        ("the project as shipped", lambda: runner.read(runner.SHIPPED), "0"),
        ("every push and pop refuses", lambda: STUB, "0"),
        ("the hooks are never called", lambda: silent_hooks(reference), "0"),
        ("the harness process exits zero early",
         lambda: exit_zero(reference), "0"),
        ("reservation held across the hooks",
         lambda: serialised(reference), "0"),
        ("the artifact padded past the read limit", grade_oversized, "0"),
    ]

    bad = 0
    for label, build, want in cases:
        reward, _passed, failed, _out = runner.grade(build())
        flag = "" if reward == want else "   <-- expected %s" % want
        bad += reward != want
        print("  %-42s reward=%s  fails %-24s%s"
              % (label, reward, ",".join(failed) or "-", flag))

    for label, run, want in (("the artifact is missing", grade_missing, "0"),
                             ("the artifact is a symlink", grade_symlink, "0")):
        reward = run()
        flag = "" if reward == want else "   <-- expected %s" % want
        bad += reward != want
        print("  %-42s reward=%s%s" % (label, reward, flag))

    print()
    if bad:
        print("%d controls came out wrong" % bad)
        return 1
    print("the reference scores 1; the shipped tree and every shortcut score 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
