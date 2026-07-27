A media archive was migrated by a tool that stripped the WAV headers from every
file and lost the sidecar metadata describing them. What survived is a directory
of raw PCM and a partial catalogue. Your job is to work out how each file was
actually written and normalise the whole archive to one encoding.

`/app/data/manifest.json` is the catalogue. Its `assets` array lists, in order,
every file in the archive with three facts the catalogue happened to record:
`name`, `sample_rate`, and `frames` (the duration in sample frames), plus
`channels`. The audio itself is in `/app/data/raw/`.

Nothing else about the encoding survived. For each file you must determine:

- **`bit_depth`** — 8, 16, 24 or 32 bits per sample.
- **`endianness`** — `"little"` or `"big"`. Meaningless for 8-bit files, which
  the archive records as `"little"`.
- **`signed`** — `true` or `false`. Unsigned samples are stored biased by half
  full scale, in the usual way.
- **`layout`** — `"interleaved"` (frames of consecutive per-channel samples) or
  `"planar"` (each channel stored end to end). Meaningless for mono files, which
  the archive records as `"interleaved"`.
- **`preamble_bytes`** — some files kept a fragment of their original header at
  the very front. It is always fewer than 64 bytes, and the audio payload always
  runs from the end of that fragment to the end of the file. Files with no
  surviving fragment have `0`.

Every file is genuine audio and every file is intact apart from a possible
header fragment. No file is truncated and no file is padded at the end.

## The canonical encoding

Convert every file to **signed 16-bit little-endian, interleaved**, keeping its
channel count and frame count. Sample values are converted exactly as follows,
with no dithering, scaling or filtering of any kind:

1. If the source is unsigned, first subtract half full scale — `2**(bit_depth-1)`
   — to centre it on zero.
2. Then map to 16 bits by width:
   - 8-bit: multiply by 256.
   - 16-bit: unchanged.
   - 24-bit: shift right by 8.
   - 32-bit: shift right by 16.

Both shifts are **arithmetic** — they round toward negative infinity, not toward
zero. `-257 >> 8` is `-2`, not `-1`. Getting this backwards changes the result
for negative samples only, which is easy to miss.

## Output

Write `/app/normalized.json`, a JSON object whose `files` value is an array with
one entry per archive file, **in manifest order**:

    {"files": [
      {"name": "asset_00.pcm", "bit_depth": 16, "endianness": "little",
       "signed": true, "layout": "interleaved", "preamble_bytes": 0,
       "sha256": "0f1e2d..."},
      ...
    ]}

`sha256` is the lowercase hex SHA-256 digest of the canonical bytes for that
file — the converted samples alone, with no header of any kind. `bit_depth` and
`preamble_bytes` must be JSON integers, `signed` a JSON boolean, and
`endianness`, `layout` and `sha256` JSON strings. Write no other files.

Write `/app/normalized.json` as soon as you have a first pass over the archive
and overwrite it as you refine your answers. A missing file scores zero.

Your submission is correct when both of the following hold:

1. `/app/normalized.json` exists and is a JSON object whose `files` value is an
   array with exactly one well-formed entry per archive file, in manifest order,
   with the field names, types and permitted values described above.
2. Every field of every entry is correct: the recovered format matches how the
   file was actually written, and each `sha256` matches the canonical bytes. All
   files must be right.
