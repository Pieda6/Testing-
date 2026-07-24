"""Deterministic dataset generator for the ecdsa-nonce-lattice task.

Fixed seed => byte-identical output on every run and every platform
(all randomness derives from SHA-256 of a fixed seed + counter, so there is
no dependence on the interpreter's RNG implementation).

Produces an ECDSA/secp256k1 corpus in which every ephemeral nonce shares the
same secret top `B_LEAK` bits (a stuck high-order prefix). The private key,
the true prefix, and the nonces are the SECRET generation state and are NOT
emitted. Only public material is written: curve name, public key Q, and the
(h, r, s) signature triples.

Parameter notes:
  B_LEAK = 24 makes exhaustive search over the unknown prefix (2^24 ~ 16.8M
  lattice reductions) infeasible within the agent budget, so the intended
  differencing reduction is the only practical route.
  M = 16 leaves a ~1.4x information margin over the ~11 signatures the lattice
  minimally needs: the golden attack solves reliably, while an incorrectly
  scaled lattice still fails.
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")
from secp256k1 import N, G, scalar_mult, inv_mod, pubkey

SEED = b"dynamo/ecdsa-nonce-lattice/v2"
L = 255          # nonce bit-length (255 < N, so every nonce is a valid scalar)
B_LEAK = 24      # shared secret high bits across all nonces (stuck 3-byte prefix)
M = 16           # number of signatures emitted


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

    # Secret shared high prefix (top B_LEAK bits of every nonce)
    prefix = det_rand_int("prefix", B_LEAK)
    low_bits = L - B_LEAK
    prefix_shifted = prefix << low_bits

    sigs = []
    used_r = set()
    idx = 0
    while len(sigs) < M:
        h = det_rand_int(f"hash{idx}", 256) % N
        e = det_rand_int(f"nonce{idx}", low_bits)  # low random part
        k = prefix_shifted + e
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
        "nonce_leak_high_bits": B_LEAK,
        "nonce_bit_length": L,
        "signatures": sigs,
    }
    secret = {"private_key": hex(d), "prefix": hex(prefix)}
    return public, secret


if __name__ == "__main__":
    public, secret = gen()
    with open("signatures.json", "w") as f:
        json.dump(public, f, indent=2)
    with open("_secret_answer.json", "w") as f:
        json.dump(secret, f, indent=2)
    print("wrote signatures.json (%d sigs, B_LEAK=%d)" % (len(public["signatures"]), B_LEAK))
    print("secret d =", secret["private_key"])
