`/app/data/records.json` holds one reporting quarter of surveillance data for
thirty-six patients. `/app/data/manual.md` holds the definitions that govern it.
Adjudicate which healthcare-associated infections are reportable, and report the
ward denominators.

The records are synthetic. No part of them comes from a real person.

## The manual

`/app/data/manual.md` is **authoritative and self-contained**. Read it in full
and apply exactly what it says. Where it differs from any surveillance manual
you already know — and in places it does — the shipped excerpt governs. It
defines candidate infections, the infection window period, the date of event,
healthcare association, the order of adjudication, the repeat infection
timeframe, secondary bloodstream infections, central line association, ward
attribution and the central line day count.

## The input

`/app/data/records.json` is a JSON object with:

- `period_start`, `period_end` — the reporting period, half-open
- `wards` — every ward name, in the order the denominators must be reported
- `patients` — an array of `{"id": "PT-001", "admissions": [...]}` in the order
  the patients must be reported

Each admission has `admit` and `discharge` dates, `wards` (a list of
`{"ward", "arrive"}` in date order), `central_lines` (a list of `{"insert",
"remove"}`), `cultures` (a list of `{"date", "source", "organisms"}` where
`source` is `blood` or `urine`), and `signs` (a list of `{"date",
"elements"}`). All dates are `YYYY-MM-DD`. The data is complete: a sign that is
not listed was not recorded, and a culture that is not listed was not taken.

## Output

Write `/app/answer.json`, a JSON object with `patients` and `central_line_days`
— shape only, the values below are illustrative:

    {"patients": [
       {"id": "PT-001",
        "uti": [{"date_of_event": "2026-01-13", "ward": "W3B",
                 "organisms": ["Escherichia coli"]}],
        "bsi": [{"date_of_event": "2026-01-09", "ward": "MICU",
                 "organisms": ["Klebsiella pneumoniae"],
                 "central_line_associated": true}]}
     ],
     "central_line_days": [{"ward": "MICU", "days": 90}]}

`patients` has one entry per patient, **in the order they appear in
`records.json`**, with `id` matching. `uti` and `bsi` each list that patient's
reportable events of that type, ordered by `date_of_event`, and are empty arrays
when there are none. Within an event, `organisms` is sorted and free of
duplicates, `ward` is a ward name, and `central_line_associated` — on
bloodstream events only — is a JSON boolean.

`central_line_days` has one entry per ward, **in the order `wards` lists them**,
with `days` a non-negative integer.

Write `/app/answer.json` as soon as you have an entry for every patient and
overwrite it as you refine it. A missing file scores zero. Write no other files.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and has exactly the structure above — one
   well-formed entry per patient in record order, one per ward in the listed
   order, using the documented field names, types and formats.
2. Every determination is right: each reportable event present with the correct
   date of event, ward and organisms, nothing reported that is not reportable,
   central line association correct, and every ward's central line day count
   correct. All thirty-six patients and all ward counts must be right.
