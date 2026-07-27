"""Deterministic archive generator for dynamo/headerless-pcm-normalize.

Fixed seed => byte-identical output on every run and platform. All randomness
derives from SHA-256 of a fixed seed plus a counter; no PRNG library is used.

The archive models a legacy tape-transfer dump whose WAV headers were stripped
by a failed migration. Each asset is raw PCM in one of the 42 sample formats
this generator enumerates exhaustively -- every combination of sample width,
channel count, byte order, signedness and channel layout that the archive's
capture tools could produce. The surviving catalogue (manifest.json) records
sample rate, duration in frames, and channel count. It records nothing else.

Why this shape:
  * Sample width is DETERMINED, not guessed: once frames and channels are known
    the byte length pins it. That is deliberate. A width ambiguity here would be
    genuinely unresolvable, because a w-bit stereo stream and a 2w-bit mono
    stream are byte-identical -- no signal analysis can separate them, and
    grading them would be a coin flip.
  * Byte order, signedness and layout are not constrained by size, and each
    fails silently. A byte-swapped decode promotes the low byte to the high byte
    and explodes the sample-to-sample difference. A signedness error wraps the
    waveform around the integer boundary. Reading a planar file as interleaved
    splices two sources together at the midpoint and doubles the roughness.
  * Some assets keep a fragment of the original header -- fewer than 64 bytes of
    it -- ahead of the audio. Its length is recoverable by arithmetic (the byte
    length minus the payload the catalogue implies), but an agent that never
    considers it decodes the whole file one offset out. The audio still looks
    like audio; only the digest betrays it.
  * The canonical target is bit-exact, so identifying the format is not enough.
    Downshifts are arithmetic (floor), which differs from truncation toward zero
    on every negative sample, and the canonical form is always interleaved
    whatever the source layout.

Emits:
  raw/asset_NN.pcm - the archive (agent-visible)
  manifest.json    - sample_rate, frames, channels per asset (agent-visible)
  expected.json    - formats and canonical digests (VERIFIER ONLY, goes in tests/)
"""
import hashlib
import json
import os

SEED = b"dynamo/headerless-pcm/v1"
MAX_PREAMBLE = 64          # exclusive bound, disclosed in instruction.md
SAMPLE_RATES = [8000, 16000, 22050, 32000, 44100, 48000]

# Two decimal digits of pi per partial phase would be arbitrary; everything here
# is derived from the seed instead. See det_unit.
import math


def enumerate_formats():
    """Every (bit_depth, channels, endianness, signed, layout) the tools emit.

    Byte order is meaningless for single-byte samples and layout is meaningless
    for a single channel, so those axes collapse -- the archive records them as
    "little" and "interleaved" respectively, and instruction.md pins that.
    """
    out = []
    for bit_depth in (8, 16, 24, 32):
        for channels in (1, 2):
            orders = ("little",) if bit_depth == 8 else ("little", "big")
            layouts = ("interleaved",) if channels == 1 else ("interleaved", "planar")
            for endianness in orders:
                for signed in (True, False):
                    for layout in layouts:
                        out.append((bit_depth, channels, endianness, signed, layout))
    return out


FORMATS = enumerate_formats()


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


def det_unit(counter):
    """Deterministic float in [0, 1)."""
    return det_int(counter, 32) / float(1 << 32)


def make_signal(tag, frames, channels):
    """Band-limited, smooth, amplitude-enveloped audio.

    Smoothness is load-bearing: a capture is heavily oversampled, so consecutive
    samples differ by a tiny fraction of the range. That is precisely what a
    byte-order, signedness or layout error destroys. The second channel is
    deliberately quieter and differently shaped so that genuine stereo never
    looks like the two halves of one decimated signal.
    """
    chans = []
    for c in range(channels):
        partials = []
        for k in range(3):
            cyc = 1.5 + 9.0 * det_unit(f"{tag}c{c}k{k}cyc")   # cycles over the clip
            amp = 0.25 + 0.55 * det_unit(f"{tag}c{c}k{k}amp")
            pha = 2.0 * math.pi * det_unit(f"{tag}c{c}k{k}pha")
            partials.append((cyc, amp, pha))
        env_cyc = 0.5 + 1.5 * det_unit(f"{tag}c{c}env")
        env_pha = 2.0 * math.pi * det_unit(f"{tag}c{c}envp")

        x = []
        for n in range(frames):
            t = n / float(frames)
            v = 0.0
            for cyc, amp, pha in partials:
                v += amp * math.sin(2.0 * math.pi * cyc * t + pha)
            env = 0.55 + 0.45 * math.sin(2.0 * math.pi * env_cyc * t + env_pha)
            x.append(v * env)
        peak = max(abs(v) for v in x) or 1.0
        scale = 0.82 if c == 0 else 0.40 + 0.25 * det_unit(f"{tag}c{c}scale")
        chans.append([v / peak * scale for v in x])
    return chans


def quantise(v, bit_depth, signed):
    """Map a float in [-1, 1] to an integer of the given width."""
    full = 1 << (bit_depth - 1)
    q = int(math.floor(v * full))
    q = max(-full, min(full - 1, q))
    return q if signed else q + full


def order_samples(chans, frames, channels, layout):
    if layout == "planar":
        return [chans[c][n] for c in range(channels) for n in range(frames)]
    return [chans[c][n] for n in range(frames) for c in range(channels)]


def pack(samples, bit_depth, endianness, signed):
    nbytes = bit_depth // 8
    order = "little" if endianness == "little" else "big"
    out = bytearray()
    for q in samples:
        out += int(q).to_bytes(nbytes, order, signed=signed)
    return bytes(out)


def to_canonical(q, bit_depth, signed):
    """One decoded integer sample -> signed 16-bit.

    Downshifts are arithmetic (floor), never truncation toward zero.
    """
    if not signed:
        q -= (1 << (bit_depth - 1))
    if bit_depth == 8:
        return q * 256
    if bit_depth == 16:
        return q
    if bit_depth == 24:
        return q >> 8
    if bit_depth == 32:
        return q >> 16
    raise ValueError(bit_depth)


def build():
    assets, answers = [], []
    for i, (bit_depth, channels, endianness, signed, layout) in enumerate(FORMATS):
        name = "asset_%02d.pcm" % i
        rate = SAMPLE_RATES[det_int(f"rate{i}", 16) % len(SAMPLE_RATES)]
        frames = 9000 + (det_int(f"frames{i}", 16) % 4000)

        # Roughly two in five assets kept a fragment of their original header.
        keeps = (det_int(f"haspre{i}", 16) % 5) < 2
        pre_len = 8 + (det_int(f"prelen{i}", 16) % (MAX_PREAMBLE - 8)) if keeps else 0
        preamble = det_bytes(f"pre{i}", pre_len)

        chans = make_signal(f"a{i}", frames, channels)
        quant = [[quantise(v, bit_depth, signed) for v in ch] for ch in chans]

        stored = order_samples(quant, frames, channels, layout)
        payload = pack(stored, bit_depth, endianness, signed)
        assert len(payload) == frames * channels * (bit_depth // 8)
        raw = preamble + payload

        # The canonical form is ALWAYS interleaved, whatever the source layout.
        canon = bytearray()
        for n in range(frames):
            for c in range(channels):
                canon += int(to_canonical(quant[c][n], bit_depth, signed)).to_bytes(
                    2, "little", signed=True)

        assets.append((name, rate, frames, channels, raw))
        answers.append({
            "name": name,
            "bit_depth": bit_depth,
            "endianness": endianness,
            "signed": signed,
            "layout": layout,
            "preamble_bytes": pre_len,
            "sha256": hashlib.sha256(bytes(canon)).hexdigest(),
        })
    return assets, answers


if __name__ == "__main__":
    assets, answers = build()
    os.makedirs("raw", exist_ok=True)
    for name, _rate, _frames, _ch, raw in assets:
        with open(os.path.join("raw", name), "wb") as f:
            f.write(raw)
    with open("manifest.json", "w") as f:
        json.dump({"assets": [{"name": n, "sample_rate": r, "frames": fr,
                               "channels": ch}
                              for n, r, fr, ch, _ in assets]}, f, indent=2)
        f.write("\n")
    with open("expected.json", "w") as f:
        json.dump({"files": answers}, f, indent=2)
        f.write("\n")

    total = sum(len(raw) for *_x, raw in assets)
    withpre = sum(1 for a in answers if a["preamble_bytes"])
    print("assets: %d | %d with header fragments | total bytes: %d"
          % (len(assets), withpre, total))
    for (name, _r, frames, ch, raw), a in zip(assets, answers):
        print("  %s %7d B %5d fr %dch %2d-bit %-6s %-8s %-11s pre=%d"
              % (name, len(raw), frames, ch, a["bit_depth"], a["endianness"],
                 "signed" if a["signed"] else "unsigned", a["layout"],
                 a["preamble_bytes"]))
