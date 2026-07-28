"""Deterministic input generator for dynamo/exec-calendar-triage.

Fixed seed => byte-identical output on every run and platform. All randomness
derives from SHA-256 of a fixed seed plus a counter; no PRNG library is used.

Models one working week for a manager's org: nine people across three time
zones, three office sites plus remote, a pile of standing commitments, and
twenty-six meeting requests competing for the same hours.

Design notes that matter for gradeability:

  * UTC offsets are stored explicitly rather than as time zone names. The week
    is deliberately placed before the US DST transition, but storing offsets
    removes any dependence on the platform's tz database, which is a real
    source of non-reproducibility.
  * Everything lands on a 15-minute grid, so "the earliest feasible start" is a
    well-defined discrete choice rather than a continuous optimum.
  * The generator does NOT compute the answer. It emits inputs only; the
    expected schedule is produced by the reference solver and then checked by an
    independent validator. That way a bug in the solver cannot quietly become
    ground truth.

Emits:
  people.json    - working hours, offsets, PTO, standing commitments (agent-visible)
  sites.json     - travel time matrix (agent-visible)
  requests.json  - the meeting requests to place (agent-visible)
"""
import hashlib
import json

SEED = b"dynamo/exec-calendar/v3"

# Mon-Fri. Chosen to sit before the 2026 US DST change so fixed offsets hold
# all week; offsets are stored in the data regardless.
DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]
SLOT_MIN = 15

SITES = ["hq", "annex", "lab"]
# Minutes of travel between sites. Symmetric, zero on the diagonal.
TRAVEL = {
    ("hq", "annex"): 30,
    ("hq", "lab"): 45,
    ("annex", "lab"): 60,
}
REMOTE_SWITCH_MIN = 15      # switching between remote and any site

# Three regions. The overlaps are deliberate: PT and ET share ~6.5h, ET and UK
# share ~3h, and PT and UK share only 16:00-16:30 UTC -- so a meeting spanning
# all three regions fits in exactly one half-hour window in the whole day, and
# only if it is short.
PEOPLE = [
    # (id, utc_offset_minutes, work_start_local, work_end_local, home_site)
    ("amara",   -480, "08:00", "17:00", "hq"),      # PT
    ("bianca",  -480, "08:00", "17:00", "hq"),      # PT
    ("hugo",    -480, "08:00", "16:30", "hq"),      # PT
    ("cyrus",   -300, "08:30", "17:30", "annex"),   # ET
    ("dara",    -300, "08:30", "17:00", "annex"),   # ET
    ("emeka",   -300, "09:00", "17:30", "hq"),      # ET
    ("iris",    -300, "08:30", "17:30", "hq"),      # ET
    ("fen",        0, "08:00", "16:30", "lab"),     # UK
    ("gita",       0, "08:00", "16:00", "lab"),     # UK
]

REGION = {
    "amara": "pt", "bianca": "pt", "hugo": "pt",
    "cyrus": "et", "dara": "et", "emeka": "et", "iris": "et",
    "fen": "uk", "gita": "uk",
}

LUNCH_LOCAL = "12:00"
LUNCH_MIN = 30
DAILY_CAP_MIN = 240         # per person, including standing commitments

N_REQUESTS = 40

# Two rules -- the priority-1 lunch exemption and the daily cap boundary -- are
# only real if some booking actually exercises them. Left to the seed alone they
# never fire: no priority-1 meeting ever wants a lunch slot, and no one ever
# reaches the cap. So one day is designed rather than sampled. fen and gita have
# their Tuesday mornings filled to 12:00 and to 210 booked minutes, which makes
# the earliest slot left that day the lunch slot, and makes a 30-minute booking
# land on exactly 240. A priority-1 request may take it; a priority-2 one may
# not, and a cap test written with >= instead of > rejects it.
DESIGNED_DAY = "2026-03-03"
DESIGNED = {
    "fen": [("08:00", 60, "lab"), ("09:15", 60, "lab"), ("10:30", 90, "lab")],
    "gita": [("08:00", 60, "lab"), ("09:15", 60, "lab"), ("10:30", 90, "lab")],
}


def det_bytes(counter, n):
    out = b""
    i = 0
    while len(out) < n:
        out += hashlib.sha256(SEED + counter.encode() + i.to_bytes(4, "big")).digest()
        i += 1
    return out[:n]


def det_int(counter, nbits):
    b = det_bytes(counter, (nbits + 7) // 8)
    return int.from_bytes(b, "big") & ((1 << nbits) - 1)


def det_pick(counter, seq):
    return seq[det_int(counter, 32) % len(seq)]


def travel_between(a, b):
    """Minutes needed to get from site a to site b."""
    if a == b:
        return 0
    if a == "remote" or b == "remote":
        return REMOTE_SWITCH_MIN
    return TRAVEL.get((a, b)) or TRAVEL[(b, a)]


def hhmm_to_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def build_people():
    out = []
    for idx, (pid, off, ws, we, home) in enumerate(PEOPLE):
        # A couple of people take a day off; spread so no day loses too many.
        pto = []
        if det_int(f"haspto{pid}", 16) % 3 == 0:
            pto.append(DAYS[det_int(f"ptoday{pid}", 16) % len(DAYS)])

        commitments = []
        for d_i, day in enumerate(DAYS):
            if day in pto:
                continue
            if pid in DESIGNED and day == DESIGNED_DAY:
                for st, dur, site in DESIGNED[pid]:
                    commitments.append({"day": day, "start_local": st,
                                        "duration_min": dur, "site": site})
                continue
            n = det_int(f"ncom{pid}{d_i}", 16) % 3      # 0..2 standing blocks
            used = []
            for k in range(n):
                dur = det_pick(f"cdur{pid}{d_i}{k}", [30, 45, 60])
                # Local start on the grid, inside the person's working window.
                span = hhmm_to_min(we) - hhmm_to_min(ws) - dur
                if span <= 0:
                    continue
                start_local = hhmm_to_min(ws) + (
                    (det_int(f"cst{pid}{d_i}{k}", 32) % (span // SLOT_MIN + 1)) * SLOT_MIN)
                # Skip if it collides with one already emitted for this person.
                site = det_pick(f"csite{pid}{d_i}{k}", SITES + ["remote"])
                # The input calendars must themselves obey the travel rule --
                # otherwise the data contradicts the policy the agent is asked
                # to apply. That includes the start of the day: people travel in
                # from their home site, so a standing commitment cannot sit
                # closer to the opening of the working window than the trip in
                # takes.
                if start_local - hhmm_to_min(ws) < travel_between(home, site):
                    continue
                if any(start_local + dur + travel_between(site, s_site) > s
                       and s + t + travel_between(s_site, site) > start_local
                       for s, t, s_site in used):
                    continue
                used.append((start_local, dur, site))
                commitments.append({
                    "day": day,
                    "start_local": "%02d:%02d" % divmod(start_local, 60),
                    "duration_min": dur,
                    "site": site,
                })
        commitments.sort(key=lambda c: (c["day"], c["start_local"]))
        out.append({
            "id": pid,
            "utc_offset_min": off,
            "work_start_local": ws,
            "work_end_local": we,
            "home_site": home,
            "pto_days": pto,
            "commitments": commitments,
        })
    return out


def build_requests(people):
    by_region = {}
    for p in people:
        by_region.setdefault(REGION[p["id"]], []).append(p["id"])
    out = []
    for i in range(N_REQUESTS):
        rid = "REQ-%03d" % (i + 1)
        prio = det_pick(f"prio{i}", [1, 1, 2, 2, 2, 3, 3, 3])

        # Most meetings are within one region, as in a real org; a few span two,
        # and a couple span all three.
        mode = det_pick(f"mode{i}", ["single"] * 6 + ["dual"] * 3 + ["all"])
        if mode == "single":
            regions = [det_pick(f"reg{i}", ["pt", "et", "uk"])]
        elif mode == "dual":
            pair = det_pick(f"pair{i}", [("pt", "et"), ("et", "uk"), ("pt", "uk")])
            regions = list(pair)
        else:
            regions = ["pt", "et", "uk"]

        # A meeting that has to reach across all three regions can only fit the
        # narrow shared window, so those are kept short by the organiser.
        if mode == "all" or set(regions) == {"pt", "uk"}:
            dur = det_pick(f"dur{i}", [30, 30, 30, 45])
        else:
            dur = det_pick(f"dur{i}", [30, 30, 45, 60, 60, 90])

        pool = [p for r in regions for p in by_region[r]]
        nreq = min(len(pool), 2 + det_int(f"nreq{i}", 16) % 4)
        nopt = min(len(pool) - nreq, det_int(f"nopt{i}", 16) % 3)

        chosen, avail = [], list(pool)
        # Guarantee at least one attendee from each region the meeting spans.
        for r in regions:
            cands = [p for p in by_region[r] if p in avail]
            pick = cands[det_int(f"seed{i}{r}", 32) % len(cands)]
            chosen.append(pick)
            avail.remove(pick)
        while len(chosen) < nreq + nopt and avail:
            p = avail.pop(det_int(f"who{i}{len(chosen)}", 32) % len(avail))
            chosen.append(p)
        nreq = max(nreq, len(regions))
        required = sorted(chosen[:nreq])
        optional = sorted(chosen[nreq:nreq + nopt])

        site = det_pick(f"site{i}", SITES + ["remote", "remote"])
        e_i = det_int(f"win{i}", 16) % 3
        l_i = min(len(DAYS) - 1, e_i + 1 + det_int(f"winl{i}", 16) % 3)
        out.append({
            "id": rid,
            "title": "Meeting %s" % rid,
            "priority": prio,
            "duration_min": dur,
            "site": site,
            "required": required,
            "optional": optional,
            "earliest_day": DAYS[e_i],
            "latest_day": DAYS[l_i],
        })
    return out


def build_sites():
    matrix = {}
    for a in SITES:
        matrix[a] = {}
        for b in SITES:
            if a == b:
                matrix[a][b] = 0
            else:
                matrix[a][b] = TRAVEL.get((a, b)) or TRAVEL[(b, a)]
    return {
        "sites": SITES,
        "travel_min": matrix,
        "remote_switch_min": REMOTE_SWITCH_MIN,
    }


def dump(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.write("\n")


if __name__ == "__main__":
    people = build_people()
    requests = build_requests(people)
    dump("people.json", {
        "days": DAYS,
        "slot_minutes": SLOT_MIN,
        "lunch_start_local": LUNCH_LOCAL,
        "lunch_minutes": LUNCH_MIN,
        "daily_cap_minutes": DAILY_CAP_MIN,
        "people": people,
    })
    dump("sites.json", build_sites())
    dump("requests.json", {"requests": requests})

    ncom = sum(len(p["commitments"]) for p in people)
    npto = sum(len(p["pto_days"]) for p in people)
    print("people: %d | standing commitments: %d | pto days: %d | requests: %d"
          % (len(people), ncom, npto, len(requests)))
    for pr in (1, 2, 3):
        print("  priority %d: %d requests"
              % (pr, sum(1 for r in requests if r["priority"] == pr)))
