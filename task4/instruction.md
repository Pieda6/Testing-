You are the executive assistant for a nine-person org spread across three time
zones. Twenty-six meeting requests came in for the week of Monday 2 March 2026,
and they have to be booked against calendars that are already partly full. Some
of them will not fit, and part of the job is saying so.

## What you have

`/app/data/people.json` — the week's days, the 15-minute booking grid, the lunch
and daily-load settings, and one record per person: their UTC offset in minutes,
their working hours in their own local time, their home site, days they are on
PTO, and the standing commitments already on their calendar (each with a day, a
local start, a duration, and a location).

`/app/data/sites.json` — the office sites, the travel time in minutes between
each pair, and the buffer needed when someone switches between remote and any
site.

`/app/data/requests.json` — the twenty-six requests, each with an id, priority,
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
4. Between it and whatever immediately precedes or follows it on their calendar
   that day, there is at least the travel time from `sites.json` — nothing if
   the two are at the same location, `remote_switch_min` if one is remote and
   the other is a site, otherwise the site-to-site figure.
5. It does not overlap their protected lunch, which runs `lunch_minutes` from
   `lunch_start_local` in their local time. **Priority 1 meetings may overlap
   lunch; priority 2 and 3 may not.**
6. It does not take their booked minutes for that day, standing commitments
   included, past `daily_cap_minutes`.

Requests are considered in this order: priority 1 first, then 2, then 3; within
the same priority, the request with more required attendees comes first; if that
still ties, the lower request id comes first.

Each request is booked into the **earliest slot that works** — the earliest day
in its window, and within that day the earliest start on the 15-minute grid.
If no slot in its window works, the request is declined.

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
   same day and start instant, and the same attendee list. All twenty-six must
   be right.
