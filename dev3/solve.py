"""Reference scheduler for dynamo/exec-calendar-triage.

The booking policy stated in the task description fully determines one schedule.
This implements it directly.

Time is handled as integer minutes since 2026-03-02T00:00:00Z. Every person
carries an explicit UTC offset, so no time zone database is consulted and the
result does not depend on the platform. Local midnight of day d for a person
whose offset is `off` sits at (d * 1440 - off) UTC minutes, which is the one
conversion the whole file rests on.

The part that is not a single forward pass is slot choice. Taking each request's
earliest feasible slot is what an obvious implementation does, and it is wrong
here: an early slot can consume the only window a later request had. So the
policy weighs a request's first few feasible slots by what each leaves behind --
tentatively book it, run the next several requests greedily, and count how many
of those still fit. The slot that strands the fewest wins, earliest breaking
ties. That keeps the answer unique while making a greedy solver diverge.

A slot works for a person only if all of these hold: they are not on PTO that
day; the meeting sits inside their working window; it does not overlap anything
already on their calendar; it does not touch their protected lunch unless the
meeting is priority 1; it does not push their booked minutes for the day past
the cap; and there is enough room to travel from whatever precedes it and to
whatever follows it that same day -- counting their own home site as where they
travel in from when nothing precedes it.

No answer key is consulted; only /app/data.
"""
import json

DATA = "/app/data"
OUT = "/app/schedule.json"

# Both stated in the task description.
CANDIDATES = 6          # feasible slots weighed per request
LOOKAHEAD = 8           # subsequent requests used to score a candidate


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt_utc(days, minute_of_week):
    """Minutes-since-week-epoch -> ISO 8601 Zulu."""
    import datetime
    base = datetime.datetime.strptime(days[0], "%Y-%m-%d")
    return (base + datetime.timedelta(minutes=minute_of_week)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class Calendar:
    """Per-person occupied intervals, in UTC minutes, each tagged with a site."""

    def __init__(self, person, days):
        self.days = days
        self.off = person["utc_offset_min"]
        self.ws = hhmm(person["work_start_local"])
        self.we = hhmm(person["work_end_local"])
        self.pto = set(person["pto_days"])
        self.home = person["home_site"]
        self.busy = []          # (start, end, site, day)
        self.used = {}          # day -> booked minutes
        for c in person["commitments"]:
            d = days.index(c["day"])
            s = self.local_to_utc(d, hhmm(c["start_local"]))
            self.busy.append((s, s + c["duration_min"], c["site"], c["day"]))
            self.used[c["day"]] = self.used.get(c["day"], 0) + c["duration_min"]
        self.busy.sort()

    def clone(self):
        """Cheap copy, for scoring a candidate slot without committing it."""
        c = Calendar.__new__(Calendar)
        c.days, c.off, c.ws, c.we = self.days, self.off, self.ws, self.we
        c.pto, c.home = self.pto, self.home
        c.busy = list(self.busy)
        c.used = dict(self.used)
        return c

    def local_to_utc(self, day_index, local_min):
        return day_index * 1440 - self.off + local_min

    def work_window(self, day_index):
        return (self.local_to_utc(day_index, self.ws),
                self.local_to_utc(day_index, self.we))

    def lunch(self, day_index, lunch_start, lunch_len):
        s = self.local_to_utc(day_index, lunch_start)
        return (s, s + lunch_len)

    def add(self, start, end, site, day):
        self.busy.append((start, end, site, day))
        self.busy.sort()
        self.used[day] = self.used.get(day, 0) + (end - start)


def travel_needed(sites, a, b):
    if a == b:
        return 0
    if a == "remote" or b == "remote":
        return sites["remote_switch_min"]
    return sites["travel_min"][a][b]


def can_attend(cal, day_index, day, start, dur, site, priority, cfg, sites):
    """Every condition the policy places on one person for one slot."""
    if day in cal.pto:
        return False
    end = start + dur

    ws, we = cal.work_window(day_index)
    if start < ws or end > we:
        return False

    if cal.used.get(day, 0) + dur > cfg["daily_cap_minutes"]:
        return False

    if priority != 1:
        ls, le = cal.lunch(day_index, hhmm(cfg["lunch_start_local"]),
                           cfg["lunch_minutes"])
        if start < le and ls < end:
            return False

    prev_item = None
    next_item = None
    for bs, be, bsite, bday in cal.busy:
        if bs < end and start < be:
            return False                    # overlap
        if bday != day:
            continue        # neighbours are the ones on this day, not the week
        if be <= start and (prev_item is None or be > prev_item[1]):
            prev_item = (bs, be, bsite)
        if bs >= end and (next_item is None or bs < next_item[0]):
            next_item = (bs, be, bsite)

    # People travel in from their home site to the first engagement of the day,
    # so the start of the working window carries the same allowance an adjacent
    # booking would. This is why the scan above is restricted to the day in
    # question: a meeting with nothing before it that day has no neighbour to
    # travel from, and must instead clear the trip from home. Leaving at the end
    # of the day is unconstrained -- they travel home on their own time.
    if prev_item is None:
        if start - ws < travel_needed(sites, cal.home, site):
            return False
    elif start - prev_item[1] < travel_needed(sites, prev_item[2], site):
        return False
    if next_item is not None:
        if next_item[0] - end < travel_needed(sites, site, next_item[2]):
            return False
    return True


def feasible_slots(cals, req, days, slot, cfg, sites, limit=None):
    """Slots this request could take, in day-then-time order."""
    out = []
    dur, site, prio = req["duration_min"], req["site"], req["priority"]
    for d in range(days.index(req["earliest_day"]),
                   days.index(req["latest_day"]) + 1):
        day = days[d]
        wins = [cals[p].work_window(d) for p in req["required"]]
        lo, hi = max(w[0] for w in wins), min(w[1] for w in wins)
        if hi - lo < dur:
            continue
        for start in range(((lo + slot - 1) // slot) * slot, hi - dur + 1, slot):
            if all(can_attend(cals[p], d, day, start, dur, site, prio, cfg,
                              sites) for p in req["required"]):
                out.append((d, day, start))
                if limit and len(out) >= limit:
                    return out
    return out


def attendees_at(cals, req, d, day, start, cfg, sites):
    going = list(req["required"])
    for p in req["optional"]:
        if can_attend(cals[p], d, day, start, req["duration_min"], req["site"],
                      req["priority"], cfg, sites):
            going.append(p)
    going.sort()
    return going


def commit(cals, req, day, start, going):
    for p in going:
        cals[p].add(start, start + req["duration_min"], req["site"], day)


def greedy_fill(cals, queue, days, slot, cfg, sites):
    """How many of `queue` still fit, each taking its earliest feasible slot."""
    n = 0
    for req in queue:
        hit = feasible_slots(cals, req, days, slot, cfg, sites, limit=1)
        if not hit:
            continue
        d, day, start = hit[0]
        commit(cals, req, day, start,
               attendees_at(cals, req, d, day, start, cfg, sites))
        n += 1
    return n


def solve(people_doc, sites, requests):
    days = people_doc["days"]
    slot = people_doc["slot_minutes"]
    cfg = people_doc
    cals = {p["id"]: Calendar(p, days) for p in people_doc["people"]}

    order = sorted(requests,
                   key=lambda r: (r["priority"], -len(r["required"]), r["id"]))

    placed = {}
    for i, req in enumerate(order):
        cands = feasible_slots(cals, req, days, slot, cfg, sites,
                               limit=CANDIDATES)
        if not cands:
            placed[req["id"]] = {"status": "declined", "day": "",
                                 "start_utc": "", "attendees": []}
            continue

        queue = order[i + 1:i + 1 + LOOKAHEAD]
        best = None
        for d, day, start in cands:
            trial = {k: v.clone() for k, v in cals.items()}
            commit(trial, req, day, start,
                   attendees_at(trial, req, d, day, start, cfg, sites))
            kept = greedy_fill(trial, queue, days, slot, cfg, sites)
            if best is None or kept > best[0]:
                best = (kept, d, day, start)

        _, d, day, start = best
        going = attendees_at(cals, req, d, day, start, cfg, sites)
        commit(cals, req, day, start, going)
        placed[req["id"]] = {"status": "scheduled", "day": day,
                             "start_utc": fmt_utc(days, start),
                             "attendees": going}

    # Emit in catalogue order, not placement order.
    return [dict(id=r["id"], **placed[r["id"]]) for r in requests]


def main():
    with open("%s/people.json" % DATA) as f:
        people_doc = json.load(f)
    with open("%s/sites.json" % DATA) as f:
        sites = json.load(f)
    with open("%s/requests.json" % DATA) as f:
        requests = json.load(f)["requests"]

    rows = solve(people_doc, sites, requests)
    with open(OUT, "w") as f:
        json.dump({"schedule": rows}, f)

    n = sum(1 for r in rows if r["status"] == "scheduled")
    print("scheduled %d of %d requests (%d declined) -> %s"
          % (n, len(rows), len(rows) - n, OUT))


if __name__ == "__main__":
    main()
