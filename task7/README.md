# dynamo/hai-surveillance-adjudication

A surveillance definitions manual with its twelve constants redacted, a prior
state audit of 36 patients — four of whose entries are wrong, and which ones is
not recorded — and a held-out quarter of 36 patients with no adjudications.
Recover the constants from the audit, then adjudicate the held-out quarter.

The records are synthetic and generated deterministically from a fixed seed.
There are no real records, no real identifiers, and nothing derived from a real
person. The task is administrative classification against a written rule set,
not diagnosis or treatment.

## Layout

    task.toml                       labels, budgets, and the three explanations
    instruction.md                  what the agent is given and asked for
    environment/Dockerfile          the single image, agent and verifier
    environment/.dockerignore       keeps all but environment/data out of the build
    environment/data/manual.md      the definitions, constants redacted (agent-visible)
    environment/data/audited.json   the prior audit: patients + validated adjudications
    environment/data/records.json   the held-out quarter to adjudicate
    solution/solve.sh               oracle entrypoint
    solution/solve.py               reference adjudicator, standard library only
    tests/test.sh                   verifier entrypoint, writes reward.txt and ctrf.json
    tests/test_outputs.py           the two graded criteria
    tests/expected.json             answer key plus patient and ward order

`tests/` is overlaid at `/tests` only at verification time. Nothing in it ever
reaches the agent image, and `environment/Dockerfile` never copies `solution/`
or `tests/`.

## What makes it hard

- **The fit is joint, not separable.** The width of the window decides the date
  of event, and the date of event decides healthcare association, ward
  attribution and line association together. Constants recovered one at a time
  are each defensible and wrong in combination.
- **The audit has to be read for what it excludes.** The validated entries
  reporting *no* event for a patient with a positive culture are what pin the
  admission-day cut and the window edges. A solver that studies only the entries
  reporting events pins almost nothing.
- **The audit is not clean.** No setting reproduces all of it, so a search that
  demands consistency finds nothing — and one that relaxes a constant until the
  last stubborn entry fits lands on a setting explaining somebody's slip. The
  recovery has to score agreement and check the winner wins outright.
- **Nothing checks the fit on the held-out quarter.** A setting that explains
  the audit and is still wrong produces a complete, coherent, plausible
  adjudication that no part of the data contradicts.
- **The constants are not the familiar ones.** Two of them differ from what any
  well-known surveillance system uses, and the instruction says so — filling
  them in from memory instead of recovering them costs a patient.

The manual ships in the container with its structure intact and its numbers
marked `[[?]]`; §5, §8 and §10 each name two possibilities and leave the choice
open. Twelve values are missing in all.

## Well-posedness

The load-bearing check. A grid of **4,811,400 settings**, wider than the truth
in every direction, exhausted against the audit: **exactly one** explains the
most entries — 32 of 36 — and it is the setting the data was generated from,
with every other setting strictly behind.

Two earlier sweeps were rejected by this check before anything shipped.

The first left *two* survivors differing in where the attribution period opens:
that discriminator had its sign exactly at the window edge, where both readings
land on the same day. Fixed by a patient whose sign sits one day inside, with a
blood culture in the resulting gap.

The second showed why the audit's errors must be *chosen*. A mis-recorded line
flag and a ward charged to the receiving unit are exactly what `line_grace=0`
and `transfer_window=0` predict — so that wrong setting explained 26 entries and
beat the truth's 24. An error a wrong setting can explain is not noise; it is
evidence for that setting. Every corruption now shipped is inexplicable under
*any* setting — a line association asserted for a patient who never had a line,
a ward never occupied, an organism never cultured, a date no window can reach —
and each falls on a chart that pins no constant, since agreement is scored per
patient and corrupting a discriminator destroys its evidence too.

The held-out quarter was then checked to exercise every constant: each of the 21
single-constant perturbations changes the answer for at least one held-out
patient, so no recovered value is decorative.

## Dev tooling (not shipped)

Lives in `dev7/`, outside this directory:

    params.py     the procedure with all twelve constants left free
    gen2.py       generator: the audit set (boundaries hand-placed) and held-out
    fit.py        exhausts the 4.8M grid; proves the audit pins one setting
    controls2.py  scores each mis-recovered constant on the held-out quarter
    harness.py    runs the verifier against the oracle and against wrong answers

## Measured

    oracle                                      1.0, byte-identical across re-runs
    no file / empty / nothing reported          0
    all denominators zero / symlinked answer    0
    schema and single-determination faults      0

One constant recovered wrongly, by held-out patients still fully correct out of
36. Grading is all-or-nothing, so every row below scores zero:

    events dated by the anchor, not the earliest element   27
    bloodstream adjudicated first                          32
    window one day narrow at the back                      32
    window one day wide at the back                        34
    admission-day cut moved either way                     34
    attribution period opens at the date of event          34
    day after line removal not counted                     34
    window off a day at the front, either way              35
    commensal gap off either way                           35
    timeframe a day short or a day long                    35
    attribution period three days short or one day long    35
    line-day threshold off either way                      35
    transfer window off either way                         35
    the familiar values, filled in from memory             35

Every one of these still fails the audit, so a solver that fits properly and
checks its fit catches all of them. They are what a sloppy fit scores.
