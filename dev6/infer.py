"""Reference inference core: recover each schedule from its log, then project.

Kept in dev/ while it is validated against truth.json. The shipped
solution/solve.py is this logic with the dev hooks removed.
"""
import datetime as dt
import itertools
import json

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
        self.trans = [(parse_iso(t["utc"]), t["offset_min"])
                      for t in doc["transitions"]]

    def offset(self, utc):
        off = self.base
        for t, o in self.trans:
            if utc >= t:
                off = o
        return off

    def local(self, utc):
        return utc + dt.timedelta(minutes=self.offset(utc))


def build_index(clock, start, end, outages=()):
    """(local date, hour, minute) -> UTC instants in [start, end) that hit it.

    A forward jump leaves local times with no instant at all; a backward jump
    leaves some with two. Instants inside an outage are dropped: nothing ran
    and nothing was recorded, so they carry no information either way.
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
    """Vixie semantics: dom and dow are OR'd when both are restricted."""
    dom_r, dw_r = len(dom) < 31, len(dw) < 7
    if dom_r and dw_r:
        return date.day in dom or dow(date) in dw
    if dom_r:
        return date.day in dom
    if dw_r:
        return dow(date) in dw
    return True


def date_status(index, dates, hours, mins, fires):
    """Per local date: True fired, False silent, None not observable.

    A date is only observable when at least one of the job's (hour, minute)
    slots exists in the window; a date whose slots are partly present and
    partly absent cannot come from an hour x minute product at all.
    """
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
    """Every (dom, dow) pair whose day predicate agrees with `status`."""
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
                bad = not s                    # the dow term already fires it
                if bad:
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


def solve(doc, all_candidates=False):
    clock = Clock(doc["clock"])
    outages = [(parse_iso(o["start_utc"]), parse_iso(o["end_utc"]))
               for o in doc.get("outages", ())]
    log = build_index(clock, parse_iso(doc["log_start_utc"]),
                      parse_iso(doc["log_end_utc"]), outages)
    pred = build_index(clock, parse_iso(doc["predict_start_utc"]),
                       parse_iso(doc["predict_end_utc"]))
    log_dates = sorted(set(d for d, _h, _m in log))
    local_of = {}
    for (d, h, m), times in log.items():
        for t in times:
            local_of[t] = (d, h, m)

    results = []
    for job in doc["jobs"]:
        fires = set(parse_iso(s) for s in job["fires"])
        hm = [local_of[t] for t in fires]
        hours = sorted(set(h for _d, h, _m in hm))
        mins = sorted(set(m for _d, _h, m in hm))
        status = date_status(log, log_dates, hours, mins, fires)
        if status is None:
            raise RuntimeError("%s: log is not an hour x minute product"
                               % job["id"])
        cands = candidates(status, log_dates)
        if not cands:
            raise RuntimeError("%s: no schedule reproduces the log" % job["id"])
        projections = set()
        for dom, dw in cands:
            projections.add(tuple(project(pred, hours, mins, dom, dw)))
            if not all_candidates:
                break
        results.append({"id": job["id"], "hours": hours, "mins": mins,
                        "candidates": cands, "projections": projections})
    return results
