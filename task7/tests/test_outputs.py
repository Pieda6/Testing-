"""Verifier for dynamo/hai-surveillance-adjudication.

An adjudication is a set of discrete determinations -- which events are
reportable, on what date, charged to which ward, with which organisms, and
whether a central line was involved -- so grading is exact and needs no
tolerance. Every value is a date, a ward name, an organism name from a fixed
vocabulary, or an integer.

expected.json holds the answer key together with the patient order and the ward
order, and is overlaid at /tests only at verification time, never in the agent
image. The orders are kept here rather than read back from /app/data because
that directory is writable by the agent.

The key was established by two adjudicators that share no code and were written
the other way round -- one over date intervals with a candidate pool, one over
explicit per-calendar-day tables -- both derived from the shipped manual rather
than from each other. They agree on all 36 patients and on every ward's central
line day count. That agreement is the whole basis for trusting the key: unlike a
task where a recovered model can be replayed against its own source data, an
adjudication has no self-consistency test, so a single implementation's output
would be nothing more than one implementation's opinion.

Grading is all-or-nothing across all 36 patients and all ward denominators.
"""
import json
import os
import re

RESULT_PATH = "/app/answer.json"
HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED_PATH = os.path.join(HERE, "expected.json")

PATIENT_FIELDS = ("id", "uti", "bsi")
UTI_FIELDS = ("date_of_event", "ward", "organisms")
BSI_FIELDS = ("central_line_associated", "date_of_event", "organisms", "ward")
DAY_FIELDS = ("days", "ward")
ID_RE = re.compile(r"\APT-\d{3}\Z")
DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


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


def _is_int(x):
    """True for a real integer. bool is a subclass of int and is not accepted."""
    return isinstance(x, int) and not isinstance(x, bool)


def _check_event(where, ev, fields, wards, i):
    assert isinstance(ev, dict), "%s event %d must be a JSON object" % (where, i)
    assert set(ev) == set(fields), (
        "%s event %d has fields %s, expected %s"
        % (where, i, sorted(ev), sorted(fields)))
    assert isinstance(ev["date_of_event"], str) \
        and DATE_RE.match(ev["date_of_event"]), (
        "%s event %d: date_of_event must be YYYY-MM-DD" % (where, i))
    assert ev["ward"] in wards, (
        "%s event %d: ward %r is not one of the wards in the records"
        % (where, i, ev["ward"]))
    orgs = ev["organisms"]
    assert isinstance(orgs, list) and orgs, (
        "%s event %d: organisms must be a non-empty array" % (where, i))
    assert all(isinstance(o, str) and o for o in orgs), (
        "%s event %d: every organism must be a non-empty string" % (where, i))
    assert orgs == sorted(set(orgs)), (
        "%s event %d: organisms must be sorted and free of duplicates"
        % (where, i))
    if "central_line_associated" in fields:
        assert isinstance(ev["central_line_associated"], bool), (
            "%s event %d: central_line_associated must be a JSON boolean"
            % (where, i))


def _parse(obj, key):
    """Return the submitted answer, or raise AssertionError on bad shape."""
    assert isinstance(obj, dict), "answer.json must be a JSON object"
    for k in ("patients", "central_line_days"):
        assert k in obj, "answer.json must contain key %r" % k
    rows, days = obj["patients"], obj["central_line_days"]
    assert isinstance(rows, list), "'patients' must be a JSON array"
    assert isinstance(days, list), "'central_line_days' must be a JSON array"
    assert len(rows) == len(key["patient_ids"]), (
        "expected %d patients, got %d" % (len(key["patient_ids"]), len(rows)))
    assert len(days) == len(key["wards"]), (
        "expected %d ward entries, got %d" % (len(key["wards"]), len(days)))

    wards = set(key["wards"])
    for i, p in enumerate(rows):
        assert isinstance(p, dict), "patient %d must be a JSON object" % i
        assert set(p) == set(PATIENT_FIELDS), (
            "patient %d has fields %s, expected %s"
            % (i, sorted(p), sorted(PATIENT_FIELDS)))
        assert isinstance(p["id"], str) and ID_RE.match(p["id"]), (
            "patient %d: id must look like PT-001" % i)
        for name, fields in (("uti", UTI_FIELDS), ("bsi", BSI_FIELDS)):
            evs = p[name]
            assert isinstance(evs, list), (
                "%s: %s must be a JSON array" % (p["id"], name))
            for j, ev in enumerate(evs):
                _check_event("%s %s" % (p["id"], name), ev, fields, wards, j)
            dates = [e["date_of_event"] for e in evs]
            assert dates == sorted(dates), (
                "%s: %s events must be ordered by date_of_event" % (p["id"], name))

    for i, row in enumerate(days):
        assert isinstance(row, dict), "central_line_days %d must be an object" % i
        assert set(row) == set(DAY_FIELDS), (
            "central_line_days %d has fields %s, expected %s"
            % (i, sorted(row), sorted(DAY_FIELDS)))
        assert row["ward"] in wards, (
            "central_line_days %d: ward %r is not one of the wards in the "
            "records" % (i, row["ward"]))
        assert _is_int(row["days"]) and row["days"] >= 0, (
            "central_line_days %d: days must be a non-negative integer" % i)
    return rows, days


def test_output_schema():
    """Criterion 1: /app/answer.json is a JSON object carrying 'patients' --
    one well-formed entry per patient, in the order the patients appear in
    records.json -- and 'central_line_days', one entry per ward in the order
    the wards are listed, using the documented fields, types and formats."""
    key = _key()
    rows, days = _parse(_read_result(), key)
    misordered = [i for i, (g, e) in enumerate(zip(rows, key["patient_ids"]))
                  if g["id"] != e]
    assert not misordered, (
        "%d patients are out of record order (first at index %d)"
        % (len(misordered), misordered[0]))
    wrong_wards = [i for i, (g, e) in enumerate(zip(days, key["wards"]))
                   if g["ward"] != e]
    assert not wrong_wards, (
        "%d ward entries are out of the order the records list them (first at "
        "index %d)" % (len(wrong_wards), wrong_wards[0]))


def test_adjudication_is_correct():
    """Criterion 2: every reportable event is present with the right date of
    event, ward and organisms, no event that is not reportable appears, central
    line association is right, and every ward's central line day count is
    right."""
    key = _key()
    rows, days = _parse(_read_result(), key)
    want = {p["id"]: p for p in key["patients"]}

    wrong = []
    for got in rows:
        exp = want[got["id"]]
        for name in ("uti", "bsi"):
            if got[name] == exp[name]:
                continue
            wrong.append("%s: %s expected %d event(s) %s, got %d %s"
                         % (got["id"], name, len(exp[name]),
                            json.dumps(exp[name]), len(got[name]),
                            json.dumps(got[name])))

    got_days = {r["ward"]: r["days"] for r in days}
    exp_days = {r["ward"]: r["days"] for r in key["central_line_days"]}
    for ward in key["wards"]:
        if got_days[ward] != exp_days[ward]:
            wrong.append("%s: %d central line days reported, expected %d"
                         % (ward, got_days[ward], exp_days[ward]))

    assert not wrong, ("%d determination(s) are wrong; first: %s"
                       % (len(wrong), wrong[0]))
