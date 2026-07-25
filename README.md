# dynamo/legacy-tag-forge

**Category:** Security / Cryptanalysis

## Overview

A legacy device-provisioning service stamps every record with a 32-bit
authentication tag. The routine that produces it was written in-house and lost
when the vendor folded — no specification survives. The agent is given the
recovered archive (`/app/data/samples.json`: 400 records with their tags) and 60
unsigned records (`/app/data/challenge.json`), and must demonstrate the scheme is
forgeable by writing correct tags for all 60 to `/app/tags.json`.

## Approach

There is no named attack to reach for — the construction is a one-off, so CRC,
HMAC and hash guesses are dead ends (CRC-32 and truncated SHA-256 of the packed
record both score 0/60 on the shipped data).

The routine is in fact **affine over GF(2)**: each of the 32 tag bits is the XOR
of a fixed secret subset of the record's 128 input bits, optionally complemented.
That has to be noticed from the archive itself — parity relations hold across
triples of records, which no arithmetic or rotation-based checksum would satisfy
— and then rebuilt.

The reference solution (`task/solution/solve.py`, called by `solve.sh`):

1. Pack each record as a 128-bit integer (`serial` lowest, then `batch`, `model`,
   `nonce`) and append a constant term, giving 129 unknowns.
2. For each of the 32 output bits, solve the system over GF(2) by Gaussian
   elimination.
3. Evaluate the recovered form against all 400 rows and count disagreements. A
   large residual means a corrupt row entered the pivot basis, so restart the
   elimination from a different row offset and keep the solution with the
   smallest residual.
4. Evaluate the 32 recovered affine forms on each challenge record.

It runs in about 0.6 s in pure Python.

## Why near-misses fail silently

Two properties, both measured on the shipped data:

- **Corrupt archive rows.** Fewer than ten of the 400 rows carry a corrupt tag
  and their indices are not recorded. A plain elimination over all rows reaches
  full rank and raises nothing — but absorbs corrupt rows into the basis and
  poisons the affected output bits. That naive solve yields **1 of 60** correct
  tags. Only measuring the residual and re-solving recovers the real map.
- **No free self-check.** Grading is on held-out challenge records the agent has
  no tags for, so agreeing with the archive proves nothing and there is nothing
  to iterate against. A nearest-neighbour lookup over the samples scores **0/60**.

Grading is all-or-nothing across all 60 tags; a 59-of-60 submission scores 0.

## Environment

`task/environment/Dockerfile` builds the single image used by both the agent and
the verifier, from the pre-approved digest-pinned `python:3.13-slim-bookworm`. It
bakes in `numpy`, `sympy`, `galois` and `pytest` + `pytest-json-ctrf`, all pinned,
so the verifier installs nothing at verify time.

Only the archive and the unsigned challenge records are copied into the image.
The tag routine, the secret map, the generator seed, and the correct challenge
tags are never present — the dataset is synthetic and was generated
deterministically from a fixed seed outside the task tree.

## Verification

`task/tests/test.sh` runs `task/tests/test_outputs.py` under pytest and writes
`1`/`0` to `/logs/verifier/reward.txt`. Two tests map 1:1 to the two stated
correctness conditions:

1. **Schema** — `/app/tags.json` is a JSON object whose `tags` is an array of
   exactly 60 hex *strings*, each below 2³² (JSON numbers, NaN and Infinity are
   rejected). The file is opened with `O_NOFOLLOW` so a symlinked output path
   cannot alias another file.
2. **Correctness** — all 60 tags are compared exactly against held-out ground
   truth in `tests/expected_tags.json`, which is overlaid only at verification
   time and never copied into the agent image.

No challenge record shares an input vector with any sample, so the tags cannot be
looked up — only a recovered rule generalises. There is no tolerance to calibrate,
because the target is a bit-exact 32-bit value.

## Local calibration

    harbor run -p task --agent oracle   # reward 1.0
    harbor run -p task --agent nop      # reward 0

Also scoring 0, all verified: CRC-32 guess, truncated SHA-256 guess,
nearest-neighbour lookup, all-zero tags, a 59-of-60 near-miss, JSON-number tags,
a wrong-length array, and a symlinked output path.
