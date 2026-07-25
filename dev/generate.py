"""Deterministic dataset generator for the ecdsa-nonce-lattice task.

Fixed seed => byte-identical output on every run and every platform (all
randomness derives from SHA-256 of a fixed seed + counter, so there is no
dependence on the interpreter's RNG implementation).

The corpus is a Hidden Number Problem instance with three independent
mechanisms, each fully disclosed in the shipped data but each of which fails
SILENTLY when the templated biased-nonce recipe is applied:

  1. Unknown window base. Nonces are k = A + e with 0 <= e < 2^W, where A has
     full ~256-bit entropy. A cannot be enumerated, so it must be cancelled
     algebraically by differencing signature equations. (A stuck B-bit prefix
     would instead let an agent skip the reduction and try all 2^B prefixes.)
  2. Per-session bases. The RNG was reseeded between sessions, so each session
     has its OWN unrelated base. Differencing must happen within a session; a
     single global pivot yields rows that are not small, and the lattice fails.
  3. Low-s normalisation. Some records were stored BIP-62 style with
     s_recorded = n - s_true. Those equations describe -k rather than +k and
     must be un-normalised first.

Each mechanism is announced by an explicit field, so everything the verifier
grades is derivable from what the agent can see.

Parameter notes:
  W = 248 leaves 8 bits of leakage per differenced pair, so the lattice needs
  more than 32 equations. M = 44 records across 4 sessions yields M - 4 = 40
  (margin ~1.22), just above the cliff: the same construction fails at 36
  equations even under BKZ-20.
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")
from secp256k1 import N, G, scalar_mult, inv_mod, pubkey

SEED = b"dynamo/ecdsa-nonce-lattice/v4"
W = 248          # window width exponent: 0 <= e < 2^W
SESSIONS = 4     # independent, unrelated window bases
M = 44           # total signatures -> M - SESSIONS = 40 differenced equations


def det_rand_int(counter, nbits):
    """Deterministic pseudo-random nbits integer from SEED + counter."""
    out = b""
    i = 0
    while len(out) * 8 < nbits:
        out += hashlib.sha256(SEED + counter.encode() + i.to_bytes(4, "big")).digest()
        i += 1
    val = int.from_bytes(out, "big")
    return val & ((1 << nbits) - 1)


def gen():
    # Private key in [1, N-1]
    d = det_rand_int("privkey", 256) % (N - 1) + 1
    Q = pubkey(d)

    # One unknown window base per session, each chosen so every nonce stays a
    # valid scalar: 1 <= A and A + 2^W <= N.
    bases = [det_rand_int(f"base{g}", 256) % (N - (1 << W) - 1) + 1
             for g in range(SESSIONS)]

    sigs = []
    used_r = set()
    idx = 0
    while len(sigs) < M:
        g = len(sigs) % SESSIONS          # round-robin session assignment
        h = det_rand_int(f"hash{idx}", 256) % N
        e = det_rand_int(f"jit{idx}", W)
        k = bases[g] + e
        neg = (det_rand_int(f"neg{idx}", 8) % 3) == 0
        idx += 1
        if not (1 <= k < N):
            continue
        R = scalar_mult(k, G)
        r = R[0] % N
        if r == 0 or r in used_r:
            continue
        s_true = (inv_mod(k, N) * (h + r * d)) % N
        if s_true == 0:
            continue
        s_rec = (N - s_true) % N if neg else s_true
        if s_rec == 0:
            continue
        used_r.add(r)
        sigs.append({
            "session": g,
            "h": hex(h),
            "r": hex(r),
            "s": hex(s_rec),
            "s_low_normalized": neg,
        })

    public = {
        "curve": "secp256k1",
        "public_key": {"x": hex(Q[0]), "y": hex(Q[1])},
        "nonce_window_bits": W,
        "signatures": sigs,
    }
    secret = {"private_key": hex(d),
              "session_bases": [hex(b) for b in bases]}
    return public, secret


if __name__ == "__main__":
    public, secret = gen()
    with open("signatures.json", "w") as f:
        json.dump(public, f, indent=2)
    with open("_secret_answer.json", "w") as f:
        json.dump(secret, f, indent=2)
    sigs = public["signatures"]
    print("wrote signatures.json: %d sigs, %d sessions, %d low-s normalized"
          % (len(sigs), SESSIONS, sum(s["s_low_normalized"] for s in sigs)))
    print("Q.x =", public["public_key"]["x"])
    print("Q.y =", public["public_key"]["y"])
