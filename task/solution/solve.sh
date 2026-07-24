#!/usr/bin/env bash
# Golden solution for dynamo/ecdsa-nonce-lattice.
#
# Recovers the ECDSA private key from the shared-high-bits nonce corpus by
# reducing to a Hidden Number Problem and running LLL. The decisive step is
# eliminating the *unknown but shared* top bits of the nonces by differencing
# signature equations, which turns the corpus into a standard HNP instance.
# No seed, generator, or answer key is consulted — only the public corpus.
set -euo pipefail

python3 - <<'PY'
import json
from fpylll import IntegerMatrix, LLL

# --- secp256k1 (self-contained) -------------------------------------------
P  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

def inv(x, m): return pow(x % m, -1, m)

def padd(a, b):
    if a is None: return b
    if b is None: return a
    x1, y1 = a; x2, y2 = b
    if x1 == x2 and (y1 + y2) % P == 0: return None
    if a == b:
        lam = (3 * x1 * x1) * inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)

def mul(k, pt):
    k %= N; r = None; a = pt
    while k:
        if k & 1: r = padd(r, a)
        a = padd(a, a); k >>= 1
    return r

G = (GX, GY)

# --- load public corpus ----------------------------------------------------
pub = json.load(open("/app/data/signatures.json"))
Q = (int(pub["public_key"]["x"], 16), int(pub["public_key"]["y"], 16))
L = pub["nonce_bit_length"]
B = pub["nonce_leak_high_bits"]
low = L - B
K = 1 << low                       # bound on |e_i - e_0|
sigs = pub["signatures"]

# k_i = a_i + t_i * d (mod N)
a, t = [], []
for sg in sigs:
    h = int(sg["h"], 16); r = int(sg["r"], 16); s = int(sg["s"], 16)
    si = inv(s, N)
    a.append(si * h % N)
    t.append(si * r % N)

# Difference against index 0 to cancel the shared unknown high part:
#   (k_i - k_0) = (a_i - a_0) + (t_i - t_0) d (mod N),   |k_i - k_0| < K
A = [(a[i] - a[0]) % N for i in range(1, len(sigs))]
T = [(t[i] - t[0]) % N for i in range(1, len(sigs))]
m = len(A)

# Balanced Boneh-Venkatesan lattice: scale residue rows by F=N//K so the
# target vector's coordinates are all ~N.
F = N // K
dim = m + 2
Bm = IntegerMatrix(dim, dim)
for i in range(m):
    Bm[i, i] = F * N
for i in range(m):
    Bm[m, i] = F * T[i]
Bm[m, m] = 1
for i in range(m):
    Bm[m + 1, i] = F * A[i]
Bm[m + 1, m + 1] = F * K
LLL.reduction(Bm)

# The private key appears (up to sign) as the m-th coordinate of a short row.
found = None
for row in Bm:
    for cand in (row[m] % N, (-row[m]) % N):
        if cand and mul(cand, G) == Q:
            found = cand
            break
    if found:
        break

if found is None:
    raise SystemExit("lattice attack failed to recover the key")

json.dump({"private_key": hex(found)}, open("/app/result.json", "w"))
print("recovered private key -> /app/result.json")
PY
