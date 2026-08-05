# dynamo/hai-surveillance-adjudication

A surveillance definitions manual with its twelve constants redacted, a prior
state audit of 39 patients — four of whose entries are wrong, and which ones is
not recorded — and a held-out quarter of 47 patients with no adjudications.
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

- **The constants are not the familiar ones.** Ten of the twelve differ from the
  values the well-known national definitions use: the window is asymmetric, two
  commensal cultures may be drawn two days apart, the admission-day cut falls a
  day later, the repeat timeframe is shorter, the attribution period opens at
  the date of event and runs longer, a line must have been in place a day
  longer, two days after removal still count, the transfer rule reaches two
  days. The instruction says so outright. A solver that fills all twelve in from
  memory gets **26 of the 47** held-out patients right.
- **The fit is joint, and the audit cannot be made separable.** No two audit
  patients differ in a single element. Each stacks several boundaries at once,
  so widening the window moves the date of event, which moves the admission-day
  test, the transfer test and the timeframe test with it. Each of the 31
  boundary-bearing patients is sensitive to three to eight of the twelve
  constants, 4.6 on average — a mismatch says one of several is wrong and does
  not say which. There is no pair to read a constant off and no order in which
  the twelve can be settled one at a time. A mistake in the procedure looks
  exactly like a mistake in a constant.
- **The search has to be framed.** The grid that contains the answer holds
  **148,500,000** settings and cannot be walked patient by patient inside the
  budget. Staging it by what each constant can affect collapses it to 1,188,000
  pool-and-walk settings, of which the reference scores 6,500 in full.
- **The audit has to be read for what it excludes.** Twenty-four of the 39
  entries report fewer events than the patient has positive cultures — one
  suppressed by the admission-day cut, a sign a day outside the window, a
  commensal pair drawn a day too far apart, a repeat absorbed into an open
  timeframe, a bloodstream culture demoted to secondary. Those absences pin the
  cut, the window edges, the drawing gap, the timeframe and the attribution
  period. A solver reasoning only from reported events pins almost nothing.
- **The audit is not clean.** No setting reproduces all of it, so a search that
  demands consistency finds nothing — and one that relaxes a constant until the
  last stubborn entry fits lands on a setting explaining somebody's slip. The
  recovery has to score agreement and check the winner wins outright.
- **Nothing checks the fit on the held-out quarter.** A setting that explains
  the audit and is still wrong produces a complete, coherent, plausible
  adjudication that no part of the data contradicts.

The manual ships in the container with its structure intact and its numbers
marked `[[?]]`; §5, §8 and §10 each name two possibilities and leave the choice
open. Twelve values are missing in all.

## Well-posedness

Three checks, run together, and each has rejected a design.

*Uniqueness.* A grid of **148,500,000 settings**, wider than the truth in every
direction on every axis, exhausted against the audit: **exactly one** explains
the most entries — 35 of 39 — and it is the setting the data was generated
from, with every other setting strictly behind.

*Non-separability.* For every patient, how many of the twelve constants have
some value in the grid that changes that patient's adjudication. Every
boundary-bearing patient is changed by **at least three**; the eight changed by
none are exactly the eight it is safe to put an error on. A patient changed by
one constant would hand that constant over on its own, and is rejected.

*Reach.* Every one of the **57** single-constant errors changes the
adjudication of at least one held-out patient, so no recovered value is
decorative.

Four earlier designs were rejected by these checks before anything shipped.

The first left *two* survivors differing in where the attribution period opens:
that discriminator had its sign exactly at the window edge, where both readings
land on the same day. Fixed by a patient whose sign sits one day inside, with a
blood culture in the resulting gap.

The second showed why the audit's errors must be *chosen*. A mis-recorded line
flag and a ward charged to the receiving unit are exactly what two wrong
constants predict — so that wrong setting explained more entries than the truth.
An error a wrong setting can explain is not noise; it is evidence for that
setting. Every corruption now shipped is inexplicable under *any* setting — a
line association asserted for a patient who never had a line, a ward never
occupied, an organism never cultured, a date no window can reach — and each
falls on a patient that pins no constant, since agreement is scored per patient
and corrupting a discriminator destroys its evidence too.

The third pinned the constants uniquely but as contrastive twins: two patients
identical but for one element, so each constant could be read off one pair.
Uniqueness and non-separability are different properties and it had only the
first. The fourth randomised every offset to destroy the twins and destroyed the
information with them — charts placed away from a boundary pin nothing, and 168
to 792 settings tied. Stacking boundaries instead of isolating them is what
gives both properties at once.

## Dev tooling (not shipped)

Lives in `dev7/`, outside this directory:

    params.py        the procedure with all twelve constants left free
    gen5.py          the shipped data: audit, held-out, key, all three checks
    gen2.py          the ordinary held-out admissions, and the first audit design
    gen3.py, gen4.py the two rejected audit designs, kept as a record
    controls3.py     scores each mis-recovered constant on audit and held-out
    harness.py       runs the verifier against the oracle and against wrong answers

## Measured

    oracle                                      1.0, byte-identical across re-runs
    no file / empty / nothing reported          0
    all denominators zero / symlinked answer    0
    schema and single-determination faults      0

One constant recovered wrongly, by held-out patients still fully correct out of
47. Grading is all-or-nothing, so every row below scores zero, and every row
also loses to the recovered setting on the audit:

    events dated by the anchor, not the earliest element   33
    window reaching only one day back                      36
    transfer rule at nought days / at one day              37 / 38
    line required in place six days                        39
    admission day 6 the first that counts                  40
    the remaining fifty-two single-constant errors         41 .. 46
    the familiar values, filled in from memory             26

The last row is the important one: recognising the domain and filling the
constants in from memory is worse than any single-constant slip, because ten of
the twelve are wrong at once.
