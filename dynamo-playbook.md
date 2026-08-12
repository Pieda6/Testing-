# Dynamo playbook

What was learned building `dynamo/schedule-recovery` and
`dynamo/hai-surveillance-adjudication`, written down so the next task does not
repeat it. The second one took five redesigns to clear the difficulty gate and
most of them were wasted; the reason they were wasted is the first section.

## 1. What actually makes a task hard

**A task is easy when being wrong tells the agent how to fix it.**

That is the whole finding, and it took four measured attempts to see. The
surveillance task shipped an audit of 39 worked examples — one per patient, in
exactly the shape the agent had to produce. That is a test suite. The loop it
allows is: implement the procedure, score it, see which patients disagree, open
one, find the rule you misread, fix it, score again. A competent agent walks
that loop inside the hour no matter how obscure the rules are.

Everything tried against that structure failed to move the number:

    audit of contrastive twins, familiar constants        solved 2/5
    conjunctive audit, no pair isolates a constant        solved 3/5
    ten of twelve constants unfamiliar, 148.5M grid       solved 4/5

Nine of fifteen trials. With n=5 those three are statistically identical — the
interventions did nothing. Non-separability, unfamiliar values and a 30× bigger
search space are all *inference* levers, and inference is what these agents are
good at.

What worked was changing the **feedback signal**. The audit stopped publishing
adjudications and started publishing what a surveillance programme actually
publishes: a summary table of counts, per ward per month. Fifty-nine admissions
collapsed into forty-five numbers. The constants stayed recoverable — proved by
exhaustion — but a cell that is one too high says *something in that ward that
month adjudicated differently* and says nothing about whether the cause was a
wrong constant or a misread rule. There is no patient to open. Fitting cannot
be turned into debugging.

**Design question to ask first, before any content:** when the agent is wrong,
what does it learn? If the answer is "which item it got wrong", the task is a
debugging exercise. Make the observable lossy — aggregate it, or make it a
single scalar the agent cannot decompose — while keeping the answer uniquely
determined.

Both tasks that passed on the first attempt (`legacy-tag-forge`,
`headerless-pcm-normalize`) have this property natively: a bad tag recovery or a
bad normalisation gives no signal about which step was wrong.

## 2. The gate arithmetic, exactly

    pass@5 gate: need (good_valid + soft_timeout) >= 3 of 5, with >= 1 good_valid

Consequences that are easy to get backwards, and that I got backwards twice:

- **Soft timeouts count.** A run that hits the agent timeout is a countable
  failure. A hard crash, an infra error or a run with nothing on disk is
  *invalid* and counts for nothing.
- **All-timeouts fails too**, because of the `>= 1 good_valid` clause. The
  oracle must be comfortably inside the budget so that a correct-but-slower
  agent still finishes and gets graded — that is where the valid failures come
  from. 445s against 3600s worked; 12% of the clock.
- **A single valid failure is not enough.** Every failing run produced exactly
  one. Three are needed. That means the solve rate has to come down to roughly
  20–30%, which is not a tuning problem — it is a change of task shape.
- **n=5 has an error bar of about ±0.2.** Do not redesign on the strength of one
  run moving 2/5 to 3/5. Compare against the pooled rate.

Two things that are never acceptable: lowering `[agent] timeout_sec` to force
timeouts, and padding the task with busywork. Both convert valid outcomes into
invalid ones and were refused.

## 3. Prove well-posedness; never assume it

Every shipped dataset should be gated by named checks that the generator runs
and that can *reject a design*. For a recover-the-parameters task these are:

| check | question | rejected |
|---|---|---|
| **uniqueness** | does exactly one setting explain the observable best? | 2 designs |
| **reach** | does every single-parameter error move the observable at all? | 1 design |
| **non-separability** | is every item sensitive to ≥3 parameters? *(per-item feedback only)* | 1 design |
| **held-out reach** | does every single-parameter error change ≥1 graded item? | tuned 3× |
| **inexplicable errors** | can a wrong setting explain a planted error? | 1 design |

Notes earned the hard way:

- **Uniqueness and non-separability are different properties.** Contrastive
  twins give the first and destroy the second. Randomising every offset to kill
  the twins destroys the *information* too — items away from a boundary pin
  nothing, and 168 to 792 settings tied. Stack several boundaries on each item
  instead: informative and conjunctive at once.
- **A planted error a wrong setting can explain is evidence for that setting,
  not noise.** A mis-recorded line flag and a ward charged to the receiving unit
  are exactly what two wrong constants predict, so that wrong setting beat the
  truth. Corruptions must be inexplicable under *any* setting, and must fall on
  items that pin nothing — corrupting a discriminator destroys its evidence too.
- **On aggregate observables the corruption rule gets sharper.** The truth
  matches everything except the planted errors, so a setting that predicts a
  planted value *and differs nowhere else* ties or wins. Two conditions, both
  checked: at each corrupted position no single-parameter error predicts the
  published value, and no single-parameter error confines all its changes to
  the corrupted positions.
- **Express every offset in the generator as a delta from the constant it
  probes** (`H - 1`, `R - 1`, `LM - 2`). Then changing the constants moves every
  boundary automatically, and re-tuning is free.
- **Seed the verification sweep with the truth's own score** so the prune bites
  from the first iteration — 397s instead of hours. Then dedupe the winners, or
  reaching the seed reads as a two-way tie.

## 4. Verifier hardening (this blocked a submission)

`python3 -m pytest` puts the **current working directory first on `sys.path`**,
and Harbor invokes `tests/test.sh` with the *agent's* directory as the working
directory. A `json.py` written by the agent is therefore imported inside the
verifier's process. Confirmed by planting one: the old entrypoint executed it.

The hardened entrypoint:

```bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/ctrf.json   # kill any symlink

WORK="$(mktemp -d)"                # never $TMPDIR — python and mktemp read it
trap 'rm -rf "${WORK}"' EXIT
cd "${WORK}" || exit 1

python3 -I -m pytest "${HERE}/test_outputs.py" -v \
    -c "${HERE}/pytest.ini" \
    --confcutdir="${HERE}" \
    -p no:cacheprovider \
    --ctrf "${WORK}/ctrf.json"
rc=$?
# ... write reward to ${WORK} then mv into /logs/verifier
```

Each flag closes a different door, and an isolated CWD alone closes only the
first:

- `mktemp -d` + `cd` — nothing the agent wrote is in the working directory
- `-I` — working directory and user site off `sys.path`, all `PYTHON*` ignored
- `-c` — rootdir pinned, so a `pytest.ini` planted above `/tests` cannot set
  `addopts` and load a plugin
- `--confcutdir` — a `conftest.py` planted above `/tests` is not executed
- `-p no:cacheprovider` — pytest writes nothing outside `/logs`
- `rm -f` then write-and-move — a symlink left at `reward.txt` is deleted, not
  written through

Also: open **both** files the verifier reads with `O_NOFOLLOW` — the agent's
result and the answer key.

Verify it, don't assert it. Mirror the real layout (`/app` with hostile files in
it, `/tests` overlaid, `/logs`) and measure: correct → 1, wrong → 0, planted
module not imported, symlinked `reward.txt` replaced.

## 5. Mechanical failures that cost whole cycles

- **Never drag a file into the GitHub web editor.** It inserts a
  `https://github.com/user-attachments/...` markdown link as line 1. That failed
  review twice. Use *Add file → Upload files*, or open and paste.
- **No pipeline meta-commentary in `README.md`.** "Why v1 failed", "pass@2 solved
  it twice" — that is a review FAIL. Neither passing task has any.
- **Never substitute short tokens into prose.** A templating script replaced the
  placeholder `LO` with `35` and shipped `O_NOFOL35W`, because `O_NOFOLLOW`
  contains those letters. Use `{{LO}}` or substitute structurally.
- `[task].description` is required. Both passing tasks carry it.
- apt packages **un**pinned, pip packages pinned, `artifacts` at top level,
  `apt-get update` and `rm -rf /var/lib/apt/lists/*` in the same layer.
- `instruction.md` ≤ 1500 Qwen3 tokens (≈ 1.59 tokens/word, so ≤ ~940 words).
- Run `preflight.py <taskdir>` before every upload. It catches the mechanical
  rubric failures locally; extend it whenever a new one is found.

## 6. Reading the pipeline when it fails

Stage order, and the aggregate gate reports each one:

    review · similarity · validation · pass2 · tier1 · qc_gate · deep_review
    · ava_review · trials

- **`trials` is where the pass@5 difficulty gate lives.** If `trials=skipped`,
  difficulty was never tested — something earlier blocked.
- **`qc_gate` consolidates two routings**: `qc_eval` (task soundness, from the
  static-eval artifact) and `qc_exec` (the execution probe). `qc_exec=PASS` means
  the build, oracle and verifier are all fine.
- **The itemised reasons are only in the QC comment on the PR.** It is a *sticky*
  comment — the bot edits its existing one in place, so on a long thread it is
  **not at the bottom**. Expand the collapsed "N hidden items" section first,
  then search for `Per-Check QC`.
- Get the actual list before changing anything. Four rounds were spent guessing
  at causes that turned out to be noise.

## 7. Process

- **Read the tasks that passed** rather than reasoning from memory about them. A
  claim about what they contain, made from memory, was wrong twice — including
  once where a `grep -A1` cut off the line being quoted.
- Keep failed designs in `dev*/` with the dead end recorded in the docstring.
  `gen3.py` (randomised, 168–792 ties) is worth more than a passing file: it is
  the evidence that a plausible fix does not work.
- Every claim in `task.toml` should be a measured number with a script behind
  it. Reviewers read those explanations closely, and a wrong figure there is a
  defect in the submission.

## 8. Repairing a task that failed the difficulty gate

From `repair-mpmc-ring`, which failed pass@2. It looked like the most elaborate
task in the set: a 2,155-line verifier, a 10KB normative spec, eleven gated
concurrency scenarios, a `difficulty_explanation` claiming batch ownership,
stale-candidate races, wraparound, and shutdown races. It was solved because the
shipped artifact was already right.

- **Before theorising, run the shipped artifact against the shipped verifier.**
  Nine of eleven scenarios passed as it stood. The two that failed were the same
  conceptual defect in two symmetric places. Thirty seconds of measurement
  replaced a day of guessing, and it also ruled out the other hypothesis —
  flakiness — before any code was written.
- **Then write the winning patch yourself, from the spec only.** A retry loop
  around the ownership exchange, about fifty lines, scored full reward first
  try. That is the difficulty gate's verdict, obtained locally in minutes
  instead of a CI round trip. If a patch you can write in one pass scores 1, the
  gate will say so too.
- **A near-correct starting artifact is the characteristic failure of a repair
  task.** The distance between what ships and what is correct *is* the task.
  Nothing in `difficulty_explanation` changes that distance; the reference
  solution's diff against the shipped file measures it. Here that diff was one
  fix expressed twice, while the prose claimed six independent axes.
- **A complete normative spec is a checklist, so difficulty has to come from
  requirements that pull against each other.** The useful defects are the ones
  where the natural repair of A violates B: a retry loop that re-fires a
  once-only hook, a lock that makes `close()` block behind a stalled producer.
  Build those wrong repairs and measure them. Two of the three forbidden repairs
  here were things I would have written myself.
- **Prefer defects that cannot be patched in place.** Ordered publication and
  capacity-from-ownership each have to be replaced by a different mechanism, not
  edited. That is what makes the intended solution a design rather than an edit,
  and it is what survives a strong model rewriting the file from scratch.
- **Check the verifier against the spec in both directions.** One scenario
  required a stalled owner's successor to *complete*; the spec only promised it
  would *acquire*. An implementation that did exactly what the spec said would
  have been graded wrong — a false negative that reads as a verifier bug. Grading
  stricter than the contract is as much a defect as grading looser.
- **Some real violations cannot be graded, and planting them is worse than
  leaving them out.** Three requirements — payload before publication, no
  visible prefix of a batch, payload before release — were built as defects and
  all scored 1, because the hook set has no observation point inside the
  payload-and-publication window. Same shape as the `ar` flag in
  reproducible-release-bundle: measured inert, documented, dropped. A defect the
  harness cannot see is a requirement the agent need not meet.
- **When the graded artifact is code the verifier compiles and runs, the
  submission is inside the verifier's process.** A static initialiser calling
  `std::_Exit(0)` passed all eleven scenarios. The fix is a token the verifier
  chooses after the build and each scenario must echo on completion: exiting zero
  is something the submission can do for itself, finishing the scenario is not.
- **Measure flakiness instead of worrying about it.** Compile once, then run each
  scenario hundreds of times, idle and with twice as many spinning processes as
  cores. Worst case here was 0.07s against gates of 700ms — a 10× margin, and
  proof that the gate failure was difficulty rather than a noisy runner. Timed
  gates in a concurrency verifier are exactly where an oracle intermittently
  fails its own tests, which the rubric rejects outright.
