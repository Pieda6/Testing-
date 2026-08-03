"""Is a clock-transition rule uniquely recoverable from the transitions a log shows?

If the agent has to DERIVE the future transition instants instead of reading them
off a list, the rule must be pinned by the ones the log contains -- otherwise the
answer stops being well defined. Grammar a solver would plausibly consider:

    (month, day-of-month, local time)            fixed date
    (month, ordinal, weekday, local time)        ordinal in 1..5 or "last"
"""
import calendar, datetime as dt

def nth_weekday(y, m, wd, k):
    """k in 1..5 -> that occurrence; k == 0 -> last."""
    days = [d for d in range(1, calendar.monthrange(y, m)[1] + 1)
            if dt.date(y, m, d).weekday() == wd]
    if k == 0:
        return days[-1]
    return days[k - 1] if k <= len(days) else None

def fits(dates, spec):
    kind = spec[0]
    for d in dates:
        if kind == "dom":
            if d.month != spec[1] or d.day != spec[2]:
                return False
        else:
            _k, m, wd, k = spec
            if d.month != m or nth_weekday(d.year, m, wd, k) != d.day:
                return False
    return True

def candidates(dates):
    out = []
    for m in range(1, 13):
        for dom in range(1, 32):
            if fits(dates, ("dom", m, dom)):
                out.append(("dom", m, dom))
        for wd in range(7):
            for k in (0, 1, 2, 3, 4, 5):
                if fits(dates, ("nth", m, wd, k)):
                    out.append(("nth", m, wd, k))
    return out

def last_sun(y, m):
    return dt.date(y, m, nth_weekday(y, m, 6, 0))

for years in (2, 3, 4, 5):
    ys = range(2022, 2022 + years)
    for label, month in (("last Sunday of April", 4),
                         ("last Sunday of September", 9)):
        obs = [last_sun(y, month) for y in ys]
        c = candidates(obs)
        print("%d observations | %-26s -> %d rule(s) fit: %s"
              % (years, label, len(c), c if len(c) <= 4 else "..."))
    print()
