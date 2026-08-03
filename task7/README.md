# dynamo/hai-surveillance-adjudication

One reporting quarter of synthetic inpatient surveillance data — 36 patients,
37 admissions, 62 cultures, five wards — plus a self-contained definitions
manual. Adjudicate which healthcare-associated infections are reportable, with
the date of event, ward, organisms and central line association for each, and
report the ward device-day denominators.

The records are synthetic and generated deterministically from a fixed seed.
There are no real records, no real identifiers, and nothing derived from a real
person. The task is administrative classification against a written rule set,
not diagnosis or treatment.

## Layout

    task.toml                       labels, budgets, and the three explanations
    instruction.md                  what the agent is given and asked for
    environment/Dockerfile          the single image, agent and verifier
    environment/.dockerignore       keeps all but environment/data out of the build
    environment/data/records.json   the surveillance records (agent-visible)
    environment/data/manual.md      the governing definitions (agent-visible)
    solution/solve.sh               oracle entrypoint
    solution/solve.py               reference adjudicator, standard library only
    tests/test.sh                   verifier entrypoint, writes reward.txt and ctrf.json
    tests/test_outputs.py           the two graded criteria
    tests/expected.json             answer key plus patient and ward order

`tests/` is overlaid at `/tests` only at verification time. Nothing in it ever
reaches the agent image, and `environment/Dockerfile` never copies `solution/`
or `tests/`.

## What makes it hard

- **Every error is silent.** An adjudication has no self-consistency test. There
  is no log to replay, no model to re-simulate — a wrong determination produces
  a coherent, plausible, internally consistent answer set that nothing in the
  records contradicts. That is the property this task is built around.
- **The date of event is not the culture date.** It is the earliest element used
  to meet the definition, often a sign preceding the culture. It then decides
  healthcare association, ward attribution and line association, so one slip
  moves three answers — and can drag an event onto admission day 2 where it
  stops being reportable at all.
- **The rules are coupled.** A reported urinary tract infection can demote a
  later blood culture to secondary; organism lists grow as suppressed repeats
  merge into them; one patient's blood culture is secondary *only* because of an
  organism an earlier suppression added.
- **Boundaries everywhere.** Admission day 3, day 14 of the timeframe, a line in
  place more than two calendar days, the day after removal, a ward arrival on
  the date of event or the day before, the clip at each end of the reporting
  period. Each is exercised in both directions by the shipped data.

The manual ships in the container and is authoritative, so nothing depends on
which edition of a real manual a model has memorised.

## Ground truth

Two adjudicators that share no code, written the other way round:

1. `solution/solve.py` — date intervals and a candidate pool;
2. `dev7/brute.py` — explicit per-calendar-day tables, walked day by day.

Each was derived from `manual.md` rather than from the other. They agree on all
36 patients and on every ward's central line day count. That agreement is the
whole basis for the key — with no self-consistency test available, one
implementation's output would be one implementation's opinion.

## Dev tooling (not shipped)

Lives in `dev7/`, outside this directory:

    gen.py        deterministic generator; every boundary hand-placed
    brute.py      the independent adjudicator
    validate.py   compares the two, and reports what the data exercises
    controls.py   scores each misreading of the manual, patient by patient
    harness.py    runs the real verifier against the oracle and wrong answers

## Measured

    oracle                                      1.0, byte-identical across re-runs
    no file / empty / nothing reported          0
    all denominators zero / symlinked answer    0

Misreadings of the manual, by patients still fully correct out of 36 (all-or-
nothing grading means every row scores 0):

    signs ignored; culture date used as date of event    28
    timeframe ignored; every candidate reported          27
    suppressed candidates dropped, not merged            28
    a lone commensal culture counted                     32
    admission day 4 required                             33
    transfer rule dropped; receiving ward charged        33
    secondary rule not applied at all                    34
    admission day 2 treated as reportable                34
    timeframe run to 15 days                             34
    attribution period one day too long                  35
    matched against the UTI culture, not merged list     35
    commensal pair unmatched by name / two days apart    35
    line days as 24-hour periods                         35
    day after removal not counted                        35
    transfer rule on the day of transfer only            35
    timeframe started the day after the date of event    35

Two more leave every patient right and the ward denominators wrong, which fails
just the same: not counting the removal day, and counting days outside the
reporting period.
