"""Verifier for dynamo/exec-calendar-triage.

Ground truth is the schedule the booking policy produces, held in
tests/expected.json. That file is overlaid only at verification time and is
never copied into the agent's image, so the answer is not reachable from inside
the task.

The policy determines exactly one schedule -- two independently written
implementations of it agree on all 40 requests -- so the comparison is exact and
there is no tolerance to calibrate.
"""
import json
import os
import re

RESULT_PATH = "/app/schedule.json"
EXPECTED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "expected.json")

FIELDS = ("id", "status", "day", "start_utc", "attendees")
STATUSES = ("scheduled", "declined")
DAY_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def _read_result():
    """Read /app/schedule.json, refusing to follow a symlink at the final path
    component (O_NOFOLLOW anti-alias guard)."""
    fd = os.open(RESULT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "r") as f:
            return json.load(f)
    except OSError:
        os.close(fd)
        raise


def _expected():
    with open(EXPECTED_PATH) as f:
        return json.load(f)["schedule"]


def _parse(obj, expected):
    """Return the submitted rows, or raise AssertionError on bad shape.

    Formats are checked strictly: day and start_utc must match the documented
    patterns exactly when a request is scheduled and be empty strings when it is
    declined, and attendees must be a sorted list of unique strings.
    """
    assert isinstance(obj, dict), "schedule.json must be a JSON object"
    assert "schedule" in obj, "schedule.json must contain key 'schedule'"
    rows = obj["schedule"]
    assert isinstance(rows, list), "'schedule' must be a JSON array"
    assert len(rows) == len(expected), (
        "expected %d entries, got %d" % (len(expected), len(rows)))

    for i, r in enumerate(rows):
        assert isinstance(r, dict), "entry %d must be a JSON object" % i
        assert set(r) == set(FIELDS), (
            "entry %d has fields %s, expected %s" % (i, sorted(r), sorted(FIELDS)))
        for key in ("id", "status", "day", "start_utc"):
            assert isinstance(r[key], str), (
                "entry %d: %s must be a string" % (i, key))
        assert r["status"] in STATUSES, (
            "entry %d: status must be one of %s" % (i, list(STATUSES)))

        att = r["attendees"]
        assert isinstance(att, list), "entry %d: attendees must be an array" % i
        assert all(isinstance(a, str) for a in att), (
            "entry %d: attendee ids must be strings" % i)
        assert len(set(att)) == len(att), (
            "entry %d: attendees contains duplicates" % i)
        assert att == sorted(att), (
            "entry %d: attendees must be sorted alphabetically" % i)

        if r["status"] == "scheduled":
            assert DAY_RE.match(r["day"]), (
                "entry %d: day must be YYYY-MM-DD" % i)
            assert UTC_RE.match(r["start_utc"]), (
                "entry %d: start_utc must be YYYY-MM-DDTHH:MM:SSZ" % i)
            assert att, "entry %d: a scheduled meeting needs attendees" % i
        else:
            assert r["day"] == "" and r["start_utc"] == "", (
                "entry %d: a declined request must have empty day/start_utc" % i)
            assert att == [], (
                "entry %d: a declined request must have no attendees" % i)
    return rows


def test_output_schema():
    """Criterion 1: /app/schedule.json is a JSON object whose 'schedule' is an
    array with one well-formed entry per request, in the order they appear in
    requests.json, using the documented field names, types and formats."""
    expected = _expected()
    rows = _parse(_read_result(), expected)
    misordered = [i for i, (g, e) in enumerate(zip(rows, expected))
                  if g["id"] != e["id"]]
    assert not misordered, (
        "%d entries are out of request order (first at index %d)"
        % (len(misordered), misordered[0]))


def test_schedule_matches_policy():
    """Criterion 2: every entry matches the booking the policy produces -- same
    status, same day and start instant, same attendee list -- checked against
    held-out ground truth, so a schedule that merely looks plausible fails."""
    expected = _expected()
    rows = _parse(_read_result(), expected)

    wrong = []
    for g, e in zip(rows, expected):
        bad = [k for k in FIELDS if g[k] != e[k]]
        if bad:
            wrong.append((e["id"], bad))
    assert not wrong, (
        "%d of %d requests are wrong (first: %s, fields %s)"
        % (len(wrong), len(expected), wrong[0][0], wrong[0][1]))
