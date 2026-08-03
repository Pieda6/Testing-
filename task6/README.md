# dynamo/schedule-recovery

Twenty-five months of firing history from a cron-style scheduler, thirty jobs,
plus an explicit description of the host's clock and its downtime. Recover
enough of each schedule to say exactly when it fires over the following two
months.

## Layout

    task.toml                     labels, budgets, and the three explanations
    instruction.md                what the agent is given and asked for
    environment/Dockerfile        the single image, used for the agent and the verifier
    environment/.dockerignore     keeps everything but environment/data out of the build context
    environment/data/jobs.json    the log, the clock and the outages (agent-visible)
    solution/solve.sh             oracle entrypoint
    solution/solve.py             reference solver, standard library only
    tests/test.sh                 verifier entrypoint, writes reward.txt and ctrf.json
    tests/test_outputs.py         the two graded criteria
    tests/expected.json           the answer key and the prediction-window bounds

`tests/` is overlaid at `/tests` only at verification time. Nothing in it ever
reaches the agent image, and `environment/Dockerfile` never copies `solution/`
or `tests/`.

## What makes it hard

Three things, and they fail in different places.

- **Cron ORs day-of-month against day-of-week when both are restricted.**
  `0 0 13 * FRI` fires on the 13th *and* on every Friday. Six of the thirty
  jobs are shaped this way.
- **The host's clock is not UTC and its offset moves** — four transitions
  inside the log, two more inside the window to be predicted. Matching happens
  in local time, so a forward transition deletes local times (the job does not
  fire) and a backward one repeats them (it fires twice, at two UTC instants).
  The offsets match no real time zone, so tzdata is no help.
- **The host was down for nine intervals.** Nothing ran and nothing was logged,
  so silence inside one is not evidence about a schedule.

An error in the clock model or the outage handling *contradicts the log*, so a
solver that checks its recovered schedules against the history finds out. An
error in the projection is silent: the schedule is right, it reproduces all
20322 logged firings, and only the future timestamps are wrong.

## Ground truth

Established twice over, by two paths sharing no code:

1. the reference solver infers each schedule from the log and projects it;
2. `dev6/gen.py` simulates the hidden schedules forward directly.

They agree on all 1581 instants. `dev6/validate.py` separately enumerates
*every* schedule consistent with the log — 39 across the thirty jobs, nine jobs
admitting two — and confirms they all predict the same instants. That is why
the graded artifact is timestamps rather than a recovered crontab.

## Dev tooling (not shipped)

Lives in `dev6/`, outside this directory:

    gen.py        deterministic generator; emits jobs.json and the private truth.json
    probe.py      the ambiguity feasibility probe run before any of this was built
    infer.py      the inference core, kept alongside the validator
    validate.py   proves the answer is well defined and matches the hidden truth
    controls.py   scores each wrong approach job by job
    harness.py    runs the real verifier against the oracle and against wrong answers

## Measured

    oracle                                          1.0, byte-identical across re-runs
    nop / empty / all-silent / symlinked answer     0
    clock frozen at the end of the log              5 / 30 jobs
    only the first future transition applied        2 / 30 jobs
    day-of-month AND day-of-week                    13 / 30 jobs
    repeated local time emitted once                26 / 30 jobs
    offsets ignored                                 0 / 30 jobs
    local minutes converted with a single offset    5 / 30 jobs

Grading is all-or-nothing across all thirty, so every row below the first
scores zero.
