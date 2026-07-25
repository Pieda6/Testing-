"""Reference solver for dynamo/ecdsa-nonce-lattice.

Four mechanisms must all be handled or the lattice silently misses the target:

  1. Each nonce is k = A_g + e with 0 <= e < 2^(W_g). A_g has full ~256-bit
     entropy, so it cannot be guessed; it is cancelled algebraically by
     differencing.
  2. The base A_g is PER SESSION, so differencing is only valid between records
     of the same session. A single global pivot mixes unrelated bases and the
     resulting rows are not small.
  3. Records flagged s_low_normalized store n - s_true, which describes -k
     instead of +k; the normalisation is undone before use.
  4. Each session has its OWN window WIDTH, so every differenced row carries its
     own bound and must be scaled individually. No uniform K works: the widest
     window starves the lattice of information, and any narrower choice is
     violated by the true offsets of the wider sessions.

The differenced system is a standard Hidden Number Problem, which a correctly
scaled Boneh-Venkatesan lattice plus LLL then solves.

No seed, generator, or answer key is consulted -- only the public corpus at
/app/data/signatures.json.
"""
import json
from collections import defaultdict

from fpylll import IntegerMatrix, LLL

# --- secp256k1 (self-contained) -------------------------------------------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def inv(x, m):
    return pow(x % m, -1, m)


def padd(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x1, y1 = a
    x2, y2 = b
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if a == b:
        lam = (3 * x1 * x1) * inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def mul(k, pt):
    k %= N
    r = None
    a = pt
    while k:
        if k & 1:
            r = padd(r, a)
        a = padd(a, a)
        k >>= 1
    return r


G = (GX, GY)


def equations(sigs, widths):
    """Return differenced (A, T, K) lists, where K_i bounds row i's offset."""
    a, t = {}, {}
    for j, sg in enumerate(sigs):
        s = int(sg["s"], 16)
        if sg["s_low_normalized"]:
            s = (N - s) % N            # mechanism 3: undo the normalisation
        si = inv(s, N)
        a[j] = si * int(sg["h"], 16) % N
        t[j] = si * int(sg["r"], 16) % N

    by_session = defaultdict(list)
    for j, sg in enumerate(sigs):
        by_session[sg["session"]].append(j)

    A, T, K = [], [], []
    for g, idxs in sorted(by_session.items()):
        pivot = idxs[0]                # mechanism 2: pivot within the session
        bound = 1 << widths[str(g)]    # mechanism 4: this session's own width
        for j in idxs[1:]:
            A.append((a[j] - a[pivot]) % N)
            T.append((t[j] - t[pivot]) % N)
            K.append(bound)
    return A, T, K


def recover(pub):
    Q = (int(pub["public_key"]["x"], 16), int(pub["public_key"]["y"], 16))
    A, T, K = equations(pub["signatures"], pub["session_window_bits"])
    m = len(A)

    # Balanced Boneh-Venkatesan lattice. Each residue column is scaled by its
    # OWN factor F_i = N // K_i, so every coordinate of the target vector is
    # ~N regardless of which session the row came from.
    F = [N // k for k in K]
    dim = m + 2
    Bm = IntegerMatrix(dim, dim)
    for i in range(m):
        Bm[i, i] = F[i] * N
    for i in range(m):
        Bm[m, i] = F[i] * T[i]
    Bm[m, m] = 1
    for i in range(m):
        Bm[m + 1, i] = F[i] * A[i]
    Bm[m + 1, m + 1] = N
    LLL.reduction(Bm)

    # The private key appears (up to sign) as the m-th coordinate of a short row.
    for row in Bm:
        for cand in (row[m] % N, (-row[m]) % N):
            if cand and mul(cand, G) == Q:
                return cand
    return None


def main():
    with open("/app/data/signatures.json") as f:
        pub = json.load(f)
    d = recover(pub)
    if d is None:
        raise SystemExit("lattice attack failed to recover the key")
    with open("/app/result.json", "w") as f:
        json.dump({"private_key": hex(d)}, f)
    print("recovered private key -> /app/result.json")


if __name__ == "__main__":
    main()
