# dynamo/hai-surveillance-adjudication

A surveillance definitions manual with its twelve constants redacted, a prior
quarter of 59 admissions published only as a summary table — counts per ward per
month, three of the numbers wrong and which ones not recorded — and a held-out
quarter of 49 patients to adjudicate. Recover the constants from the table, then
adjudicate the held-out quarter.

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
    environment/data/audited.json   the prior quarter: admissions + published summary
    environment/data/records.json   the held-out quarter to adjudicate
    solution/solve.sh               oracle entrypoint
    solution/solve.py               reference adjudicator, standard library only
    tests/test.sh                   verifier entrypoint, writes reward.txt and ctrf.json
    tests/pytest.ini                pinned config, so rootdir cannot be hijacked
    tests/test_outputs.py           the two graded criteria
    tests/expected.json             answer key plus patient and ward order

`tests/` is overlaid at `/tests` only at verification time. Nothing in it ever
reaches the agent image, and `environment/Dockerfile` never copies `solution/`
or `tests/`.

The entrypoint is hardened so a submission cannot grade itself. Harbor runs it
with the agent's own directory as the working directory, and CPython puts the
working directory first on the import path — so a `json.py` the agent wrote gets
imported inside the verifier. Planting one confirmed it: the previous entrypoint
executed it. Now the entrypoint runs from a fresh directory of its own, `python3
-I` keeps the working directory and the user site off `sys.path` and ignores
every `PYTHON*` variable, `-c` and `--confcutdir` pin the config and conftest
search to `tests/`, the cache provider is off, and both output files are deleted
before being written so a symlink in their place is removed rather than followed.
Re-measured against the real container layout: correct answer 1, wrong answer 0,
planted module not imported, symlinked `reward.txt` replaced.

## What makes it hard

- **The audit publishes counts, not answers.** Fifty-nine admissions collapse
  into fifteen cells: per ward, per month, how many urinary events, how many
  bloodstream events, how many of those were line-associated. Forty-five numbers
  in all. There is no patient to open, no date to compare, no organism list to
  diff. A cell one too high says something in that ward that month adjudicated
  differently, and says nothing about whether the cause was a wrong constant or
  a rule of the manual read wrongly. **Fitting cannot be turned into
  debugging** — which is exactly what an audit of worked adjudications quietly
  allows.
- **The constants are not the familiar ones.** Ten of the twelve differ from the
  values the well-known national definitions use. A solver that fills all twelve
  in from memory gets **28 of the 49** held-out patients right and reproduces
  only 11 of the 45 published numbers, against the recovered setting's 42.
- **The search has to be framed.** The grid holding the answer has
  **148,500,000** settings. Staged by what each constant can reach — five decide
  which candidates exist, four decide which are reported and when, three decide
  only ward and line association — it comes down to 1,188,000 pool-and-walk
  settings, and a bound on the last three keeps the full scoring to a handful.
- **Two rules bite that no count announces.** A blood culture growing three or
  more organism names is disregarded in full; *Candida* is a recognised pathogen
  in blood but is not eligible for a urinary event. Miss either and the
  predicted table cannot be made to match, the constants recovered from it are
  wrong, and two held-out patients are wrong on top.
- **The table is not clean.** Three published numbers are wrong, so no setting
  reproduces it and a search demanding one finds nothing. The recovery has to
  score agreement and check the winner wins outright.
- **Nothing checks the fit on the held-out quarter.** A setting that matches the
  table and is still wrong produces a complete, coherent, plausible adjudication
  that no part of the data contradicts.

## Well-posedness

Four checks, run together, each of which has rejected a design.

*Reach.* Every one of the 57 single-constant errors moves at least one published
number. A constant the table cannot see is not recoverable from it — this check
rejected the first version of this design, where eight errors were invisible to
a table of counts.

*Uniqueness.* The grid of **148,500,000 settings**, wider than the truth in
every direction on every axis, exhausted against the published table: **exactly
one** setting matches the most numbers — 42 of 45, the setting the data was
generated from — and no other setting reached that score at all.

*Inexplicable errors.* On a table of counts this is sharper than it was on
worked adjudications. The truth matches every number but the three wrong ones,
so a setting that predicts a wrong number where it is published — and differs
nowhere else — would tie or win. The corrupted positions are therefore chosen so
that no single-constant error predicts the value published there, and so that no
single-constant error confines all of its changes to those positions. Both are
checked rather than assumed.

*Held-out reach.* Every one of the 57 single-constant errors changes the
adjudication of at least one held-out patient, so no recovered value is
decorative.

## What was rejected on the way

Two designs failed uniqueness on a per-patient audit. One left two survivors
differing in where the attribution period opens, because that discriminator had
its sign exactly at the window edge, where both readings land on the same day.
One let a wrong setting explain more entries than the truth: a mis-recorded line
flag and a ward charged to the receiving unit are exactly what two wrong
constants predict, so an error a wrong setting can explain is evidence for that
setting, not noise.

Two failed on separability. One was built as contrastive twins — two patients
identical but for one element — which pinned the constants uniquely but let each
be read off one pair. Randomising every offset to destroy the twins destroyed
the information with them: charts away from a boundary pin nothing, and 168 to
792 settings tied.

The fifth is the one that matters here. Charts stacked on several boundaries at
once fixed separability and left the task no harder, because separability was
never what made it tractable. Worked adjudications are a test suite: implement
the procedure, score it, see which patients disagree, open one, find the rule
you read wrongly, fix it, score again. Publishing counts removes that loop while
leaving the constants recoverable, which is the whole of this design.

## Dev tooling (not shipped)

Lives in `dev7/`, outside this directory:

    params.py        the procedure with all twelve constants left free
    gen6.py          the shipped data: admissions, published table, key, checks
    gen5.py          the chart shapes, and the stacked-boundary audit design
    gen2.py          the ordinary admissions, and the contrastive-twin design
    gen3.py, gen4.py the randomised and stacked designs, kept as a record
    controls3.py     scores each mis-recovered constant on table and held-out
    harness.py       runs the verifier against the oracle and against wrong answers

## Measured

    oracle                                      1.0, byte-identical across re-runs
    no file / empty / nothing reported          0
    all denominators zero / symlinked answer    0
    schema and single-determination faults      0

One constant recovered wrongly, by held-out patients still fully correct out of
49. Grading is all-or-nothing, so every row below scores zero, and every row
also misses at least one published number:

    events dated by the anchor, not the earliest element   35
    window reaching only one day back                      38
    transfer rule at nought days / at one day              39 / 40
    line required in place six days                        41
    admission day 6 the first that counts                  42
    the remaining fifty-one single-constant errors         43 .. 48
    the familiar values, filled in from memory             28

The last row is the important one: recognising the domain and filling the
constants in from memory is worse than any single-constant slip, because ten of
the twelve are wrong at once.
