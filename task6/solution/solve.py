"""Reference solver for dynamo/schedule-recovery.

Reads /app/data/jobs.json and writes /app/answer.json. Pure standard library,
no randomness, no network.

The shape of the problem: each job fired at every whole minute whose LOCAL time
matched a five-field schedule, the local clock is a base UTC offset plus a list
of transitions, and the host was down for a handful of known intervals during
which nothing ran and nothing was recorded. Recover enough of each schedule to
say exactly when it will fire next.

Three things carry the work.

1. Anchor everything on local time, not UTC. Build the map from a local
   (date, hour, minute) to the UTC instants that reach it, by walking the window
   one minute at a time and applying the offset in force. A forward transition
   leaves local times with no instant at all; a backward one leaves some with
   two. Doing this by construction means the odd cases need no special handling
   anywhere else -- including in the prediction window, which contains one
   transition of each kind.

2. Read the minute and hour fields straight off the log, then decide each local
   date's status: it FIRED if every slot the job could have used that date is in
   the log, it was SILENT if none is, and it is UNKNOWN if the date has no
   usable slot at all -- every one deleted by a transition, clipped by the
   window, or swallowed by an outage. Silence during an outage is not evidence,
   and treating it as evidence is what makes a wrong day-of-month look right.

3. Search the day fields. Day-of-week has only 128 subsets, so enumerate them.
   For each, the day-of-month set follows from the dates the day-of-week term
   does not already account for: a firing date forces its day number in, a
   silent one forces it out. Anything neither forced in nor out is free, and
   free values are enumerated too. Every surviving pair is checked against the
   log in full, and the first survivor is projected forward -- over this data
   all survivors of a job agree on the future, which is why the answer is
   timestamps rather than a rewritten crontab.
"""
import datetime as dt
import itertools
import json
import os

DATA_PATH = "/app/data/jobs.json"
RESULT_PATH = "/app/answer.json"

ALL_DOM = frozenset(range(1, 32))
ALL_DOW = frozenset(range(7))


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def dow(d):
    """Cron day-of-week: Sunday 0 .. Saturday 6."""
    return (d.weekday() + 1) % 7


class Clock(object):
    def __init__(self, doc):
        self.base = doc["base_offset_min"]
        self.trans = sorted((parse_iso(t["utc"]), t["offset_min"])
                            for t in doc["transitions"])

    def offset(self, utc):
        off = self.base
        for t, o in self.trans:
            if utc >= t:
                off = o
        return off

    def local(self, utc):
        return utc + dt.timedelta(minutes=self.offset(utc))


def build_index(clock, start, end, outages=()):
    """(local date, hour, minute) -> UTC instants in [start, end) reaching it.

    Instants inside an outage are left out: nothing ran and nothing was
    recorded, so they carry no information either way.
    """
    idx = {}
    t, step = start, dt.timedelta(minutes=1)
    while t < end:
        if not any(a <= t < b for a, b in outages):
            lt = clock.local(t)
            idx.setdefault((lt.date(), lt.hour, lt.minute), []).append(t)
        t += step
    return idx


def day_pred(dom, dw, date):
    """Vixie semantics: day-of-month and day-of-week are OR'd when both are
    restricted, and AND'd -- which is to say, ignored -- when either is not."""
    dom_r, dw_r = len(dom) < 31, len(dw) < 7
    if dom_r and dw_r:
        return date.day in dom or dow(date) in dw
    if dom_r:
        return date.day in dom
    if dw_r:
        return dow(date) in dw
    return True


def date_status(index, dates, hours, mins, fires):
    """Per local date: True fired, False silent, None nothing observable."""
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
            return None                  # not an hour x minute product at all
        else:
            status[d] = False
    return status


def candidates(status, dates):
    """Every (day-of-month, day-of-week) pair whose predicate fits `status`."""
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
                    bad = True           # the day-of-week term already fires it
                    break
                continue
            (inc if s else exc).add(d.day)
        if bad or (inc & exc):
            continue
        free = [k for k in range(1, 32) if k not in inc and k not in exc]
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
    clock = Clock(doc["clock"])
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
        assert status is not None, "%s: log is not an hour x minute product" % job["id"]
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
    answers = {"schedules": solve(doc)}
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(answers, f)
        f.write("\n")
    os.replace(tmp, RESULT_PATH)


if __name__ == "__main__":
    main()
