"""Reference solver for dynamo/legacy-tag-forge.

The archive's tag function turns out to be affine over GF(2): every tag bit is
the XOR of a fixed subset of the record's 128 input bits, optionally
complemented. That is discoverable from the archive itself -- parity checks on
triples of records hold, which no CRC-style or arithmetic construction would
satisfy -- and once it is known, each of the 32 output bits is an independent
linear system in 129 unknowns (128 mask bits plus one constant).

Two things make a naive solve wrong rather than merely slow:

  * A handful of archived rows carry corrupt tags. Plain elimination over all
    rows can absorb a corrupt row into the pivot basis, silently producing a
    wrong mask for that bit. The fix is to solve, measure the residual against
    every row, and restart from a different offset when the residual is large.
  * Grading is on held-out challenge records, so agreeing with the archive is
    not evidence of correctness. Only the recovered rule generalises; a lookup
    table over the samples does not.

No answer key is consulted -- only /app/data/samples.json.
"""
import json

FIELDS = ("serial", "batch", "model", "nonce")
NBITS_IN = 128
NU = NBITS_IN + 1          # 128 mask bits + constant, constant kept at bit 0


def pack(rec):
    """Pack the four 32-bit fields into one 128-bit integer, serial lowest."""
    return (int(rec["serial"], 16)
            | (int(rec["batch"], 16) << 32)
            | (int(rec["model"], 16) << 64)
            | (int(rec["nonce"], 16) << 96))


def rref(rows):
    """Reduced row echelon form over GF(2).

    rows: iterable of (coef, rhs). Returns {pivot_bit: (coef, rhs)}.
    """
    piv = {}
    for coef, rhs in rows:
        v, b = coef, rhs
        for p in sorted(piv, reverse=True):
            if (v >> p) & 1:
                pv, pb = piv[p]
                v ^= pv
                b ^= pb
        if v == 0:
            continue                      # dependent row (or a corrupt one)
        p = v.bit_length() - 1
        for q in list(piv):
            pv, pb = piv[q]
            if (pv >> p) & 1:
                piv[q] = (pv ^ v, pb ^ b)
        piv[p] = (v, b)
    return piv


def solve_bit(rows_all):
    """Recover one output bit's affine form; returns (coef_vector, residual)."""
    best = None
    # Deterministic restarts, so a corrupt row landing in the basis is escaped.
    for off in (0, 61, 113, 157, 29, 181):
        rot = rows_all[off:] + rows_all[:off]
        piv = rref(rot)
        if len(piv) != NU:
            continue                      # not yet full rank from this offset
        sol = 0
        for p, (v, b) in piv.items():
            if v == (1 << p) and b:
                sol |= (1 << p)
        residual = sum(1 for c, r in rows_all
                       if (bin(c & sol).count("1") & 1) != r)
        if best is None or residual < best[1]:
            best = (sol, residual)
        if residual == 0:
            break
    if best is None:
        raise SystemExit("archive does not determine the tag function")
    return best


def main():
    with open("/app/data/samples.json") as f:
        samples = json.load(f)["records"]
    with open("/app/data/challenge.json") as f:
        chal = json.load(f)
    challenge = chal["records"]
    nbits_out = chal["tag_bits"]

    # Constant term is carried as bit 0, so the input vector is (x << 1) | 1.
    vecs = [(pack(r) << 1) | 1 for r in samples]
    tags = [int(r["tag"], 16) for r in samples]

    sols = []
    for j in range(nbits_out):
        rows = [(vecs[i], (tags[i] >> j) & 1) for i in range(len(samples))]
        sol, _ = solve_bit(rows)
        sols.append(sol)

    out = []
    for r in challenge:
        x = (pack(r) << 1) | 1
        t = 0
        for j, sol in enumerate(sols):
            if bin(x & sol).count("1") & 1:
                t |= (1 << j)
        out.append("0x%08x" % t)

    with open("/app/tags.json", "w") as f:
        json.dump({"tags": out}, f)
    print("wrote %d forged tags -> /app/tags.json" % len(out))


if __name__ == "__main__":
    main()
