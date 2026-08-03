`/app/data/jobs.json` is three years of firing history from a cron-style
scheduler — twenty-four jobs — together with what is known about the host it ran
on. Work out when each job fires next.

## The scheduler

Every job has a five-field schedule — minute, hour, day-of-month, month,
day-of-week — and fires at **every whole minute whose local time matches it**.
Each field is either `*`, meaning any value, or a set of allowed values, and the
fields are matched independently, with two things to know:

- **The month field is `*` for every job here.** It is not in play.
- **Day-of-month and day-of-week are OR'd when both are restricted.** If both
  name a set, a date matches when its day number is in one set **or** its
  weekday is in the other. If either is `*`, only the other applies. This is
  Vixie cron's rule and it is the rule in force.

Day-of-week runs Sunday `0` through Saturday `6`.

## The clock

The host does not run on UTC. `clock` gives `base_offset_min`, its offset from
UTC in minutes at the start of the log. That offset does not stay put — the host
changes it twice a year — and **the changes are not listed. The log is where you
find them.**

Each change happens at a whole hour of local time, on a fixed occurrence of a
fixed weekday in a fixed month: the first, second, third, fourth, fifth or
**last** such weekday. There is one such rule for each of the two changes, and
both have been in force, unchanged, for the whole history. The offsets are the
host's own; no time zone database describes them.

Local time is UTC plus the offset in force at that instant, so a change moves
local time:

- one that moves the clock **forward** deletes a stretch of local times, and a
  job scheduled inside that stretch does not fire that day at all;
- one that moves it **backward** repeats a stretch, and a job scheduled inside
  that stretch fires **twice**, at two different UTC instants.

Changes fall inside the log and inside the window you must predict.

## Outages

`outages` lists half-open UTC intervals during which the host was down. Nothing
ran and nothing was recorded. A job's silence inside an outage says nothing
about its schedule.

## The input

`/app/data/jobs.json` is a JSON object with:

- `clock` — `base_offset_min`, the offset in force at the start of the log
- `log_start_utc`, `log_end_utc` — the half-open window the log covers
- `predict_start_utc`, `predict_end_utc` — the half-open window to predict
- `outages` — an array of `start_utc` / `end_utc` pairs
- `jobs` — an array of `{"id": "JOB-001", "fires": [...]}`, where `fires` holds
  every UTC instant that job fired during the log window, ascending, written as
  `YYYY-MM-DDTHH:MM:SSZ`

Outside the outages the log is complete: if a job does not appear at some minute
of the log window and that minute is not inside an outage, the job did not fire
then.

## Output

Write `/app/answer.json`, a JSON object whose `schedules` value is an array with
one entry per job, **in the same order as `jobs.json`** — shape only, the
instants below are illustrative:

    {"schedules": [
      {"id": "JOB-001", "fires": ["2026-02-04T03:30:00Z", "2026-02-11T03:30:00Z"]},
      {"id": "JOB-002", "fires": ["2026-02-01T08:15:00Z"]}
    ]}

`id` must match the job. `fires` lists every UTC instant at which that job fires
in `[predict_start_utc, predict_end_utc)`, strictly ascending, in the same
`YYYY-MM-DDTHH:MM:SSZ` form.

Write `/app/answer.json` as soon as you have an entry for every job and
overwrite it as you refine it. A missing file scores zero. Write no other files.

The timestamps are what is graded, not a recovered crontab: any working you
like is fine, so long as the instants come out right.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and is a JSON object whose `schedules` value is an
   array with exactly one well-formed entry per job, in the order the jobs
   appear in `jobs.json`, using the field names, types and formats described
   above.
2. Every entry lists exactly the instants that job fires in the prediction
   window — none missing and none extra. All twenty-four must be right.
