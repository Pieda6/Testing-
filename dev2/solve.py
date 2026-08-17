"""Reference solver for dynamo/headerless-pcm-normalize.

The catalogue records sample rate, frame count and channel count. Everything
else about how each file was written -- sample width, byte order, signedness,
channel layout, and whether a fragment of the original header survives at the
front -- has to be recovered from the bytes, and every wrong choice decodes
without raising anything.

Two of those are arithmetic. The payload occupies frames x channels x width
bytes and any header fragment is under 64 bytes, so for each candidate width the
leftover is forced; only one width leaves a leftover in range, because the
widths are thousands of bytes apart. That pins the width and the fragment length
together.

The other three come from the signal. Real audio is heavily oversampled, so
consecutive samples differ by a tiny fraction of the waveform's range, and every
wrong reading destroys that:

  * a byte-swapped decode promotes the low byte to the high byte, so neighbouring
    samples jump by thousands;
  * a signedness error wraps the waveform around the integer boundary, inserting
    a full-scale discontinuity wherever it crosses;
  * reading an interleaved file as planar splices the two channels end to end.

So: enumerate the handful of surviving interpretations, decode each, and score by
mean absolute first difference normalised by the channel's own range.

Roughness alone is not quite enough for one case. Reading a PLANAR file as
interleaved builds each channel from alternate samples of the same signal, which
only about doubles the roughness -- on this archive that margin narrows to 1.5x,
too thin to rest a bit-exact answer on. But those two channels are then the even
and odd samples of one waveform, so they correlate at essentially 1.0, which
genuine stereo never does. A correlation test rejects that reading outright and
turns a marginal call into a decisive one.

Then convert to the canonical encoding: signed 16-bit little-endian, always
interleaved whatever the source layout, downshifts arithmetic. Record the
SHA-256 of those bytes.

No answer key is consulted; only /app/data.
"""
import hashlib
import json

import numpy as np

DATA = "/app/data"
OUT = "/app/normalized.json"
MAX_PREAMBLE = 64          # exclusive; stated in the task description
WIDTHS = (1, 2, 3, 4)      # bytes per sample

# Alternate samples of one waveform correlate at ~1.0; real stereo does not.
CORR_REJECT = 0.99


def decode(raw, bit_depth, endianness, signed):
    """Decode a raw byte stream to int64 samples in stored order."""
    if bit_depth == 8:
        dt = np.dtype("i1" if signed else "u1")
        return np.frombuffer(raw, dtype=dt).astype(np.int64)
    if bit_depth in (16, 32):
        code = {16: "2", 32: "4"}[bit_depth]
        prefix = "<" if endianness == "little" else ">"
        dt = np.dtype(prefix + ("i" if signed else "u") + code)
        return np.frombuffer(raw, dtype=dt).astype(np.int64)
    if bit_depth == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        if endianness == "little":
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        else:
            v = b[:, 2] | (b[:, 1] << 8) | (b[:, 0] << 16)
        if signed:
            v = np.where(v >= (1 << 23), v - (1 << 24), v)
        return v
    raise ValueError(bit_depth)


def split(samples, frames, channels, layout):
    """Return a (frames, channels) matrix from the stored sample order."""
    if layout == "planar":
        return samples.reshape(channels, frames).T
    return samples.reshape(frames, channels)


def roughness(m):
    """Mean absolute first difference per channel, normalised by its range."""
    total = 0.0
    for c in range(m.shape[1]):
        col = m[:, c]
        rng = float(col.max() - col.min())
        if rng <= 0:
            return float("inf")            # a constant channel is not audio
        total += float(np.abs(np.diff(col)).mean()) / rng
    return total / m.shape[1]


def channel_corr(m):
    """|Pearson r| between the first two channels; 0.0 for mono."""
    if m.shape[1] < 2:
        return 0.0
    a = m[:, 0].astype(np.float64)
    b = m[:, 1].astype(np.float64)
    if a.std() == 0 or b.std() == 0:
        return 1.0
    return float(abs(np.corrcoef(a, b)[0, 1]))


def layout_and_geometry(nbytes, frames, channels):
    """Resolve sample width and header-fragment length from the byte length."""
    fits = []
    for w in WIDTHS:
        pre = nbytes - frames * channels * w
        if 0 <= pre < MAX_PREAMBLE:
            fits.append((w * 8, pre))
    if len(fits) != 1:
        raise SystemExit("byte length does not pin a unique sample width")
    return fits[0]


def readings(bit_depth, channels):
    # Byte order is meaningless for single-byte samples and layout is
    # meaningless for one channel; the archive records those as "little" and
    # "interleaved".
    orders = ("little",) if bit_depth == 8 else ("little", "big")
    layouts = ("interleaved",) if channels == 1 else ("interleaved", "planar")
    return [(e, s, l) for e in orders for s in (True, False) for l in layouts]


def to_canonical(m, bit_depth, signed):
    """(frames, channels) matrix -> interleaved signed 16-bit little-endian."""
    v = m
    if not signed:
        v = v - (1 << (bit_depth - 1))
    if bit_depth == 8:
        v = v * 256
    elif bit_depth == 24:
        v = v >> 8
    elif bit_depth == 32:
        v = v >> 16
    return np.ascontiguousarray(v).astype("<i2").tobytes()


def identify(raw, frames, channels):
    bit_depth, preamble = layout_and_geometry(len(raw), frames, channels)
    payload = raw[preamble:]

    best = None
    for endianness, signed, layout in readings(bit_depth, channels):
        samples = decode(payload, bit_depth, endianness, signed)
        if len(samples) != frames * channels:
            continue
        m = split(samples, frames, channels, layout)
        if channel_corr(m) > CORR_REJECT:
            continue                       # planar data misread as interleaved
        score = roughness(m)
        if best is None or score < best[0]:
            best = (score, endianness, signed, layout)
    if best is None:
        raise SystemExit("no interpretation fits")

    score, endianness, signed, layout = best
    m = split(decode(payload, bit_depth, endianness, signed),
              frames, channels, layout)
    return score, bit_depth, endianness, signed, layout, preamble, m


def main():
    with open("%s/manifest.json" % DATA) as f:
        assets = json.load(f)["assets"]

    files = []
    for a in assets:
        with open("%s/raw/%s" % (DATA, a["name"]), "rb") as f:
            raw = f.read()
        score, bd, endianness, signed, layout, preamble, m = identify(
            raw, a["frames"], a["channels"])
        files.append({
            "name": a["name"],
            "bit_depth": bd,
            "endianness": endianness,
            "signed": signed,
            "layout": layout,
            "preamble_bytes": preamble,
            "sha256": hashlib.sha256(to_canonical(m, bd, signed)).hexdigest(),
        })
        print("%s -> %2d-bit %-6s %-8s %-11s pre=%-2d (roughness %.5f)"
              % (a["name"], bd, endianness, "signed" if signed else "unsigned",
                 layout, preamble, score))

    with open(OUT, "w") as f:
        json.dump({"files": files}, f)
    print("wrote %d entries -> %s" % (len(files), OUT))


if __name__ == "__main__":
    main()
