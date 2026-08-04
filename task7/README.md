# dynamo/hai-surveillance-adjudication

A surveillance definitions manual with its twelve constants redacted, a prior
state audit of 28 patients whose 24 adjudications were validated under the
complete manual, and a held-out quarter of 36 patients with none. Recover the
constants from the audit, then adjudicate the held-out quarter with them.

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
- **Nothing checks the fit on the held-out quarter.** A setting that reproduces
  the whole audit and is still wrong produces a complete, coherent, plausible
  adjudication that no part of the data contradicts.
- **The constants are not the familiar ones.** Two of them differ from what any
  well-known surveillance system uses, and the instruction says so — filling
  them in from memory instead of recovering them costs a patient.

The manual ships in the container with its structure intact and its numbers
marked `[[?]]`; §5, §8 and §10 each name two possibilities and leave the choice
open. Twelve values are missing in all.

## Well-posedness

The load-bearing check. A grid of **4,811,400 settings**, wider than the truth
in every direction, exhausted against the audit: **exactly one** reproduces all
24 validated adjudications, and it is the setting the data was generated from.

The first sweep found *two* survivors, differing in where the attribution period
opens — that discriminator had been built with its sign exactly at the window
edge, which makes the two readings land on the same day. A patient was added
whose sign sits one day inside, with a blood culture in the resulting gap. The
re-run leaves one.

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
