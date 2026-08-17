"""Deterministic input generator for the schedule-recovery task.

Fixed seed => byte-identical output on every run and platform. All randomness
comes from SHA-256 of a fixed seed plus a counter; no PRNG library is involved.

The host's clock is described explicitly -- a base offset plus a list of
transition instants -- so nothing depends on a time zone database, and a library
primed with real tzdata gives wrong answers. The offsets deliberately do not
match any real zone.

Scheduler semantics, by construction: a job fires at every whole minute whose
LOCAL time matches its schedule. Everything awkward falls out of that rather
than needing its own rule -- a local time skipped by a forward transition never
fires, and a local time repeated by a backward transition fires twice. Both are
visible in the log, which is where the agent has to notice them.

The log runs twenty-five months. That length is not decoration: over a shorter
run a day-of-month value can land on the same weekday every time it occurs,
which leaves schedules that agree on the whole log and disagree about the
future -- and an outage can erase the single occurrence that separated them.
Twenty-five months puts every day-of-month value 1..30 on every weekday more
than once. Day 31 is the one exception, so the prediction window is chosen to
end before a 31st. dev6/validate.py is the arbiter: it enumerates every
schedule consistent with the log and checks they all predict the same thing.

Emits jobs.json (agent-visible). The true schedules stay here and never ship.
"""
import datetime as dt
import hashlib
import json
import os

SEED = b"dynamo/schedule-recovery/v1"
HERE = os.path.dirname(os.path.abspath(__file__))

# --- the host clock -------------------------------------------------------
# Base offset and transitions, chosen not to coincide with any real zone.
BASE_OFFSET = -210                       # -03:30
TRANSITIONS = [                          # (utc instant, new offset in minutes)
    (dt.datetime(2024, 6, 10, 4, 0), -150),    # forward: deletes local times
    (dt.datetime(2024, 10, 21, 4, 30), -210),  # backward: repeats local times
    (dt.datetime(2025, 7, 15, 4, 0), -150),    # forward again
    (dt.datetime(2025, 11, 4, 4, 30), -210),   # backward: repeats local times
    (dt.datetime(2026, 2, 17, 4, 30), -150),   # forward, inside the prediction
    (dt.datetime(2026, 3, 8, 5, 0), -210),     # backward, inside the prediction
]
LOG_START = dt.datetime(2024, 1, 1, 0, 0)
LOG_END = dt.datetime(2026, 2, 1, 0, 0)
PRED_END = dt.datetime(2026, 3, 31, 0, 0)

# Intervals when the scheduler host was down. Nothing was recorded, and
# nothing ran. Silence inside one of these is not evidence about a schedule,
# which is the whole point: the inference has to treat those dates as
# unobserved rather than as "did not match". Deliberately placed clear of the
# clock transitions, so the deleted and repeated local times stay visible.
OUTAGES = [
    (dt.datetime(2024, 4, 8, 0, 0), dt.datetime(2024, 4, 11, 0, 0)),
    (dt.datetime(2024, 8, 19, 6, 0), dt.datetime(2024, 8, 20, 18, 0)),
    (dt.datetime(2024, 12, 30, 0, 0), dt.datetime(2025, 1, 2, 0, 0)),
    (dt.datetime(2025, 3, 5, 0, 0), dt.datetime(2025, 3, 8, 12, 0)),
    (dt.datetime(2025, 6, 11, 9, 0), dt.datetime(2025, 6, 12, 21, 0)),
    (dt.datetime(2025, 9, 29, 0, 0), dt.datetime(2025, 10, 2, 0, 0)),
    (dt.datetime(2025, 11, 17, 0, 0), dt.datetime(2025, 11, 18, 0, 0)),
    (dt.datetime(2025, 12, 24, 0, 0), dt.datetime(2025, 12, 27, 0, 0)),
    (dt.datetime(2026, 1, 13, 0, 0), dt.datetime(2026, 1, 14, 6, 0)),
]

N_JOBS = 30


def down(utc):
    return any(a <= utc < b for a, b in OUTAGES)


def det_int(counter, nbits=32):
    b = hashlib.sha256(SEED + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def offset_at(utc):
    off = BASE_OFFSET
    for t, o in TRANSITIONS:
        if utc >= t:
            off = o
    return off


def to_local(utc):
    return utc + dt.timedelta(minutes=offset_at(utc))


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
        # The month field is always `*`: a log that does not cover every month
        # cannot distinguish "odd months" from "not February", and the two
        # predict differently. Stated in the instruction as a restriction.
        S.append((frozenset(mi), frozenset(ho), frozenset(dom),
                  ALL_M, frozenset(dow)))

    # dom AND dow both restricted -> OR. The headline trap.
    add([0], [0], dom=[13], dow=[5])
    add([30], [4], dom=[1, 15], dow=[0])
    add([0], [9], dom=[7], dow=[3])
    add([45], [22], dom=[28], dow=[6])
    add([15], [3], dom=[1, 11, 21, 31], dow=[2])
    add([0], [6], dom=[2, 3, 5, 7], dow=[1, 4])

    # Local times that a transition deletes or repeats.
    add([45], [0])                       # local 00:45 daily
    add([15], [1])                       # local 01:15 daily
    add([0, 30], [1, 2])                 # straddles both shifted hours
    add([0], [4], dom=[15])              # lands on a transition day

    # Ordinary shapes.
    add([0, 30], [9, 13, 17])
    add([0], [0, 6, 12, 18])
    add([5], [12], dow=[1, 2, 3, 4, 5])
    add([0], [0])
    add([0], [12], dom=[1])
    add([20], [6], dow=[0, 6])
    add([0, 20, 40], [8])
    add([0], [23], dom=[31])             # only long months
    add([10], [5], dom=[29])             # skips February in a non-leap year
    add([0], [7], dom=[30, 31])          # absent from February entirely
    add([50], [17], dom=[2, 9, 16, 23, 30])
    add([25], [11], dow=[3])
    add([0], [21], dom=[5, 20])

    # Fill the rest deterministically from the same shape vocabulary.
    i = 0
    while len(S) < N_JOBS:
        k = det_int("shape%d" % i) % 5
        m = det_int("m%d" % i) % 60
        h = det_int("h%d" % i) % 24
        if k == 0:
            add([m], [h])
        elif k == 1:
            add([m], [h], dow=[det_int("w%d" % i) % 7])
        elif k == 2:
            add([m], [h], dom=[1 + det_int("d%d" % i) % 28])
        elif k == 3:
            add([m], [h], dom=[1 + det_int("d%d" % i) % 28],
                dow=[det_int("w%d" % i) % 7])
        else:
            a = det_int("a%d" % i) % 21
            add([m], [a, a + 1, a + 2])
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
        "clock": {
            "base_offset_min": BASE_OFFSET,
            "transitions": [{"utc": iso(t), "offset_min": o}
                            for t, o in TRANSITIONS],
        },
        "log_start_utc": iso(LOG_START),
        "log_end_utc": iso(LOG_END),
        "outages": [{"start_utc": iso(a), "end_utc": iso(b)}
                    for a, b in OUTAGES],
        "predict_start_utc": iso(LOG_END),
        "predict_end_utc": iso(PRED_END),
        "jobs": jobs,
    }
    with open(os.path.join(HERE, "jobs.json"), "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"jobs": truth}, f, indent=1)
        f.write("\n")

    n_fire = sum(len(j["fires"]) for j in jobs)
    silent = [j["id"] for j in jobs if not j["fires"]]
    size = os.path.getsize(os.path.join(HERE, "jobs.json"))
    print("jobs %d | log firings %d | bytes %d | never-firing jobs: %s"
          % (len(jobs), n_fire, size, silent or "none"))


if __name__ == "__main__":
    main()
