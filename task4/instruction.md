Forty meeting requests have come in for the week of Monday 2 March 2026,
for a nine-person org spread across three time zones. They must be booked
against calendars that are already partly full, under the org's booking policy.
Some will not fit, and those must be declined rather than forced.

## What you have

`/app/data/people.json` — the week's days, the 15-minute booking grid, the lunch
and daily-load settings, and one record per person: their UTC offset in minutes,
their working hours in their own local time, their home site, days they are on
PTO, and the standing commitments already on their calendar (each with a day, a
local start, a duration, and a location).

`/app/data/sites.json` — the office sites, the travel time in minutes between
each pair, and the buffer needed when someone switches between remote and any
site.

`/app/data/requests.json` — the forty requests, each with an id, priority,
duration, location, required attendees, optional attendees, and the earliest and
latest day it may be booked on.

## The booking policy

Standing commitments and PTO are fixed and cannot be moved. Only the requests
are being booked, and a request once booked is never moved to make room for
another. A booking is allowed only if all of the following hold for every
required attendee:

1. They are not on PTO that day.
2. The meeting sits entirely inside their working hours **for that day in their
   own local time**.
3. It does not overlap anything already on their calendar.
4. Between it and whatever immediately precedes or follows it **on that same
   day**, there is at least the travel time from `sites.json` — nothing if the
   two are at the same location, `remote_switch_min` if one is remote and the
   other is a site, otherwise the site-to-site figure. Everyone starts their day
   at their own `home_site`, so if nothing precedes it that day, that allowance
   is instead needed between the start of their working hours and the meeting.
   Nothing is required after their last engagement: they travel home on their
   own time.
5. It does not overlap their protected lunch, which runs `lunch_minutes` from
   `lunch_start_local` in their local time. **Priority 1 meetings may overlap
   lunch; priority 2 and 3 may not.**
6. It does not take their booked minutes for that day, standing commitments
   included, past `daily_cap_minutes`.

Requests are considered in this order: priority 1 first, then 2, then 3; within
the same priority, the request with more required attendees comes first; if that
still ties, the lower request id comes first.

If no slot in its window works, the request is declined. Otherwise the slot is
chosen by what it costs the requests still to come, not by being earliest. Take
the **first six** slots that work, in day-then-time order on the 15-minute grid.
For each, tentatively book the request there — with the same attendees it would
really have — then place the **next eight** requests in the order above, one at a
time, each into the earliest slot that then works for it, and count how many of
those eight get placed. The request takes the slot with the highest count; if
several tie, the earliest of them.

Once the slot is fixed, each optional attendee joins if conditions 1–6 hold for
them individually at that slot. An optional attendee who cannot make it is left
off; the meeting still goes ahead.

## Output

Write `/app/schedule.json`, a JSON object whose `schedule` value is an array with
one entry per request, **in the same order as `requests.json`**:

    {"schedule": [
      {"id": "REQ-001", "status": "scheduled", "day": "2026-03-03",
       "start_utc": "2026-03-03T16:30:00Z", "attendees": ["amara", "fen"]},
      {"id": "REQ-002", "status": "declined", "day": "", "start_utc": "",
       "attendees": []}
    ]}

`status` is `"scheduled"` or `"declined"`. For a scheduled request, `day` is the
booked day as `YYYY-MM-DD`, `start_utc` is the start instant in UTC as
`YYYY-MM-DDTHH:MM:SSZ`, and `attendees` lists every person actually attending —
required plus admitted optional — sorted alphabetically. For a declined request,
`day` and `start_utc` are empty strings and `attendees` is an empty array. Write
no other files.

Write `/app/schedule.json` as soon as you have a first pass over the requests and
overwrite it as you refine it. A missing file scores zero.

Your submission is correct when both of the following hold:

1. `/app/schedule.json` exists and is a JSON object whose `schedule` value is an
   array with exactly one well-formed entry per request, in the order they
   appear in `requests.json`, using the field names, types and value formats
   described above.
2. Every entry matches the booking the policy produces — the same status, the
   same day and start instant, and the same attendee list. All forty must be
   right.
