# dynamo/ecdsa-nonce-lattice

A Terminal-Bench 2 (Harbor) cryptanalysis task. The agent is given a corpus of
ECDSA/secp256k1 signatures produced by a faulty signer whose ephemeral nonces all
share the same secret high bits, and must recover the signer's long-term private
key.

## Overview

- **Category / sub-category:** Security / Cryptanalysis.
- **Problem:** recover the private key `d` from public signatures and the public
  key `Q = d·G`.
- **Deliverable:** `/app/result.json` = `{"private_key": "<hex>"}`.

The corpus contains no nonce reuse, so the elementary two-signatures-share-a-nonce
break does not apply. Instead the RNG fault is a **stuck high byte**: every nonce
`k` is a 255-bit integer whose top 8 bits are the same unknown constant. This is a
partial-nonce-leakage break in the same family as the real-world Minerva, TPM-FAIL,
and LadderLeak attacks.

## Why it's hard

Every widely documented biased-nonce lattice attack assumes the leaked high bits
are **zero** ("short nonces"). Here they are a nonzero **unknown** shared constant,
so the textbook lattice has no short vector at the true solution and returns a wrong
key — which the agent can detect only if it bothers to check `d·G == Q`. The
decisive, non-templated step is to **difference the signature equations** to cancel
the unknown shared prefix, producing a standard Hidden Number Problem (HNP), then to
build and correctly scale a Boneh–Venkatesan lattice with enough samples. Stating
this in the instruction does not trivialize the task: the reduction and the lattice
scaling are the real cryptanalytic work.

## Approach (reference solution)

For each signature, `k_i ≡ a_i + t_i·d (mod n)` with `a_i = s_i⁻¹h_i`,
`t_i = s_i⁻¹r_i`. Differencing against a pivot signature cancels the shared high
part: `(k_i − k_0) ≡ (a_i − a_0) + (t_i − t_0)d (mod n)` with `|k_i − k_0| < 2²⁴⁷`.
Build an HNP lattice from the differenced pairs, scale the residue rows by
`n // 2²⁴⁷` so the target vector is balanced, run LLL, read `d` off the short
vector, and confirm with `d·G == Q`. It runs in well under a second with `fpylll`.

See `task/solution/solve.sh`.

## Environment

- Base image `python:3.13-slim-bookworm`, pinned by digest.
- `fpylll` (LLL/BKZ) and `ecdsa` provided for the agent; `pytest` +
  `pytest-json-ctrf` baked in for the verifier. No network needed at runtime.
- Only the **public** corpus (`task/environment/data/signatures.json`) is copied
  into the agent image — never the generator, seed, nonce prefix, or private key.

## Verification

`task/tests/test_outputs.py` embeds only the signer's **public** key `Q` (immutable,
public information) and independently recomputes `d·G` on secp256k1, asserting it
equals `Q`. Because finding `d` with `d·G == Q` is the discrete-log problem itself,
a false accept is impossible and no private key is stored in the image. The verifier
also pins the output schema (JSON object; `private_key` must be a hex string
decoding to `1 ≤ d < n`; JSON numbers / NaN / Infinity rejected) and opens the result
path with `O_NOFOLLOW` to block symlink aliasing.

## Reproducing the corpus

The dataset is generated deterministically (all randomness derives from SHA-256 of a
fixed seed, so it is byte-identical on every platform):

```bash
cd dev && python3 generate.py   # writes signatures.json (+ a dev-only secret file)
```

## Calibration

- `harbor run -p task --agent oracle` → reward `1.0`.
- `harbor run -p task --agent nop`    → reward `0`.

Difficulty (≥ 4/8 valid failures with GPT-5.4 xhigh via Terminus-2) is confirmed at
the Pass@8 stage.
