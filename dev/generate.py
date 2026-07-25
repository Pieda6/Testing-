"""Deterministic dataset generator for dynamo/legacy-tag-forge.

Fixed seed => byte-identical output on every run and platform (all randomness
derives from SHA-256 of a fixed seed + counter).

The provisioning archive is authenticated with a one-off tag function: each of
the 32 tag bits is the XOR of a fixed secret subset of the record's 128 input
bits, optionally complemented. Equivalently tag = M*x + c over GF(2) for a
secret 32x128 matrix M and a 32-bit constant c.

Why this shape:
  * No named technique. There is no CRC, HMAC or published attack to reach for;
    the only route is to notice the structure in the archive and rebuild it.
  * Survives disclosure. Even stating outright that the tag is a fixed Boolean
    function of the input bits leaves all of the work -- setting up 32 systems
    over GF(2), spanning the input space, and coping with corrupt rows.
  * No free self-check. Grading is on held-out challenge records, so fitting the
    visible samples proves nothing and a lookup table scores zero.
  * Silent failure. A small number of archived rows carry corrupt tags. A plain
    elimination over all rows can absorb one into the basis and yield a wrong
    map for that bit with no error raised.

Emits:
  samples.json   - 200 records with tags (agent-visible)
  challenge.json - 60 records without tags (agent-visible)
  expected_tags.json - the 60 correct tags (VERIFIER ONLY, goes in tests/)
"""
import hashlib
import json

SEED = b"dynamo/legacy-tag/v1"
NBITS_IN = 128           # four 32-bit fields
NBITS_OUT = 32
N_SAMPLES = 200
N_CHALLENGE = 60
N_CORRUPT = 6
FIELDS = ("serial", "batch", "model", "nonce")


def det_bytes(counter, n):
    out = b""
    i = 0
    while len(out) < n:
        out += hashlib.sha256(SEED + counter.encode() + i.to_bytes(4, "big")).digest()
        i += 1
    return out[:n]


def det_int(counter, nbits):
    b = det_bytes(counter, (nbits + 7) // 8)
    return int.from_bytes(b, "big") & ((1 << nbits) - 1)


# Secret affine map: row j is a 128-bit mask; tag bit j = parity(mask_j & x) ^ c_j
M = [det_int(f"row{j}", NBITS_IN) for j in range(NBITS_OUT)]
C = det_int("const", NBITS_OUT)


def pack(rec):
    """Pack the four 32-bit fields into one 128-bit integer, serial lowest."""
    return (rec["serial"]
            | (rec["batch"] << 32)
            | (rec["model"] << 64)
            | (rec["nonce"] << 96))


def tag_of(rec):
    x = pack(rec)
    t = 0
    for j in range(NBITS_OUT):
        if bin(M[j] & x).count("1") & 1:
            t |= (1 << j)
    return t ^ C


def make_rec(i):
    return {f: det_int(f"{f}{i}", 32) for f in FIELDS}


def build():
    samples = []
    for i in range(N_SAMPLES):
        r = make_rec(i)
        r["tag"] = tag_of(r)
        samples.append(r)

    # Corrupt a few archived tags by flipping one bit. Indices are NOT disclosed;
    # the instruction states only that fewer than ten rows are affected.
    idx = sorted({det_int(f"corr{j}", 16) % N_SAMPLES for j in range(N_CORRUPT * 3)})[:N_CORRUPT]
    for ci in idx:
        samples[ci]["tag"] ^= (1 << (det_int(f"cb{ci}", 8) % NBITS_OUT))

    challenge = [make_rec(10_000 + i) for i in range(N_CHALLENGE)]
    answers = [tag_of(r) for r in challenge]

    # No challenge record may coincide with a sample, or it could be looked up.
    assert not ({pack(r) for r in challenge} & {pack(r) for r in samples})
    return samples, challenge, answers, idx


def hexrec(r, with_tag):
    out = {f: hex(r[f]) for f in FIELDS}
    if with_tag:
        out["tag"] = "0x%08x" % r["tag"]
    return out


if __name__ == "__main__":
    samples, challenge, answers, corrupt = build()
    with open("samples.json", "w") as f:
        f.write('{\n"fields":["serial","batch","model","nonce"],\n"tag_bits":32,\n"records":[\n')
        lines = [json.dumps(hexrec(r, True), separators=(",", ":")) for r in samples]
        f.write(",\n".join(lines))
        f.write("\n]\n}\n")
    with open("challenge.json", "w") as f:
        json.dump({"fields": list(FIELDS), "tag_bits": NBITS_OUT,
                   "records": [hexrec(r, False) for r in challenge]}, f, indent=2)
    with open("expected_tags.json", "w") as f:
        json.dump({"tags": ["0x%08x" % t for t in answers]}, f, indent=2)
    print("samples: %d (%d corrupt) | challenge: %d"
          % (len(samples), len(corrupt), len(challenge)))
    print("corrupt indices (secret):", corrupt)
