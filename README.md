# dynamo/ecdsa-nonce-lattice

**Category:** Security / Cryptanalysis

## Overview

The agent audits an ECDSA (secp256k1) signing service with a faulty random number
generator. It is given the public evidence in `/app/data/signatures.json` — the
curve, the signer's public key `Q`, and 44 signature records — and must
recover the signer's long-term private key `d`, writing it to `/app/result.json` as
`{"private_key": "<hex>"}`.

The RNG fault is a stuck window: every nonce of a session lies in
`[A_g, A_g + 2²⁴⁸)` for a base `A_g` of the same magnitude as the group order —
unknown, and different for every session. This is partial nonce leakage, the same
class of break as the real-world Minerva, TPM-FAIL, and LadderLeak attacks, and it is
the daily work of an applied cryptanalyst auditing a signer.

## Approach

The corpus contains no repeated `r`, so the elementary "two signatures shared a
nonce" break does not apply. Three independent mechanisms must all be handled before
the lattice finds anything, and each fails *silently* rather than raising an error:

1. **Unknown window base.** `A_g` has full ~256-bit entropy, so it cannot be guessed
   or enumerated — it has to be cancelled algebraically by differencing signature
   equations. (Had the fault been a stuck *B*-bit prefix, an agent could skip the
   reduction entirely and try all 2^*B* candidates.)
2. **Per-session bases.** Differencing is only valid *within* a session. The
   templated single-global-pivot recipe mixes unrelated bases and yields rows that
   are not small.
3. **Low-s normalization.** Records flagged `s_low_normalized` store `n − s_true`,
   so those equations describe `−k` rather than `+k` — a real-world BIP-62 footgun
   that silently corrupts a third of the system.

The reference solution (`task/solution/solve.py`, called by `solve.sh`):

1. Undo the normalization where flagged, then form `a_j = s_true⁻¹h_j` and
   `t_j = s_true⁻¹r_j`, so `k_j ≡ a_j + t_j·d (mod n)`.
2. Group by session and difference each session against its own pivot, cancelling
   `A_g` and leaving `|k_j − k_p| < 2²⁴⁸`.
3. Stack all 40 differenced equations into one Boneh–Venkatesan lattice, scaling the
   residue rows by `n // 2²⁴⁸` so the target vector is balanced.
4. Run LLL, read `d` off the short vector, and confirm `d·G == Q`.

It recovers the key in about 0.3 s with `fpylll`.

Grading is all-or-nothing on a single recovered key, so getting two of the three
mechanisms right scores zero. Measured on the shipped data, the correct construction
succeeds while session-blind differencing, ignoring the normalization, and an
unscaled lattice each fail. The window is only 8 bits narrower than `n`, so each
differenced pair yields ~8 bits: 44 records across 4 sessions give 40 equations
(margin ~1.22), and the same construction fails at 36 even under BKZ-20 — while
every valid variant tried (any pivot choice, rounded scale factors, a 2×-off
constant column, BKZ) succeeds, so the margin punishes wrong methods rather than
merely different ones.

## Environment

`task/environment/Dockerfile` builds the single image used by both the agent and the
verifier, from the pre-approved digest-pinned `python:3.13-slim-bookworm`. It bakes in
`fpylll` (lattice reduction), `ecdsa`, and `pytest` + `pytest-json-ctrf`, all pinned,
so the verifier installs nothing at verify time.

Only the **public** corpus is copied into the image
(`task/environment/data/signatures.json`). The private key, the session window bases,
and the generator seed are never present — the dataset is synthetic and was generated
deterministically from a fixed seed outside the task tree.

## Verification

`task/tests/test.sh` runs `task/tests/test_outputs.py` under pytest and writes `1`/`0`
to `/logs/verifier/reward.txt`. Two tests map 1:1 to the two stated correctness
conditions:

1. **Schema** — `/app/result.json` is a JSON object whose `private_key` is a hex
   *string* decoding to an integer `d` with `1 ≤ d < n` (JSON numbers, NaN, and
   Infinity are rejected). The file is opened with `O_NOFOLLOW` so a symlinked output
   path cannot alias another file.
2. **Correctness** — the verifier independently recomputes `d·G` on secp256k1 and
   asserts it equals the signer's public key `Q`.

Ground truth is only the **public** key `Q`, embedded in the test file. No private key
is stored anywhere in the image. Because finding `d` with `d·G == Q` is the discrete
logarithm problem itself, a false accept is impossible and no tolerance is needed —
grading is exact and deterministic.

## Local calibration

```bash
harbor run -p task --agent oracle   # reward 1.0
harbor run -p task --agent nop      # reward 0
```

Adversarial cases also score 0: a wrong key, a numeric `private_key`, `NaN`, a
decimal-encoded key, and a symlinked output path.
