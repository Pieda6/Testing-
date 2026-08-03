"""Pick the transition rule and the log/prediction years.

Two things must both hold, and they pull in opposite directions:

  PINNED    at least one occurrence inside the log must separate "last <weekday>"
            from "4th <weekday>", or the rule is not determined and the task is
            ill posed;
  BITES     the occurrence inside the PREDICTION window must separate them too,
            or an agent that carelessly infers "4th" is still right and the trap
            is decorative.

Search every (month, weekday) for a run of years where both hold.
"""
import calendar, datetime as dt

def occurrences(y, m, wd):
    return [d for d in range(1, calendar.monthrange(y, m)[1] + 1)
            if dt.date(y, m, d).weekday() == wd]

NAMES = "Mon Tue Wed Thu Fri Sat Sun".split()
hits = []
for m in range(1, 13):
    for wd in range(7):
        for y0 in range(2020, 2025):
            log_years = [y0, y0 + 1, y0 + 2]          # >=3 observations
            pred_year = y0 + 3
            pinned = any(len(occurrences(y, m, wd)) == 5 for y in log_years)
            bites = len(occurrences(pred_year, m, wd)) == 5
            if pinned and bites:
                last = occurrences(pred_year, m, wd)[-1]
                fourth = occurrences(pred_year, m, wd)[3]
                hits.append((m, wd, log_years, pred_year, fourth, last))

for m, wd, ly, py, fourth, last in hits:
    print("%-3s last %s | log %s | predict %d: 4th=%d last=%d (differ by %d days)"
          % (calendar.month_abbr[m], NAMES[wd], ly, py, fourth, last, last - fourth))
