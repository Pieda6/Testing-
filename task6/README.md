# dynamo/schedule-recovery

Three years of firing history from a cron-style scheduler, twenty-four jobs,
plus the host's UTC offset at the start of the log and the intervals it was
down. Recover the host's offset-change rule and every job's schedule, then say
exactly when each fires over the following ten months.

## Layout

    task.toml                     labels, budgets, and the three explanations
    instruction.md                what the agent is given and asked for
    environment/Dockerfile        the single image, used for the agent and the verifier
    environment/.dockerignore     keeps everything but environment/data out of the build context
    environment/data/jobs.json    the log, the base offset and the outages (agent-visible)
    solution/solve.sh             oracle entrypoint
    solution/solve.py             reference solver, standard library only
    tests/test.sh                 verifier entrypoint, writes reward.txt and ctrf.json
    tests/test_outputs.py         the two graded criteria
    tests/expected.json           the answer key and the prediction-window bounds

`tests/` is overlaid at `/tests` only at verification time. Nothing in it ever
reaches the agent image, and `environment/Dockerfile` never copies `solution/`
or `tests/`.

## What makes it hard

- **The clock's transitions are not given.** Only the offset at the start of the
  log is. Six changes are visible in the log, as every daily job's UTC times
  shifting together; two more fall inside the window to be predicted and are
  never observed at all. Those two have to come from fitting a rule — month,
  weekday, *which occurrence* of that weekday, which local hour — to the six
  that were seen.
- **That fit cannot be checked against the log.** A rule off by a week, or one
  that reads "4th Sunday" where the truth is "last Sunday", reproduces all
  21308 logged firings exactly and is still wrong about the future. This is the
  crux, and it is what v1 of this task was missing.
- **Pinning a transition to one instant takes a specific observation.** A job on
  the even hours works, because shifting it an hour lands on the odd hours — a
  disjoint set, distinguishing every hour of the day. A contiguous run of times
  does not: slide it an hour and it covers itself everywhere but its two ends,
  so the change can hide inside. Direction needs a second job, since the even
  hours look the same shifted either way.
- **Cron ORs day-of-month against day-of-week when both are restricted.**
  `0 0 13 * FRI` fires on the 13th *and* on every Friday. Six of the twenty-four
  jobs are shaped this way.
- **The host was down for eight intervals.** Nothing ran and nothing was logged,
  so silence inside one is not evidence about a schedule.

Errors in the clock *model* or the outage handling contradict the log, so a
solver that checks finds out and recovers. Errors in the clock *rule* are
silent.

## Ground truth

Established twice over, by two paths sharing no code:

1. the reference solver recovers the clock and each schedule from the log alone
   and projects them forward;
2. `dev6/gen.py` simulates the hidden schedules forward directly under the true
   clock.

They agree on all 5911 instants, and the recovered clock matches the generator's
exactly — including the two transitions inside the prediction window that the
log never shows. `dev6/validate.py` enumerates *every* offset rule consistent
with the six logged changes and *every* schedule consistent with the log, and
finds exactly one of each, so the answer is well defined.

The calendar was chosen for that (`dev6/calsearch.py`): three occurrences fall
inside the log, two of them in months with five of that weekday — which is what
separates "last" from "4th". Two observations would leave the readings tied.

## Dev tooling (not shipped)

Lives in `dev6/`, outside this directory:

    gen.py        deterministic generator; emits jobs.json and the private truth.json
    probe.py      the ambiguity feasibility probe run before any of this was built
    ruleprobe.py  how many observations pin an offset rule (three; two are not enough)
    calsearch.py  picks the month/weekday/years so the rule is both pinned and trapped
    infer.py      the inference core, kept alongside the validator
    validate.py   proves the clock and the answer are well defined and match the truth
    controls.py   scores each wrong approach job by job, and whether it reproduces the log
    harness.py    runs the real verifier against the oracle and against wrong answers

## Measured

    oracle                                          1.0, byte-identical across re-runs
    nop / empty / all-silent / symlinked answer     0

Silent — the recovered schedules reproduce all 21308 logged firings, so the
solver's own validation passes; only the future is wrong:

    4th occurrence read for the last one             6 / 24 jobs
      ... spring change only                         6 / 24 jobs
      ... autumn change only                         7 / 24 jobs
    change placed an hour late                      20 / 24 jobs
    change placed a week late                        1 / 24 jobs
    clock frozen at the end of the log               0 / 24 jobs
    only the first future change applied             3 / 24 jobs
    change direction reversed                        0 / 24 jobs
    repeated local time emitted once                22 / 24 jobs

Detectable — these contradict the log:

    UTC read as local                               no consistent schedule
    base offset held, no transitions at all         no consistent schedule
    outage silence read as evidence                 no consistent schedule
    day-of-month AND day-of-week                    17 / 24 jobs

Grading is all-or-nothing across all twenty-four, so every row below the first
scores zero.
