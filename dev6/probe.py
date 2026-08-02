"""Feasibility probe for a schedule-recovery task.

Concept: give a log of past firing times; the agent infers each job's schedule
and reports the next firings. Graded on projected timestamps, so any expression
equivalent on the projection window is accepted.

The concept only works if the log DETERMINES the projection. This enumerates
every schedule in a stated grammar that is consistent with a job's log, and
checks whether they all project identically. If not, the concept is ill-posed.
"""
import itertools, datetime as dt

# Explicit DST model: no tz database, so results are platform-independent.
# US-style 2026: forward 2026-03-08 02:00 local, back 2026-11-01 02:00 local.
STD, DST = -5*60, -4*60
FWD = dt.datetime(2026, 3, 8, 7, 0)    # UTC instant of the spring transition
BACK = dt.datetime(2026, 11, 1, 6, 0)  # UTC instant of the autumn transition

def offset(utc):
    return DST if FWD <= utc < BACK else STD

def local(utc):
    return utc + dt.timedelta(minutes=offset(utc))

# Grammar: each field is a literal, a list, a range, or a step over its domain.
def field_options(lo, hi, kinds=("any", "lit", "step", "range")):
    out = []
    if "any" in kinds:
        out.append(frozenset(range(lo, hi+1)))
    if "lit" in kinds:
        for v in range(lo, hi+1):
            out.append(frozenset([v]))
    if "step" in kinds:
        for k in (2, 3, 4, 5, 6, 10, 12, 15, 20, 30):
            if k <= hi-lo:
                out.append(frozenset(range(lo, hi+1, k)))
    if "range" in kinds:
        for a in range(lo, hi+1):
            for b in range(a+1, hi+1):
                out.append(frozenset(range(a, b+1)))
    return list(dict.fromkeys(out))

def fires(spec, lt):
    """Vixie semantics: dom and dow are OR'd when both are restricted."""
    mi, ho, dom, mo, dow = spec
    if lt.minute not in mi or lt.hour not in ho or lt.month not in mo:
        return False
    dom_r = len(dom) < 31
    dow_r = len(dow) < 7
    d_ok, w_ok = lt.day in dom, (lt.weekday()+1) % 7 in dow
    if dom_r and dow_r:
        return d_ok or w_ok
    return d_ok and w_ok

def run(spec, start, end):
    out, t = [], start
    while t < end:
        if fires(spec, local(t)):
            out.append(t)
        t += dt.timedelta(minutes=1)
    return out


def consistent_specs(log, start, end, month_any=frozenset(range(1,13))):
    """Every grammar spec reproducing `log` exactly on [start,end)."""
    obs = set(log)
    mins = sorted({local(t).minute for t in log})
    hrs  = sorted({local(t).hour for t in log})
    # Over a multi-day window every minute/hour in the spec must appear, so the
    # observed sets pin those fields; we still allow supersets that some day
    # filter could hide, by testing candidates that contain the observed set.
    m_opts = [o for o in field_options(0,59) if set(mins) <= o]
    h_opts = [o for o in field_options(0,23) if set(hrs) <= o]
    d_opts = field_options(1,31,("any","lit"))
    w_opts = field_options(0,6,("any","lit"))
    out = []
    for mi in m_opts:
        for ho in h_opts:
            for dom in d_opts:
                for dow in w_opts:
                    spec = (mi,ho,dom,month_any,dow)
                    if set(run(spec,start,end)) == obs:
                        out.append(spec)
    return out
