# Surveillance Definitions Manual (excerpt)

This excerpt is authoritative for the reporting period. Where it differs from
any other surveillance manual you may be familiar with, this excerpt governs.

## 1. Terms

**Calendar day.** No times are recorded anywhere in the data. Every window is
counted in whole calendar days and includes both of its endpoints unless stated
otherwise.

**Admission day.** For an admission with admit date `A`, admission day 1 is `A`
and admission day *n* is `A` plus *n* − 1 days. Day numbering restarts at each
admission.

**Ward occupancy.** Each admission lists ward arrivals in date order. The
patient occupies a ward from its arrival date through the day before the next
arrival, and the last ward through the discharge date.

**Central line in place.** A line episode with insert date `I` and removal date
`R` has a line in place on every calendar day from `I` through `R` inclusive.
Line day 1 is `I`.

**Organism classes.** §7 lists the common commensals. Every other organism name
appearing in the data is a *recognised pathogen*.

**Element.** A culture, or a sign recorded on a given date.

## 2. Candidate bloodstream infections

A **BSI candidate** arises in either of two ways.

**BSI-P.** A blood culture growing at least one recognised pathogen. Its
*anchor date* is that culture's date. Its organisms are the recognised pathogens
on that culture; commensals on the same culture are not included.

**BSI-C.** Two blood cultures of the same admission, drawn on the same calendar
day or on two consecutive calendar days, that grow a common commensal of the
same name, together with at least one of `fever`, `chills` or `hypotension`
recorded during that admission on a date inside the infection window
period (§4). Its anchor date is the earlier of the two culture dates. Its
organisms are the matched commensal alone.

A single blood culture growing only commensals is not a candidate.

## 3. Candidate urinary tract infections

A **UTI candidate** is a urine culture growing at least one recognised pathogen,
together with at least one of `fever`, `dysuria`, `urgency`,
`suprapubic_tenderness` or `costovertebral_tenderness` recorded during the same
admission on a date inside the infection window period. Its anchor date is that
culture's date. Its organisms are the recognised pathogens on that culture.

## 4. Infection window period

The seven calendar days made up of the anchor date, the three days before it and
the three days after it.

## 5. Date of event

The earliest date, among the dates of the elements used to meet the definition,
that lies inside the infection window period. Concretely:

- **BSI-P** — the anchor date.
- **BSI-C** — the earlier of: the earlier of the two culture dates, and the
  earliest qualifying sign date inside the infection window period.
- **UTI** — the earlier of: the culture date, and the earliest qualifying sign
  date inside the infection window period.

## 6. Healthcare association

A candidate belongs to the admission that contains its anchor date. It is
**healthcare-associated**, and therefore reportable, only if its date of event
falls on admission day 3 or later of that admission. A candidate whose date of
event falls on admission day 1 or day 2, or before the admit date, is **present
on admission** and is not reported.

## 7. Common commensals

    Bacillus species
    Corynebacterium species
    Cutibacterium acnes
    Micrococcus species
    Staphylococcus epidermidis

## 8. Adjudication order

Adjudicate every UTI candidate first, then every BSI candidate. Within each
group take candidates in ascending order of date of event; if two share a date
of event take the one with the earlier anchor date first; if they still tie take
the one whose first organism name sorts earlier. Organism lists are updated as
adjudication proceeds, so a later step sees the effect of an earlier one.

## 9. Repeat infection timeframe

Reporting an event opens a **repeat infection timeframe** of 14 calendar days
beginning on its date of event, which is day 1 of the timeframe. While a
timeframe of a given type is open for a patient:

- a later candidate of the same type whose date of event lies inside the
  timeframe is **not reported**; and
- every organism of that suppressed candidate is added to the organism list of
  the event that opened the timeframe.

A suppressed candidate does not extend the timeframe and does not open one.
Timeframes are per patient and per type, and they carry across admissions.

## 10. Secondary bloodstream infections

A BSI candidate is **secondary**, and is not reported as a bloodstream
infection, if there is a reported UTI event for the same patient such that both
hold:

- the BSI candidate's anchor date lies within that UTI's **attribution
  period** — the first day of its infection window period through the last day
  of its repeat infection timeframe, inclusive; and
- at least one of the BSI candidate's organisms is identical to an organism
  already in that UTI event's organism list.

Every organism of a secondary BSI candidate is added to that UTI event's
organism list. A secondary candidate does not open a bloodstream timeframe and
is not suppressed by one.

## 11. Central line association

A reported bloodstream infection is **central-line-associated** if some central
line episode of the same admission satisfies both:

- its date of event is on or after line day 3 — that is, at least two calendar
  days after the insert date; and
- its date of event is on or before the day after the removal date.

## 12. Location attribution

Let `d` be the date of event and let `A` be the date the patient arrived in the
ward they occupied on `d`. If `A` is `d` or the day before `d`, attribute the
event to the ward occupied on the day before `A`; if that ward does not exist
because `A` is the admit date, attribute the event to the ward occupied on `d`.
Otherwise attribute the event to the ward occupied on `d`.

## 13. Central line days

For each ward, the number of (patient, calendar day) pairs for which the patient
occupied that ward on that day and had a central line in place on that day,
counting only days from the reporting period start through the day before the
reporting period end.
