`/app/data/manual.md` defines which healthcare-associated infections are
reportable — but the numbers in it have been redacted. `/app/data/audited.json`
is a prior quarter: 59 admissions, and the summary the programme published for
them under the complete manual. It publishes counts only — per ward, per month,
how many urinary events, how many bloodstream events, how many of those were
line-associated. No patient, no date, no organism, no worked adjudication.

**A few of the published numbers are wrong** — at most four of the forty-five.
Which ones is not recorded.

Recover what the manual is missing from that summary, then adjudicate the
held-out quarter in `/app/data/records.json` with it.

All records are synthetic. No part of them comes from a real person.

## The manual

`/app/data/manual.md` is **authoritative and self-contained except for its
constants**. Every withheld value is marked `[[?]]`, and §5, §8 and §10 each
name two possibilities and leave the choice open. Twelve values are missing in
all. Read it in full and apply exactly what it says. Where it differs from any
surveillance manual you already know — and it does — the shipped excerpt
governs. **Most of its constants are not the familiar ones**: ten of the twelve
differ from the values the well-known national definitions use, so they have to
be recovered rather than assumed.

## The input

`audited.json` and `records.json` share a structure: `period_start` and
`period_end` (half-open), `wards` (every ward name, in the order denominators
must be reported), and `patients`. Each patient is
`{"id": ..., "admissions": [...]}`, and each admission has `admit` and
`discharge` dates, `wards` (a list of `{"ward", "arrive"}` in date order),
`central_lines` (a list of `{"insert", "remove"}`), `cultures` (a list of
`{"date", "source", "organisms"}` where `source` is `blood` or `urine`), and
`signs` (a list of `{"date", "elements"}`). All dates are `YYYY-MM-DD`.

`audited.json` additionally carries `summary` — one entry per ward per month,
`{"ward", "month", "uti_events", "bsi_events", "central_line_associated"}`, with
`month` as `YYYY-MM` — and `central_line_days`. §13 of the manual says exactly
what those counts are over. A cell that is lower than the cultures suggest is as
informative as one that is high.

The data is complete: a sign that is not listed was not recorded, and a culture
that is not listed was not taken.

## Output

Write `/app/answer.json` — **for the patients in `records.json` only** — a JSON
object with `patients` and `central_line_days`. Shape only; the values below are
illustrative:

    {"patients": [
       {"id": "PT-001",
        "uti": [{"date_of_event": "2026-02-13", "ward": "W3B",
                 "organisms": ["Escherichia coli"]}],
        "bsi": [{"date_of_event": "2026-02-09", "ward": "MICU",
                 "organisms": ["Klebsiella pneumoniae"],
                 "central_line_associated": true}]}
     ],
     "central_line_days": [{"ward": "MICU", "days": 90}]}

`patients` has one entry per held-out patient, **in the order they appear in
`records.json`**, with `id` matching. `uti` and `bsi` each list that patient's
reportable events of that type, ordered by `date_of_event`, and are empty arrays
when there are none. Within an event, `organisms` is sorted and free of
duplicates, `ward` is a ward name, and `central_line_associated` — on
bloodstream events only — is a JSON boolean.

`central_line_days` has one entry per ward, **in the order `wards` lists them**,
with `days` a non-negative integer, counted over the held-out patients.

Write `/app/answer.json` before you are confident in it — as soon as you can put
one entry on disk for every held-out patient, even if you expect to change them
— and overwrite it as you refine. A missing file scores zero. Write no other
files.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and has exactly the structure above — one
   well-formed entry per held-out patient in record order, one per ward in the
   listed order, using the documented field names, types and formats.
2. Every determination is right: each reportable event present with the correct
   date of event, ward and organisms, nothing reported that is not reportable,
   central line association correct, and every ward's central line day count
   correct. All forty-seven patients and all ward counts must be right.
