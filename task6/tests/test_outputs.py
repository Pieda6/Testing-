"""Verifier for dynamo/schedule-recovery.

The answer is a set of future firing instants per job, so the grading is exact
and needs no tolerance: the submitted timestamps either are the ones the
scheduler produces or they are not.

expected.json holds the answer key and the bounds of the prediction window, and
is overlaid at /tests only at verify time, never in the agent image. The bounds
are kept here rather than read back from /app/data because that directory is
writable by the agent.

The key was established twice over, by two paths that share no code: once by
running the reference inference over the log and projecting the recovered
schedules forward, and once by simulating the generator's hidden schedules
forward directly. Both agree on all 1581 instants. The generator also verified
that every schedule consistent with the log -- 39 of them across the thirty
jobs, several jobs admitting more than one -- projects to the same instants, so
the answer is well defined even though the schedule is not always unique.

Grading is all-or-nothing across all thirty jobs.
"""
import json
import os
import re

RESULT_PATH = "/app/answer.json"
HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED_PATH = os.path.join(HERE, "expected.json")

FIELDS = ("id", "fires")
ID_RE = re.compile(r"\AJOB-\d{3}\Z")
TS_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def _read_result():
    """Read /app/answer.json, refusing to follow a symlink at the final path
    component (O_NOFOLLOW anti-alias guard)."""
    fd = os.open(RESULT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "r") as f:
            return json.load(f)
    except OSError:
        os.close(fd)
        raise


def _key():
    with open(EXPECTED_PATH) as f:
        return json.load(f)


def _expected():
    return _key()["schedules"]


def _window():
    k = _key()
    return k["predict_start_utc"], k["predict_end_utc"]


def _parse(obj, expected):
    """Return the submitted entries, or raise AssertionError on bad shape."""
    assert isinstance(obj, dict), "answer.json must be a JSON object"
    assert "schedules" in obj, "answer.json must contain key 'schedules'"
    rows = obj["schedules"]
    assert isinstance(rows, list), "'schedules' must be a JSON array"
    assert len(rows) == len(expected), (
        "expected %d entries, got %d" % (len(expected), len(rows)))

    start, end = _window()
    for i, r in enumerate(rows):
        assert isinstance(r, dict), "entry %d must be a JSON object" % i
        assert set(r) == set(FIELDS), (
            "entry %d has fields %s, expected %s"
            % (i, sorted(r), sorted(FIELDS)))
        assert isinstance(r["id"], str) and ID_RE.match(r["id"]), (
            "entry %d: id must look like JOB-001" % i)
        fires = r["fires"]
        assert isinstance(fires, list), (
            "entry %d: fires must be a JSON array" % i)
        assert all(isinstance(t, str) and TS_RE.match(t) for t in fires), (
            "entry %d: every instant must be a string of the form "
            "YYYY-MM-DDTHH:MM:SSZ" % i)
        assert all(fires[j] < fires[j + 1] for j in range(len(fires) - 1)), (
            "entry %d: instants must be strictly ascending" % i)
        outside = [t for t in fires if not start <= t < end]
        assert not outside, (
            "entry %d: instant %s is outside [%s, %s)"
            % (i, outside[0], start, end))
    return rows


def test_output_schema():
    """Criterion 1: /app/answer.json is a JSON object whose 'schedules' is an
    array with one well-formed entry per job, in the order the jobs appear in
    jobs.json, using the documented fields, types and formats."""
    expected = _expected()
    rows = _parse(_read_result(), expected)
    misordered = [i for i, (g, e) in enumerate(zip(rows, expected))
                  if g["id"] != e["id"]]
    assert not misordered, (
        "%d entries are out of job order (first at index %d)"
        % (len(misordered), misordered[0]))


def test_predicted_firings_are_exact():
    """Criterion 2: every entry lists exactly the instants that job fires in
    the prediction window -- none missing and none extra, across all thirty."""
    expected = _expected()
    rows = _parse(_read_result(), expected)

    wrong = []
    for got, exp in zip(rows, expected):
        g, e = got["fires"], exp["fires"]
        if g == e:
            continue
        gs, es = set(g), set(e)
        missing, extra = sorted(es - gs), sorted(gs - es)
        detail = []
        if missing:
            detail.append("%d missing (first %s)" % (len(missing), missing[0]))
        if extra:
            detail.append("%d not fired (first %s)" % (len(extra), extra[0]))
        if not detail:
            detail.append("%d instants repeated" % (len(g) - len(gs)))
        wrong.append("%s: %d instants given, %d expected; %s"
                     % (exp["id"], len(g), len(e), ", ".join(detail)))

    assert not wrong, ("%d of %d jobs are wrong; first: %s"
                       % (len(wrong), len(expected), wrong[0]))
