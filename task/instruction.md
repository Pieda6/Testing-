You are auditing a legacy device-provisioning service. Every provisioning record
it issues carries a 32-bit authentication tag, and the routine that computes that
tag was lost when the original vendor folded — no specification for it survives.
Your job is to demonstrate that the scheme is forgeable by producing valid tags
for records the service never signed.

`/app/data/samples.json` is the recovered archive. It has `fields` (the record
field names, in packing order), `tag_bits` (32), and `records`: 240 provisioning
records, each with the four 32-bit hex fields `serial`, `batch`, `model`, `nonce`
and the hex `tag` the service issued for it.

`/app/data/challenge.json` has the same shape but its 60 records carry no tag.
These are the records you must forge tags for. None of them appears in the
archive.

What is known about the tag routine:

- It is deterministic and depends only on the four fields of the record it is
  tagging. The same four field values always produce the same tag. No key
  material, timestamp, counter, or record ordering enters into it.
- It is not any published or standard checksum, MAC, or hash construction. It was
  written in-house. You will not find it by name; recover it from the archive.
- When the routine treats a record as a bit string it packs the four fields into
  a single 128-bit value, `serial` occupying the lowest 32 bits, then `batch`,
  then `model`, then `nonce` in the highest 32 bits.
- The archive is imperfect: fewer than twenty of the 240 rows carry a corrupt
  tag. On an affected row the recorded tag is unrelated to the one the routine
  would produce — the whole 32-bit value is wrong, not a single flipped bit.
  Which rows are affected is not recorded. Every row of `challenge.json` is
  clean.

Write the forged tags to `/app/tags.json` as a single JSON object with exactly
this shape:

    {"tags": ["0x00000000", "0x00000000", ...]}

`tags` must be an array of exactly 60 hex strings, one per record of
`challenge.json` and in the same order. Each must be a string (not a JSON
number), must fit in 32 bits, and a leading `0x` is optional. Write no other
files.

Your submission is correct when all of the following hold:

1. `/app/tags.json` exists and is a JSON object whose `tags` value is an array of
   exactly 60 hexadecimal strings, each denoting a value below 2³².
2. Every one of the 60 tags equals the tag the archive's own routine produces for
   the corresponding challenge record. All 60 must be right; the correct tags are
   held out and are not derivable from `challenge.json` alone.

You have 1800 seconds to complete this task. Do not cheat by using online
solutions or hints specific to this task.
