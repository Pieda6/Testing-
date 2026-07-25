"""Reference solver for dynamo/legacy-tag-forge.

The archive's tag routine is affine over GF(2): every tag bit is the XOR of a
fixed subset of the record's 128 input bits, optionally complemented. That is
discoverable from the archive itself -- parity relations hold across triples of
records, which no CRC-style or arithmetic construction satisfies -- and once
known, the whole 32-bit map is determined by any 129 independent rows.

The obstacle is the corrupt rows. A dozen of the 240 archived rows have their
tag replaced outright, and because the corruption is row-wise rather than
bit-wise, every output bit sees the same ~5% of bad rows. No fixed choice of
pivot rows dodges them: on the shipped data the best contiguous 129-row window
leaves a residual of 111 against the 12 a clean basis would leave. A plain
elimination still reaches full rank and raises nothing, so the failure is
silent.

The way through is to search for a clean basis:

  * Sample 129 rows at random and solve all 32 output bits from that ONE
    elimination, carrying the 32-bit tag along as the right-hand side.
  * Score the candidate by FULL-tag agreement over every archived row. A
    corrupt row has a random 32-bit tag, so it disagrees with certainty --
    which makes a clean basis identifiable exactly: its residual equals the
    number of corrupt rows, while a poisoned basis scores near half the archive.
  * Stop once the residual drops to the disclosed corruption bound.

At 12 bad rows in 240 a random basis is clean with probability ~0.95^129, so
this converges in a few thousand draws (about 85 s here). The RNG is seeded, so
the run is deterministic.

No answer key is consulted -- only /app/data/samples.json.
"""
import json
import random

FIELDS = ("serial", "batch", "model", "nonce")
NBITS_IN = 128
NU = NBITS_IN + 1          # 128 mask bits + constant, constant kept at bit 0
MAX_TRIES = 60000
RNG_SEED = 20240725


def pack(rec):
    """Pack the four 32-bit fields into one 128-bit integer, serial lowest."""
    return (int(rec["serial"], 16)
            | (int(rec["batch"], 16) << 32)
            | (int(rec["model"], 16) << 64)
            | (int(rec["nonce"], 16) << 96))


def solve_basis(rows, nbits_out):
    """Solve all output bits from one basis.

    rows: [(coef, tag)] with coef a 129-bit vector and tag the full output word.
    The elimination carries the whole tag as the right-hand side, so a single
    pass yields every output bit's mask. Returns None if the rows are not
    independent enough to pin the map.
    """
    piv = {}
    for coef, tag in rows:
        v, t = coef, tag
        for p in sorted(piv, reverse=True):
            if (v >> p) & 1:
                pv, pt = piv[p]
                v ^= pv
                t ^= pt
        if v == 0:
            continue                      # dependent row
        p = v.bit_length() - 1
        for q in list(piv):
            pv, pt = piv[q]
            if (pv >> p) & 1:
                piv[q] = (pv ^ v, pt ^ t)
        piv[p] = (v, t)
    if len(piv) != NU:
        return None
    masks = [0] * nbits_out
    for p, (v, t) in piv.items():
        for j in range(nbits_out):
            if (t >> j) & 1:
                masks[j] |= (1 << p)
    return masks


def predict(masks, coef):
    t = 0
    for j, m in enumerate(masks):
        if bin(coef & m).count("1") & 1:
            t |= (1 << j)
    return t


def recover(rows, nbits_out, max_bad):
    """Find a clean basis by random restart, scored on full-tag agreement."""
    rng = random.Random(RNG_SEED)
    best = None
    for _ in range(MAX_TRIES):
        masks = solve_basis(rng.sample(rows, NU), nbits_out)
        if masks is None:
            continue
        residual = sum(1 for c, t in rows if predict(masks, c) != t)
        if best is None or residual < best[1]:
            best = (masks, residual)
        if residual <= max_bad:
            break
    if best is None:
        raise SystemExit("archive does not determine the tag routine")
    return best


def main():
    with open("/app/data/samples.json") as f:
        samples = json.load(f)["records"]
    with open("/app/data/challenge.json") as f:
        chal = json.load(f)
    challenge = chal["records"]
    nbits_out = chal["tag_bits"]

    # Constant term is carried as bit 0, so the input vector is (x << 1) | 1.
    rows = [(((pack(r) << 1) | 1), int(r["tag"], 16)) for r in samples]

    # The instruction bounds the corruption at fewer than twenty rows; accept a
    # basis once its residual is inside that bound.
    masks, residual = recover(rows, nbits_out, max_bad=19)

    out = ["0x%08x" % predict(masks, (pack(r) << 1) | 1) for r in challenge]
    with open("/app/tags.json", "w") as f:
        json.dump({"tags": out}, f)
    print("recovered map (residual %d corrupt rows); wrote %d forged tags "
          "-> /app/tags.json" % (residual, len(out)))


if __name__ == "__main__":
    main()
