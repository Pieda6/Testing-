"""Deterministic dataset generator for the ecdsa-nonce-lattice task.

Fixed seed => byte-identical output on every run and every platform (all
randomness derives from SHA-256 of a fixed seed + counter, so there is no
dependence on the interpreter's RNG implementation).

The corpus is a Hidden Number Problem instance carrying four independent
mechanisms. Each is fully disclosed in the shipped data, and each fails
SILENTLY -- wrong key, no exception -- when the templated biased-nonce recipe
is applied:

  1. Unknown window base. Nonces are k = A_g + e with 0 <= e < 2^(W_g), and A_g
     has full ~256-bit entropy. A_g cannot be enumerated, so it must be
     cancelled algebraically by differencing. (A stuck B-bit prefix would let an
     agent skip the reduction and try all 2^B candidate prefixes instead.)
  2. Per-session bases. The RNG was reseeded between sessions, so each session
     has its OWN unrelated base. Differencing is only valid within a session; a
     single global pivot mixes unrelated bases and the rows are not small.
  3. Low-s normalisation. Some records are stored BIP-62 style with
     s_recorded = n - s_true. Those equations describe -k rather than +k.
  4. Per-session window WIDTHS. Each session's window has its own width, so the
     lattice needs a per-row bound. The widths are chosen so that NO uniform
     choice of K can work: too narrow and the true offsets violate the bound,
     too wide and the lattice is starved of information. With 10 equations per
     session the correct per-row bounds yield 4*10 + 6*10 + 12*10 + 16*10 = 380
     bits against the 256 needed (margin ~1.48), whereas assuming the widest
     window uniformly yields only 4*40 = 160 bits and fails.

Every mechanism is announced by an explicit field, so everything the verifier
grades is derivable from what the agent can see.
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")
from secp256k1 import N, G, scalar_mult, inv_mod, pubkey

SEED = b"dynamo/ecdsa-nonce-lattice/v5"
WIDTHS = {0: 252, 1: 250, 2: 244, 3: 240}   # per-session window width exponents
SESSIONS = 4
M = 44                                       # -> M - SESSIONS = 40 equations


def det_rand_int(counter, nbits):
    """Deterministic pseudo-random nbits integer from SEED + counter."""
    out = b""
    i = 0
    while len(out) * 8 < nbits:
        out += hashlib.sha256(SEED + counter.encode() + i.to_bytes(4, "big")).digest()
        i += 1
    return int.from_bytes(out, "big") & ((1 << nbits) - 1)


def gen():
    d = det_rand_int("privkey", 256) % (N - 1) + 1
    Q = pubkey(d)

    # One unknown base per session, each chosen so every nonce of that session
    # stays a valid scalar: 1 <= A_g and A_g + 2^(W_g) <= N.
    bases = {g: det_rand_int(f"base{g}", 256) % (N - (1 << WIDTHS[g]) - 1) + 1
             for g in range(SESSIONS)}

    sigs = []
    used_r = set()
    idx = 0
    while len(sigs) < M:
        g = len(sigs) % SESSIONS          # round-robin session assignment
        h = det_rand_int(f"hash{idx}", 256) % N
        e = det_rand_int(f"jit{idx}", WIDTHS[g])
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
        "session_window_bits": {str(g): WIDTHS[g] for g in range(SESSIONS)},
        "signatures": sigs,
    }
    secret = {"private_key": hex(d),
              "session_bases": {str(g): hex(bases[g]) for g in range(SESSIONS)}}
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
