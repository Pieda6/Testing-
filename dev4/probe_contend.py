"""Can an engineered high-contention instance make greedy lose while exact
search stays cheap? Builds a small world by hand and measures both."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DAYS = ["2026-03-02", "2026-03-03"]
PEOPLE = [
    ("amara", -480, "08:00", "17:00", "hq"),
    ("bianca", -480, "08:00", "17:00", "hq"),
    ("cyrus", -300, "08:30", "17:30", "annex"),
    ("dara", -300, "08:30", "17:00", "annex"),
    ("fen", 0, "08:00", "16:30", "lab"),
]
SITES = {"sites": ["hq", "annex", "lab"],
         "travel_min": {"hq": {"hq": 0, "annex": 30, "lab": 45},
                        "annex": {"hq": 30, "annex": 0, "lab": 60},
                        "lab": {"hq": 45, "annex": 60, "lab": 0}},
         "remote_switch_min": 15}

# Requests deliberately pile onto the same few people and the same narrow
# windows, with durations that make "take the earliest slot" block two later
# meetings apiece.
SPEC = [
    # (id, prio, dur, site, required, optional, day)
    ("REQ-001", 2, 90, "hq", ["amara", "cyrus"], [], 0),
    ("REQ-002", 2, 60, "hq", ["amara", "cyrus"], [], 0),
    ("REQ-003", 2, 60, "hq", ["amara", "bianca"], [], 0),
    ("REQ-004", 1, 60, "annex", ["cyrus", "dara"], [], 0),
    ("REQ-005", 2, 90, "annex", ["bianca", "dara"], [], 0),
    ("REQ-006", 3, 30, "hq", ["amara", "dara"], [], 0),
    ("REQ-007", 2, 60, "lab", ["fen", "cyrus"], [], 1),
    ("REQ-008", 1, 45, "hq", ["amara", "fen"], [], 1),
    ("REQ-009", 3, 60, "annex", ["bianca", "cyrus"], [], 1),
    ("REQ-010", 2, 90, "hq", ["amara", "bianca"], [], 1),
    ("REQ-011", 2, 45, "annex", ["cyrus", "dara"], [], 1),
    ("REQ-012", 3, 30, "lab", ["fen", "dara"], [], 1),
    ("REQ-013", 2, 60, "hq", ["bianca", "fen"], [], 0),
    ("REQ-014", 3, 45, "annex", ["amara", "dara"], [], 1),
]


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    people = []
    for pid, off, ws, we, home in PEOPLE:
        people.append({"id": pid, "utc_offset_min": off,
                       "work_start_local": ws, "work_end_local": we,
                       "home_site": home, "pto_days": [], "commitments": []})
    json.dump({"days": DAYS, "slot_minutes": 15, "lunch_start_local": "12:00",
               "lunch_minutes": 30, "daily_cap_minutes": 240,
               "people": people},
              open("%s/people.json" % out_dir, "w"))
    json.dump(SITES, open("%s/sites.json" % out_dir, "w"))
    reqs = []
    for rid, prio, dur, site, req, opt, d in SPEC:
        reqs.append({"id": rid, "title": "Meeting " + rid, "priority": prio,
                     "duration_min": dur, "site": site, "required": req,
                     "optional": opt, "earliest_day": DAYS[d],
                     "latest_day": DAYS[d]})
    json.dump({"requests": reqs}, open("%s/requests.json" % out_dir, "w"))


if __name__ == "__main__":
    d = "/tmp/contend"
    build(d)
    import core as C
    import opt as O
    w = C.World(d)
    t = time.time()
    target, out, nodes = O.solve_exact(w, deadline=time.time() + 600)
    el = time.time() - t
    print("requests %d | exact optimum %s in %.1fs (%d nodes)"
          % (len(w.R), target, el, nodes))
    for name, kw in [
            ("greedy id order", dict(order_key=lambda r: r["id"])),
            ("greedy priority", dict(order_key=lambda r: (r["priority"], r["id"]))),
            ("look-ahead 6/8", dict(
                order_key=lambda r: (r["priority"], -len(r["required"]), r["id"]),
                lookahead=8, candidates=6))]:
        h = O.heuristic(w, **kw)
        same = sum(1 for r in w.R if h.get(r["id"]) == out.get(r["id"]))
        print("  %-18s counts %s vs %s | matches optimum on %d/%d rows"
              % (name, O.counts_of(w, h), target, same, len(w.R)))
