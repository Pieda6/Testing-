"""Verifier for dynamo/arborescence-battery.

Correctness is checked by certificate, not by string-matching one blessed
answer. For each instance the submitted edge set is re-examined against the
graph itself: it must genuinely be a spanning arborescence rooted at the given
root, its weights must sum to the total the submission claims, and that total
must equal the true optimum. An instance may have several optimal arborescences;
any of them is accepted, and nothing that is merely valid-but-not-optimal is.

Two files are overlaid here at verification time and are never in the agent's
image: expected.json, holding the optimal weight of every instance, and
instances.json, a trusted copy of the graphs. The copy matters -- /app/data is
writable by the agent, so the verifier must not read the graphs from there.
"""
import json
import os
import re

RESULT_PATH = "/app/answer.json"
HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED_PATH = os.path.join(HERE, "expected.json")
INSTANCES_PATH = os.path.join(HERE, "instances.json")

FIELDS = ("id", "feasible", "total_weight", "edges")
ID_RE = re.compile(r"\AG-\d{3}\Z")


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


def _expected():
    with open(EXPECTED_PATH) as f:
        return json.load(f)["answers"]


def _instances():
    with open(INSTANCES_PATH) as f:
        return {i["id"]: i for i in json.load(f)["instances"]}


def _is_int(x):
    """True for a real integer. bool is a subclass of int and is not accepted."""
    return isinstance(x, int) and not isinstance(x, bool)


def _parse(obj, expected):
    """Return the submitted answers, or raise AssertionError on bad shape.

    Types are checked strictly: feasible is a JSON boolean, total_weight a plain
    integer, and edges a sorted list of unique non-negative integers. An
    instance with no arborescence must carry weight 0 and no edges.
    """
    assert isinstance(obj, dict), "answer.json must be a JSON object"
    assert "answers" in obj, "answer.json must contain key 'answers'"
    rows = obj["answers"]
    assert isinstance(rows, list), "'answers' must be a JSON array"
    assert len(rows) == len(expected), (
        "expected %d entries, got %d" % (len(expected), len(rows)))

    for i, r in enumerate(rows):
        assert isinstance(r, dict), "entry %d must be a JSON object" % i
        assert set(r) == set(FIELDS), (
            "entry %d has fields %s, expected %s"
            % (i, sorted(r), sorted(FIELDS)))
        assert isinstance(r["id"], str) and ID_RE.match(r["id"]), (
            "entry %d: id must look like G-001" % i)
        assert isinstance(r["feasible"], bool), (
            "entry %d: feasible must be a JSON boolean" % i)
        assert _is_int(r["total_weight"]), (
            "entry %d: total_weight must be an integer" % i)

        e = r["edges"]
        assert isinstance(e, list), "entry %d: edges must be an array" % i
        assert all(_is_int(x) for x in e), (
            "entry %d: edge ids must be integers" % i)
        assert all(x >= 0 for x in e), (
            "entry %d: edge ids must be non-negative" % i)
        assert len(set(e)) == len(e), "entry %d: edges contains duplicates" % i
        assert e == sorted(e), "entry %d: edges must be sorted ascending" % i

        if not r["feasible"]:
            assert r["total_weight"] == 0, (
                "entry %d: an instance with no arborescence must report "
                "total_weight 0" % i)
            assert e == [], (
                "entry %d: an instance with no arborescence must report no "
                "edges" % i)
    return rows


def _arborescence_fault(inst, edge_ids, claimed):
    """None if `edge_ids` is a spanning arborescence of weight `claimed`."""
    by_id = {e["id"]: e for e in inst["edges"]}
    missing = [i for i in edge_ids if i not in by_id]
    if missing:
        return "edge id %d is not in this instance" % missing[0]
    chosen = [by_id[i] for i in edge_ids]
    if len(chosen) != inst["n"] - 1:
        return ("%d edges given for %d vertices; an arborescence has exactly %d"
                % (len(chosen), inst["n"], inst["n"] - 1))
    selfloop = [e for e in chosen if e["u"] == e["v"]]
    if selfloop:
        return "edge %d is a self-loop" % selfloop[0]["id"]
    heads = [e["v"] for e in chosen]
    if inst["root"] in heads:
        return "an edge points at the root"
    if len(set(heads)) != len(heads):
        return "two edges point at the same vertex"
    parent = {e["v"]: e["u"] for e in chosen}
    for v in range(inst["n"]):
        if v == inst["root"]:
            continue
        seen, x = set(), v
        while x != inst["root"]:
            if x in seen or x not in parent:
                return "vertex %d is not reachable from the root" % v
            seen.add(x)
            x = parent[x]
    total = sum(e["w"] for e in chosen)
    if total != claimed:
        return "edge weights sum to %d, not the stated %d" % (total, claimed)
    return None


def test_output_schema():
    """Criterion 1: /app/answer.json is a JSON object whose 'answers' is an
    array with one well-formed entry per instance, in the order the instances
    appear in instances.json, using the documented fields, types and formats."""
    expected = _expected()
    rows = _parse(_read_result(), expected)
    misordered = [i for i, (g, e) in enumerate(zip(rows, expected))
                  if g["id"] != e["id"]]
    assert not misordered, (
        "%d entries are out of instance order (first at index %d)"
        % (len(misordered), misordered[0]))


def test_arborescences_are_optimal():
    """Criterion 2: every entry is right -- feasibility matches, the reported
    edges really do form a spanning arborescence of the reported weight, and
    that weight is the true optimum. Checked against held-out ground truth, so
    an arborescence that is valid but not cheapest fails."""
    expected = _expected()
    rows = _parse(_read_result(), expected)
    instances = _instances()

    wrong = []
    for got, exp in zip(rows, expected):
        inst = instances[exp["id"]]
        if got["feasible"] != exp["feasible"]:
            wrong.append("%s: reported feasible=%s, truth is %s"
                         % (exp["id"], got["feasible"], exp["feasible"]))
            continue
        if not exp["feasible"]:
            continue
        if got["total_weight"] != exp["total_weight"]:
            wrong.append("%s: reported total weight %d, optimum is %d"
                         % (exp["id"], got["total_weight"], exp["total_weight"]))
            continue
        fault = _arborescence_fault(inst, got["edges"], got["total_weight"])
        if fault:
            wrong.append("%s: %s" % (exp["id"], fault))

    assert not wrong, ("%d of %d instances are wrong; first: %s"
                       % (len(wrong), len(expected), wrong[0]))
