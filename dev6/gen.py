"""Deterministic input generator for the schedule-recovery task.

Fixed seed => byte-identical output on every run and platform. All randomness
comes from SHA-256 of a fixed seed plus a counter; no PRNG library is involved.

WHAT CHANGED FROM v1, AND WHY
-----------------------------
v1 shipped the host's clock as an explicit list of transition instants,
including the two inside the prediction window. Pass@2 solved it twice at
reward 1.0 in under half an hour: with the semantics disclosed and the future
clock handed over, everything the agent needed was checkable against the log,
and it closed the loop with its own simulator.

So the transition list is gone. The input gives the base offset and nothing
else about the clock. The transitions are plainly visible in the log -- at one
instant every job's UTC firing times shift together -- so recovering when they
happened and by how much is now part of the inference. Extrapolating them into
the prediction window is the part that cannot be checked against the log: a
rule that is off by a week, or that reads "4th Sunday" for "last Sunday", still
reproduces every logged firing exactly and is still wrong about the future.

The host changes its offset on a rule, twice a year, at a whole hour local
time, on a fixed occurrence of a fixed weekday in a fixed month. Both rules are
"last Sunday", and the calendar was chosen (see calsearch.py) so that:

  * the log pins "last" against "4th" -- March 2024, March 2025 and November
    2025 each have five Sundays, so the two readings disagree there and the log
    settles it; and
  * the prediction window pins it too -- March 2026 and November 2026 also have
    five Sundays, so an agent that carelessly infers "4th Sunday" predicts the
    22nd instead of the 29th and loses.

The offsets deliberately match no real zone, so a library primed with tzdata is
wrong. Scheduler semantics, by construction: a job fires at every whole minute
whose LOCAL time matches its schedule. Everything awkward falls out of that --
a local time deleted by a forward transition never fires, one repeated by a
backward transition fires twice.

Emits jobs.json (agent-visible). The true schedules and the true clock rules
stay here and never ship.
"""
import calendar
import datetime as dt
import hashlib
import json
import os

SEED = b"dynamo/schedule-recovery/v2"
HERE = os.path.dirname(os.path.abspath(__file__))

# --- the host clock -------------------------------------------------------
BASE_OFFSET = -210                       # -03:30 before the first transition

# (month, weekday, ordinal, local hour, offset after the change).
# weekday is Monday 0 .. Sunday 6; ordinal 0 means the last occurrence.
RULES = [
    (3, 6, 0, 1, -150),                  # last Sunday of March, 01:00 local
    (11, 6, 0, 1, -210),                 # last Sunday of November, 01:00 local
]

LOG_START = dt.datetime(2023, 1, 1, 0, 0)
LOG_END = dt.datetime(2026, 2, 1, 0, 0)
PRED_END = dt.datetime(2026, 12, 6, 0, 0)

# Intervals when the scheduler host was down. Nothing ran and nothing was
# recorded, so silence inside one is not evidence about a schedule. Placed
# clear of the transitions, which stay fully visible.
OUTAGES = [
    (dt.datetime(2023, 5, 9, 0, 0), dt.datetime(2023, 5, 12, 0, 0)),
    (dt.datetime(2023, 8, 21, 6, 0), dt.datetime(2023, 8, 22, 18, 0)),
    (dt.datetime(2024, 1, 6, 0, 0), dt.datetime(2024, 1, 9, 0, 0)),
    (dt.datetime(2024, 6, 18, 12, 0), dt.datetime(2024, 6, 19, 12, 0)),
    (dt.datetime(2024, 10, 2, 0, 0), dt.datetime(2024, 10, 5, 0, 0)),
    (dt.datetime(2025, 2, 14, 0, 0), dt.datetime(2025, 2, 15, 6, 0)),
    (dt.datetime(2025, 7, 23, 0, 0), dt.datetime(2025, 7, 26, 0, 0)),
    (dt.datetime(2025, 12, 24, 0, 0), dt.datetime(2025, 12, 27, 0, 0)),
]

N_JOBS = 24


def nth_weekday(year, month, weekday, ordinal):
    """ordinal 1..5 picks that occurrence; 0 picks the last one."""
    days = [d for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if dt.date(year, month, d).weekday() == weekday]
    if ordinal == 0:
        return days[-1]
    return days[ordinal - 1] if ordinal <= len(days) else None


def build_transitions(start, end):
    """Expand the rules into (utc instant, new offset), chronologically.

    The local hour named by a rule is read in the offset in force just BEFORE
    the change, which is what makes a forward rule delete a stretch of local
    time and a backward one repeat it.
    """
    out, off = [], BASE_OFFSET
    for year in range(start.year, end.year + 1):
        dated = []
        for month, wd, ordinal, hour, new in RULES:
            day = nth_weekday(year, month, wd, ordinal)
            dated.append((dt.date(year, month, day), hour, new))
        dated.sort()
        for day, hour, new in dated:
            local = dt.datetime.combine(day, dt.time(hour))
            utc = local - dt.timedelta(minutes=off)
            if start <= utc < end:
                out.append((utc, new))
            off = new
    return out


TRANSITIONS = build_transitions(LOG_START, PRED_END)


def offset_at(utc):
    off = BASE_OFFSET
    for t, o in TRANSITIONS:
        if utc >= t:
            off = o
    return off


def to_local(utc):
    return utc + dt.timedelta(minutes=offset_at(utc))


def down(utc):
    return any(a <= utc < b for a, b in OUTAGES)


def det_int(counter, nbits=32):
    b = hashlib.sha256(SEED + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def matches(spec, lt):
    """Vixie semantics: when both dom and dow are restricted they are OR'd."""
    mi, ho, dom, mo, dow = spec
    if lt.minute not in mi or lt.hour not in ho or lt.month not in mo:
        return False
    dom_r, dow_r = len(dom) < 31, len(dow) < 7
    d_ok, w_ok = lt.day in dom, (lt.weekday() + 1) % 7 in dow
    if dom_r and dow_r:
        return d_ok or w_ok
    return d_ok and w_ok


def fire_times(spec, start, end):
    """Every whole minute in [start, end) whose local time matches."""
    out, t = [], start
    step = dt.timedelta(minutes=1)
    while t < end:
        if matches(spec, to_local(t)):
            out.append(t)
        t += step
    return out


ALL_M = frozenset(range(1, 13))
ALL_D = frozenset(range(1, 32))
ALL_W = frozenset(range(7))


def build_specs():
    """Hand-picked shapes, so every trap is present rather than hoped for."""
    S = []

    def add(mi, ho, dom=ALL_D, dow=ALL_W):
        # The month field is always `*`. Month restrictions would multiply the
        # candidate search by 2^12 for no extra insight.
        S.append((frozenset(mi), frozenset(ho), frozenset(dom),
                  ALL_M, frozenset(dow)))

    # The clock probe. Its local times are every even hour on the hour, which
    # a 60-minute shift moves onto the ODD hours -- a disjoint set, with a
    # distinguishing instant in every hour of the day. That is what pins a
    # transition to a single whole hour. A contiguous grid would not: shift a
    # contiguous band by an hour and it lands on itself everywhere except its
    # two ends, so the change could hide anywhere inside it.
    add([0], range(0, 24, 2))

    # dom AND dow both restricted -> OR. The headline trap.
    add([0], [0], dom=[13], dow=[5])
    add([30], [4], dom=[1, 15], dow=[0])
    add([0], [9], dom=[7], dow=[3])
    add([45], [22], dom=[28], dow=[6])
    add([15], [3], dom=[1, 11, 21, 31], dow=[2])
    add([0], [6], dom=[2, 3, 5, 7], dow=[1, 4])

    # Single local times a transition deletes or repeats.
    add([15], [1])                       # local 01:15 daily
    add([45], [0])                       # local 00:45 daily
    add([0], [1], dom=[29])              # rare day, inside the moved hour

    # Ordinary shapes.
    add([0], [12])
    add([5], [12], dow=[1, 2, 3, 4, 5])
    add([0], [12], dom=[1])
    add([20], [6], dow=[0, 6])
    add([0], [23], dom=[31])             # only long months
    add([10], [5], dom=[29])             # skips February in a non-leap year
    add([0], [7], dom=[30, 31])          # absent from February entirely
    add([50], [17], dom=[2, 9, 16, 23, 30])
    add([25], [11], dow=[3])
    add([0], [21], dom=[5, 20])

    # Fill the rest deterministically from the same shape vocabulary.
    i = 0
    while len(S) < N_JOBS:
        k = det_int("shape%d" % i) % 4
        m = det_int("m%d" % i) % 60
        h = det_int("h%d" % i) % 24
        if k == 0:
            add([m], [h])
        elif k == 1:
            add([m], [h], dow=[det_int("w%d" % i) % 7])
        elif k == 2:
            add([m], [h], dom=[1 + det_int("d%d" % i) % 28])
        else:
            add([m], [h], dom=[1 + det_int("d%d" % i) % 28],
                dow=[det_int("w%d" % i) % 7])
        i += 1
    return S[:N_JOBS]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    specs = build_specs()
    jobs, truth = [], []
    for k, spec in enumerate(specs):
        jid = "JOB-%03d" % (k + 1)
        log = [t for t in fire_times(spec, LOG_START, LOG_END) if not down(t)]
        jobs.append({"id": jid, "fires": [iso(t) for t in log]})
        truth.append({"id": jid, "spec": [sorted(f) for f in spec]})

    doc = {
        "clock": {"base_offset_min": BASE_OFFSET},
        "log_start_utc": iso(LOG_START),
        "log_end_utc": iso(LOG_END),
        "predict_start_utc": iso(LOG_END),
        "predict_end_utc": iso(PRED_END),
        "outages": [{"start_utc": iso(a), "end_utc": iso(b)}
                    for a, b in OUTAGES],
        "jobs": jobs,
    }
    with open(os.path.join(HERE, "jobs.json"), "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"jobs": truth,
                   "transitions": [{"utc": iso(t), "offset_min": o}
                                   for t, o in TRANSITIONS]}, f, indent=1)
        f.write("\n")

    n_fire = sum(len(j["fires"]) for j in jobs)
    silent = [j["id"] for j in jobs if not j["fires"]]
    size = os.path.getsize(os.path.join(HERE, "jobs.json"))
    print("jobs %d | log firings %d | bytes %d | never-firing: %s"
          % (len(jobs), n_fire, size, silent or "none"))
    print("transitions:")
    for t, o in TRANSITIONS:
        where = "log" if t < LOG_END else "PREDICTION"
        print("  %s -> %+d  (%s, %s)" % (iso(t), o, t.strftime("%a %d %b %Y"),
                                         where))


if __name__ == "__main__":
    main()
