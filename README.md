# dynamo/ecdsa-nonce-lattice

**Category:** Security / Cryptanalysis

## Overview

The agent audits an ECDSA (secp256k1) signing service with a faulty random number
generator. It is given the public evidence in `/app/data/signatures.json` — the
curve, the signer's public key `Q`, and 16 signature triples `(h, r, s)` — and must
recover the signer's long-term private key `d`, writing it to `/app/result.json` as
`{"private_key": "<hex>"}`.

The RNG fault is a stuck high prefix: every ephemeral nonce is a 255-bit integer whose
**top 24 bits are the same unknown constant**. This is partial nonce leakage, the same
class of break as the real-world Minerva, TPM-FAIL, and LadderLeak attacks, and it is
the daily work of an applied cryptanalyst auditing a signer.

## Approach

The corpus contains no repeated `r`, so the elementary "two signatures shared a
nonce" break does not apply. The intended solution is a Hidden Number Problem (HNP)
lattice attack:

1. Rewrite each signature as `k_i ≡ a_i + t_i·d (mod n)` with `a_i = s_i⁻¹h_i` and
   `t_i = s_i⁻¹r_i`.
2. Because every nonce shares the same unknown top bits, **difference the equations
   against a pivot signature** to cancel that shared prefix, leaving
   `(k_i − k_0) ≡ (a_i − a_0) + (t_i − t_0)d (mod n)` with `|k_i − k_0| < 2²³¹`.
3. Build a Boneh–Venkatesan lattice from the differenced pairs, scaling the residue
   rows by `n // 2²³¹` so the target vector is balanced.
4. Run LLL, read `d` off the short vector, and confirm with `d·G == Q`.

The decisive step is (2). Every widely documented biased-nonce lattice attack assumes
the leaked high bits are *zero* ("short nonces"); here they are a nonzero **unknown**
constant, so the textbook lattice has no short vector at the true solution and returns
a wrong key. The reference solution (`task/solution/solve.py`, called by `solve.sh`)
recovers the key in a tenth of a second with `fpylll`.

Two shortcuts are deliberately closed. The prefix is 24 bits wide, so enumerating its
2²⁴ (~16.8M) possible values and solving a standard zero-MSB HNP for each is
computationally infeasible — a measured sweep would take on the order of a thousand
hours against a 1800-second budget. And only 16 signatures are supplied, about 1.4×
the information the lattice minimally needs, so a wrongly scaled or wrongly oriented
lattice fails rather than being rescued by surplus data.

## Environment

`task/environment/Dockerfile` builds the single image used by both the agent and the
verifier, from the pre-approved digest-pinned `python:3.13-slim-bookworm`. It bakes in
`fpylll` (lattice reduction), `ecdsa`, and `pytest` + `pytest-json-ctrf`, all pinned,
so the verifier installs nothing at verify time.

Only the **public** corpus is copied into the image
(`task/environment/data/signatures.json`). The private key, the nonce prefix, and the
generator seed are never present — the dataset is synthetic and was generated
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
