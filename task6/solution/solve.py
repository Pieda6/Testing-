"""Reference solver for dynamo/schedule-recovery.

Reads /app/data/jobs.json and writes /app/answer.json. Pure standard library,
no randomness, no network.

The shape of the problem: each job fired at every whole minute whose LOCAL time
matched a five-field schedule; the host's local clock is a base UTC offset that
changes twice a year on a rule; and the host was down for a handful of known
intervals during which nothing ran and nothing was recorded. The input gives
the base offset and the outages. It does NOT give the clock's transitions --
those have to come out of the log, and then be projected forward.

Two stages, and the second is the one that carries the difficulty.

STAGE 1 -- THE CLOCK.
Jobs that fire every day read the clock directly: their local firing times are
fixed, so their UTC times are that fixed set displaced by the offset in force,
and every change shows up as all of them moving together on one day. Finding
the day is easy. Pinning the instant needs a little care, and the job to lean
on is one whose local times are the even hours: shift those by an hour and they
land on the odd hours, a disjoint set, so there is something to check in every
hour of the day. A contiguous run of times would be no use -- slide it by an
hour and it covers itself everywhere except at its two ends, so the change
could hide anywhere inside. Direction needs a second job, since the even hours
look the same shifted forwards or backwards; any job on a different minute
settles it, because its UTC times move the opposite way.

With the changes in hand, fit the rule -- month, weekday, which occurrence,
which local hour -- and run it forward through the prediction window.

Nothing about that last step can be checked against the log. A rule that is off
by a week, or that reads "4th <weekday>" where the truth is "last <weekday>",
reproduces every logged firing exactly and is still wrong about the future. It
is worth being deliberate about the occurrence: the two readings agree in a
month with four of that weekday and disagree in a month with five, so only the
five-weekday months in the log carry the distinction.

STAGE 2 -- THE SCHEDULES.
Build the map from a local (date, hour, minute) to the UTC instants that reach
it, over the log and over the prediction window, skipping minutes inside an
outage. That map has the transitions built into its shape: a local time deleted
by a forward change has no instants, one repeated by a backward change has two.
The minute and hour fields read straight off the log. Then classify each local
date -- FIRED if every slot it could have used is in the log, SILENT if none
is, UNKNOWN if it has no usable slot at all, which is what keeps outage silence
from being read as evidence. What is left is the day fields: enumerate the 127
non-empty day-of-week subsets, and for each, the day-of-month set follows from
the dates the day-of-week term does not already cover, under cron's rule that
the two are OR'd when both are restricted. Check every surviving pair against
the whole log, then project.
"""
import calendar
import datetime as dt
import itertools
import json
import os

DATA_PATH = "/app/data/jobs.json"
RESULT_PATH = "/app/answer.json"

ALL_DOM = frozenset(range(1, 32))
ALL_DOW = frozenset(range(7))
DAY = 1440


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def dow(d):
    """Cron day-of-week: Sunday 0 .. Saturday 6."""
    return (d.weekday() + 1) % 7


def nth_weekday(year, month, weekday, ordinal):
    """ordinal 1..5 picks that occurrence; 0 picks the last one."""
    days = [d for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if dt.date(year, month, d).weekday() == weekday]
    if ordinal == 0:
        return days[-1]
    return days[ordinal - 1] if ordinal <= len(days) else None


# --------------------------------------------------------------------------
# Stage 1: the clock
# --------------------------------------------------------------------------

def probe_jobs(jobs):
    """The jobs that fire on (nearly) every day of the log.

    Their local firing times are a fixed set displaced by the offset in force,
    so they read the clock directly. Several are needed rather than one: a
    pattern on even hours pins WHEN a 60-minute change happened, because
    shifting it by an hour lands on the odd hours and so distinguishes every
    hour of the day, but it cannot say which DIRECTION the clock moved, since
    shifting it the other way lands on the odd hours too. A job at some other
    minute settles the direction, because its UTC times move the opposite way.
    """
    cover = [(len(set(s[:10] for s in j["fires"])), j) for j in jobs]
    best = max(c for c, _j in cover)
    daily = [j for c, j in cover if c >= 0.9 * best]
    daily.sort(key=lambda j: -len(j["fires"]))
    return daily


def daily_shifts(job):
    """Per UTC date, the displacement of that date's firing times against the
    most common pattern. Constant except where the offset moves."""
    by_date = {}
    for s in job["fires"]:
        t = parse_iso(s)
        by_date.setdefault(t.date(), set()).add(t.hour * 60 + t.minute)

    counts = {}
    for v in by_date.values():
        counts[frozenset(v)] = counts.get(frozenset(v), 0) + 1
    base = max(counts, key=counts.get)

    shifts = {}
    for d, v in by_date.items():
        best, best_cost = None, None
        # smallest displacement first: a pattern can be invariant under a large
        # shift (even hours are, under 120 minutes) and the small one is meant
        for delta in sorted(range(-240, 241, 15), key=lambda x: (abs(x), x)):
            moved = frozenset((x - delta) % DAY for x in base)
            cost = len(moved ^ v)
            if best_cost is None or cost < best_cost:
                best, best_cost = delta, cost
        shifts[d] = (best, best_cost)
    return shifts, base


def transition_days(shifts):
    """Dates on which the displacement moves. The change itself is on that day
    or shortly before it, so `locate` searches a window around it."""
    days = sorted(shifts)
    out, run = [], shifts[days[0]][0]
    for i in range(1, len(days)):
        cur = shifts[days[i]][0]
        if cur != run and shifts[days[i]][1] == 0:
            out.append(days[i])
            run = cur
    return out


class StaticClock(object):
    """A clock with a single transition, used while locating that transition."""

    def __init__(self, before, at, after):
        self.before, self.at, self.after = before, at, after

    def local(self, utc):
        off = self.after if utc >= self.at else self.before
        return utc + dt.timedelta(minutes=off)


def locate(probes, day, off_before, outages):
    """Pin one transition: its instant, and the offset in force after it.

    The probe job fires at a fixed set of local times every day. Read that set
    off a quiet day before the change, then ask which (instant, new offset)
    pair reproduces exactly what the probe did across the change -- including
    the firings a forward change deletes and the doubled ones a backward change
    creates. Only whole local hours are considered, as the rule form says.
    """
    # a settled day before the change, clear of outages, to read patterns from
    quiet = None
    for back in range(4, 30):
        d = day - dt.timedelta(days=back)
        lo = dt.datetime.combine(d, dt.time())
        if any(a < lo + dt.timedelta(days=1) and lo < b for a, b in outages):
            continue
        if all(any(t.date() == d for t in p) for p in probes):
            quiet = d
            break
    assert quiet, "no settled day before %s to read the patterns from" % day
    patterns = [set((t.hour * 60 + t.minute + off_before) % DAY
                    for t in p if t.date() == quiet) for p in probes]

    lo = dt.datetime.combine(day - dt.timedelta(days=2), dt.time())
    hi = dt.datetime.combine(day + dt.timedelta(days=1), dt.time())
    actual = [sorted(t for t in p if lo <= t < hi) for p in probes]
    span = int((hi - lo).total_seconds()) // 60
    minutes = [lo + dt.timedelta(minutes=i) for i in range(span)]
    live = [t for t in minutes if not any(a <= t < b for a, b in outages)]

    hits = []
    for delta in (-120, -90, -60, -30, 30, 60, 90, 120):
        after = off_before + delta
        for cand in minutes:
            if (cand + dt.timedelta(minutes=off_before)).minute:
                continue                       # changes land on a whole hour
            clock = StaticClock(off_before, cand, after)
            locals_ = [(t, clock.local(t)) for t in live]
            ok = True
            for pattern, want in zip(patterns, actual):
                got = [t for t, lt in locals_
                       if lt.hour * 60 + lt.minute in pattern]
                if got != want:
                    ok = False
                    break
            if ok:
                hits.append((cand, after))
    return hits


class Clock(object):
    def __init__(self, base, transitions):
        self.base = base
        self.trans = sorted(transitions)

    def offset(self, utc):
        off = self.base
        for t, o in self.trans:
            if utc >= t:
                off = o
        return off

    def local(self, utc):
        return utc + dt.timedelta(minutes=self.offset(utc))


def fit_rules(observed, base_offset):
    """Fit (month, weekday, ordinal, local hour) rules to the observed changes.

    Returns every set of rules consistent with all of them. Over this data
    exactly one fits.
    """
    groups = {}
    for utc, new_off, prev_off in observed:
        local = utc + dt.timedelta(minutes=prev_off)
        groups.setdefault(new_off, []).append((local, prev_off))

    fits = {}
    for new_off, obs in groups.items():
        ok = []
        for month in range(1, 13):
            for wd in range(7):
                for ordinal in range(0, 6):
                    hours = set(l.hour for l, _p in obs)
                    if len(hours) != 1:
                        continue
                    good = all(l.month == month
                               and nth_weekday(l.year, month, wd, ordinal)
                               == l.day for l, _p in obs)
                    if good:
                        ok.append((month, wd, ordinal, obs[0][0].hour, new_off))
        fits[new_off] = ok
    return fits


def expand(rules, base_offset, start, end):
    out, off = [], base_offset
    for year in range(start.year, end.year + 1):
        dated = []
        for month, wd, ordinal, hour, new in rules:
            day = nth_weekday(year, month, wd, ordinal)
            if day is None:
                continue
            dated.append((dt.date(year, month, day), hour, new))
        dated.sort()
        for day, hour, new in dated:
            local = dt.datetime.combine(day, dt.time(hour))
            utc = local - dt.timedelta(minutes=off)
            if start <= utc < end:
                out.append((utc, new))
            off = new
    return out


def recover_clock(doc):
    """The clock over the log AND the prediction window, from the log alone."""
    base = doc["clock"]["base_offset_min"]
    outages = [(parse_iso(o["start_utc"]), parse_iso(o["end_utc"]))
               for o in doc.get("outages", ())]
    daily = probe_jobs(doc["jobs"])
    probes = [[parse_iso(s) for s in j["fires"]] for j in daily]
    shifts, _pattern = daily_shifts(daily[0])

    observed, off = [], base
    for day in transition_days(shifts):
        hits = locate(probes, day, off, outages)
        assert len(hits) == 1, ("%d whole-hour instants reproduce the change "
                                "near %s: %s" % (len(hits), day, hits))
        utc, new_off = hits[0]
        observed.append((utc, new_off, off))
        off = new_off

    fits = fit_rules(observed, base)
    sets = [list(c) for c in itertools.product(*fits.values())]
    assert sets, "no rule fits the observed changes"

    end = parse_iso(doc["predict_end_utc"])
    start = parse_iso(doc["log_start_utc"])
    clocks = [Clock(base, expand(rules, base, start, end)) for rules in sets]
    return clocks[0], sets, observed


# --------------------------------------------------------------------------
# Stage 2: the schedules
# --------------------------------------------------------------------------

def build_index(clock, start, end, outages=()):
    idx = {}
    t, step = start, dt.timedelta(minutes=1)
    while t < end:
        if not any(a <= t < b for a, b in outages):
            lt = clock.local(t)
            idx.setdefault((lt.date(), lt.hour, lt.minute), []).append(t)
        t += step
    return idx


def day_pred(dom, dw, date):
    dom_r, dw_r = len(dom) < 31, len(dw) < 7
    if dom_r and dw_r:
        return date.day in dom or dow(date) in dw
    if dom_r:
        return date.day in dom
    if dw_r:
        return dow(date) in dw
    return True


def date_status(index, dates, hours, mins, fires):
    status = {}
    for d in dates:
        want = set()
        for h in hours:
            for m in mins:
                want.update(index.get((d, h, m), ()))
        if not want:
            status[d] = None
        elif want <= fires:
            status[d] = True
        elif want & fires:
            return None
        else:
            status[d] = False
    return status


def candidates(status, dates):
    out = []
    for bits in range(1, 128):
        dw = frozenset(i for i in range(7) if bits >> i & 1)
        full_w = len(dw) == 7

        if all(status[d] is None or status[d] == day_pred(ALL_DOM, dw, d)
               for d in dates):
            out.append((ALL_DOM, dw))

        inc, exc, bad = set(), set(), False
        for d in dates:
            s = status[d]
            if s is None:
                continue
            if not full_w and dow(d) in dw:
                if not s:
                    bad = True
                    break
                continue
            (inc if s else exc).add(d.day)
        if bad or (inc & exc):
            continue
        free = [k for k in range(1, 32) if k not in inc and k not in exc]
        if len(free) > 14:
            raise RuntimeError("%d free day numbers" % len(free))
        for r in range(len(free) + 1):
            for extra in itertools.combinations(free, r):
                dom = frozenset(inc | set(extra))
                if not dom or len(dom) > 30:
                    continue
                if all(status[d] is None or status[d] == day_pred(dom, dw, d)
                       for d in dates):
                    out.append((dom, dw))
    return out


def project(index, hours, mins, dom, dw):
    out = []
    for (d, h, m), times in index.items():
        if h in hours and m in mins and day_pred(dom, dw, d):
            out.extend(times)
    return sorted(out)


def solve(doc):
    clock, _rule_sets, _observed = recover_clock(doc)
    outages = [(parse_iso(o["start_utc"]), parse_iso(o["end_utc"]))
               for o in doc.get("outages", ())]
    log = build_index(clock, parse_iso(doc["log_start_utc"]),
                      parse_iso(doc["log_end_utc"]), outages)
    pred = build_index(clock, parse_iso(doc["predict_start_utc"]),
                       parse_iso(doc["predict_end_utc"]))
    dates = sorted(set(d for d, _h, _m in log))
    local_of = {}
    for (d, h, m), times in log.items():
        for t in times:
            local_of[t] = (h, m)

    answers = []
    for job in doc["jobs"]:
        fires = set(parse_iso(s) for s in job["fires"])
        hm = [local_of[t] for t in fires]
        hours = sorted(set(h for h, _m in hm))
        mins = sorted(set(m for _h, m in hm))
        status = date_status(log, dates, hours, mins, fires)
        assert status is not None, (
            "%s: log is not an hour x minute product" % job["id"])
        cands = candidates(status, dates)
        assert cands, "%s: no schedule reproduces the log" % job["id"]
        dom, dw = cands[0]
        answers.append({"id": job["id"],
                        "fires": [iso(t) for t in
                                  project(pred, hours, mins, dom, dw)]})
    return answers


def main():
    with open(DATA_PATH) as f:
        doc = json.load(f)
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"schedules": solve(doc)}, f)
        f.write("\n")
    os.replace(tmp, RESULT_PATH)


if __name__ == "__main__":
    main()
