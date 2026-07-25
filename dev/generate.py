"""Deterministic dataset generator for the ecdsa-nonce-lattice task.

Fixed seed => byte-identical output on every run and every platform (all
randomness derives from SHA-256 of a fixed seed + counter, so there is no
dependence on the interpreter's RNG implementation).

Nonce model: every ephemeral nonce is k_i = A + e_i, where A is a single
unknown base with full ~256-bit entropy and 0 <= e_i < 2^W. Only public
material is emitted: curve name, public key Q, the window width W, and the
(h, r, s) triples. The private key, A, and the offsets are secret generation
state and are NOT written to the task tree.

Why this model rather than "the top B bits of every nonce are stuck":
  With a shared B-bit prefix, the unknown is only B bits wide, so the intended
  differencing reduction can be bypassed by enumerating all 2^B candidate
  prefixes and solving an ordinary zero-MSB HNP for each. Making the base a
  full-entropy value decouples the two quantities: guessing A is 2^256 work
  (infeasible by construction, not by parameter choice), while the information
  gained per differenced pair stays at 256-W = 8 bits, which keeps the lattice
  tight.

Parameter notes:
  W = 248 leaves 8 bits of leakage per pair, so the lattice needs > 32
  differenced equations. M = 40 sits just above that cliff (margin ~1.22):
  the golden attack succeeds, whereas the same construction at M = 36 fails
  even under BKZ-20, and an unscaled lattice fails at every M tested.
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")
from secp256k1 import N, G, scalar_mult, inv_mod, pubkey

SEED = b"dynamo/ecdsa-nonce-lattice/v3"
W = 248          # window width exponent: 0 <= e_i < 2^W
M = 40           # number of signatures emitted


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

    # Unknown window base A, chosen so every nonce stays a valid scalar:
    # 1 <= A and A + 2^W <= N.
    A = det_rand_int("base", 256) % (N - (1 << W) - 1) + 1

    sigs = []
    used_r = set()
    idx = 0
    while len(sigs) < M:
        h = det_rand_int(f"hash{idx}", 256) % N
        e = det_rand_int(f"jit{idx}", W)
        k = A + e
        idx += 1
        if not (1 <= k < N):
            continue
        R = scalar_mult(k, G)
        r = R[0] % N
        if r == 0 or r in used_r:
            continue
        s = (inv_mod(k, N) * (h + r * d)) % N
        if s == 0:
            continue
        used_r.add(r)
        sigs.append({"h": hex(h), "r": hex(r), "s": hex(s)})

    public = {
        "curve": "secp256k1",
        "public_key": {"x": hex(Q[0]), "y": hex(Q[1])},
        "nonce_window_bits": W,
        "signatures": sigs,
    }
    secret = {"private_key": hex(d), "window_base": hex(A)}
    return public, secret


if __name__ == "__main__":
    public, secret = gen()
    with open("signatures.json", "w") as f:
        json.dump(public, f, indent=2)
    with open("_secret_answer.json", "w") as f:
        json.dump(secret, f, indent=2)
    print("wrote signatures.json (%d sigs, W=%d)" % (len(public["signatures"]), W))
    print("Q.x =", public["public_key"]["x"])
    print("Q.y =", public["public_key"]["y"])
