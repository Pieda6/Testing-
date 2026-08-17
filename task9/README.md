# Repair MPMC Ring

This repository contains the Dynamo task `dynamo/repair-mpmc-ring`.

## Classification

- Category: Debugging and Repair
- Sub-category: Concurrency and synchronization debugging
- Primary artifact: `/app/src/mpmc_ring.cpp`

## Layout

    task/task.toml                       labels, budgets, and the three explanations
    task/instruction.md                  what the agent is given and asked for
    task/environment/Dockerfile          the single image, agent and verifier
    task/environment/.dockerignore       keeps all but app/ out of the build
    task/environment/app/                the project, COPYed to /app
    task/environment/app/MPMC_SPEC.md    the normative contract
    task/solution/mpmc_ring.cpp          oracle: the repaired implementation
    task/solution/solve.sh               copies it over the artifact
    task/tests/test.sh                   verifier entrypoint, hardened
    task/tests/pytest.ini                pinned config, so rootdir cannot be hijacked
    task/tests/test_outputs.py           trusted header, C++20 harness, eleven scenarios

There is no answer key. Correctness here is a property of what the code does
under a schedule, so the verifier compiles the submission against a trusted copy
of the public header and runs it; many different correct implementations pass.

## What ships, and why it is wrong

`/app/src/mpmc_ring.cpp` is the implementation a competent engineer writes
first. It is a bounded ring with independent atomic producer and consumer
tickets, a publication frontier advanced in logical ticket order, capacity taken
as the distance between the reserve and consume tickets, and a compare-exchange
to claim the range that was observed to be eligible. Under ordinary use it is
correct, and the two scenarios covering ordinary use pass as it stands.

Six defects, on four axes:

    ownership     the producer insists on the ticket it observed before the
                  hook, so an operation that was overtaken while blocked fails
                  instead of rebasing on a later eligible range
    ownership     the same insistence on the consumer side
    capacity      a slot is treated as free once the consumer has taken its
                  ticket rather than once it has released the slot, so a
                  producer overwrites a payload its consumer still holds
    publication   publication is serialised in ticket order, so a producer
                  whose payload work is finished waits for an earlier owner
                  that is still stalled inside its hook
    close         a defensive re-check after ownership abandons a batch the
                  producer already owns when a close lands underneath it
    arithmetic    availability compares ticket values outright instead of their
                  modular distance, so an empty ring reports values available
                  once tickets wrap

Two of these cannot be patched where they stand. Ordered publication has to be
replaced by per-slot lifecycle state, because the contract requires a later
range to *complete* while remaining invisible until the earlier one publishes —
completion and visibility are separate events. Capacity has to start tracking
release rather than ownership. The rest of the repair follows from those two
decisions, which is why the intended solution is a design rather than a patch.

## What makes it hard

- **The contract is fully disclosed and it does not help enough.**
  `MPMC_SPEC.md` states every requirement. The work is satisfying them at the
  same time: atomic range ownership, a candidate hook that fires at most once,
  revalidation after being overtaken, ordered visibility with unordered
  completion, release-before-reuse, and a close that linearises against
  ownership without ever waiting on a hook.
- **The obvious repairs are themselves forbidden.** Fixing the ownership race
  with a retry loop invokes the candidate hook again, which the contract rules
  out. Fixing the close race by taking a lock around ownership makes `close()`
  block behind a producer parked in a hook, which the contract also rules out.
  Both wrong repairs were measured; both score zero.
- **All-or-nothing.** Eleven scenarios, every one required. Finding five of the
  six defects scores what finding none scores.
- **No feedback loop.** The scenarios are not in the agent's image. The
  specification says what must hold; deciding which schedules would expose a
  violation is the agent's job.

## Verification

The verifier reads only the declared artifact — `O_NOFOLLOW`, regular file, size
capped — compiles it against a trusted copy of the header with `-std=c++20
-Wall -Wextra -Wpedantic -Werror` and the undefined-behaviour sanitizer halting
on the first report, then runs eleven scenarios driven by condition-variable
gates rather than random stress:

    s0   construction, API validation, single and batch FIFO, full, empty, close
    s1   failed pushes and pops leave no trace
    s2   reuse across the signed and unsigned ticket boundaries, empty across wrap
    s3   a producer stalled after ownership does not hold up a later producer
    s4   a consumer stalled after ownership does not hold up a later consumer
    s5   close does not revoke a batch that is already owned
    s6   a slot is not reused before its prior consumer releases it
    s7   an overtaken producer candidate rebases; hook fires once; no early visibility
    s8   an overtaken consumer candidate rebases; hook fires once
    s9   close defeats a producer stalled before ownership, without waiting for it
    s10  mixed multi-producer/multi-consumer exact-once delivery

The submission is compiled into the harness process, so exiting successfully is
something it could do for itself. Each scenario therefore has to echo a token
the verifier chooses after the build; a process that exits zero without running
the scenario to its end fails.

Scenario timeouts are deadlock guards, not the source of difficulty. Across 704
runs of the reference solution — half of them with twice as many spinning
processes as cores — the slowest scenario took 0.07s against gates of 700ms and
more.

## Measured

    the reference solution                              reward 1, about 7s
    the project as shipped                              0   (s1,s2,s3,s5,s6,s7,s8,s10)
    each of the six planted defects, applied alone      0
    retry re-fires the candidate hook                   0
    producer reservation held across the hook           0
    consumer reservation held across the hook           0
    every push and pop refuses                          0
    the hooks are never called                          0
    the harness process exits zero early                0
    the artifact missing, symlinked, or oversized       0

Repairing the modular-arithmetic defect alone clears two scenarios and still
scores zero, which is the shape of the whole task: no single repair is enough.

## Three requirements the hook set cannot expose

The contract also requires that payloads be written before publication, that a
batch not become visible a prefix at a time, and that a consumer obtain its
payload before releasing a slot. All three were built as defects and measured;
all three score 1, because the hook set has no observation point *inside* the
payload-and-publication window, and without one there is no deterministic
schedule that separates those steps. They are therefore not planted — grading a
defect the harness cannot see would be worse than leaving it out. Adding a hook
point would close the gap, at the cost of enlarging the public API the agent
must implement and pointing straight at the answer.

A signed comparison in the capacity test was measured too. It is caught, but
only by the scenarios that already catch the ticket-difference defect beneath
it, so it is left out rather than credited as coverage it does not add.

## Dev tooling (not shipped)

Lives in `dev9/`, outside the task directory:

    runner.py       stages /app and /tests as the container does and grades
    mutations.py    every defect and every forbidden repair, one at a time
    controls.py     the oracle, the shipped tree, and the ways of not doing the work
    stability.py    the reference solution, many runs, idle and under load
