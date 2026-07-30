"""Verifier for dynamo/arborescence-battery.

Every answer must carry its own proof, and the proof is what is checked.

For an instance that has a spanning arborescence, the submission gives the edge
set and a dual solution. The edge set is re-examined against the graph -- exactly
n-1 edges, no self-loop, nothing entering the root, no two edges sharing a head,
every vertex reachable from the root, weights summing to the reported total. The
dual is then checked for non-negativity and for the covering constraint on every
edge, and its value must equal the weight of the arborescence. Because every
spanning arborescence contains an edge entering every non-empty vertex set that
excludes the root, any dual-feasible y lower-bounds every arborescence; matching
that bound is therefore a proof of optimality, not evidence of it.

For an instance with no spanning arborescence, the submission gives a non-empty
set of non-root vertices with no edge entering it. No arborescence can reach
those vertices, so that is a proof of infeasibility.

Every entry also reports the optimal weight from each of the n possible roots,
which is checked against held-out ground truth. Most roots leave the graph with
no arborescence at all, so this is where per-root feasibility has to be decided
rather than assumed.

Several optimal arborescences may exist, and several dual solutions may certify
them; any correct pair is accepted. The held-out optimum in tests/expected.json
is checked as well, so a submission must be both provably optimal and equal to
the known answer. instances.json is a trusted copy of the graphs: /app/data is
writable by the agent, so the verifier must not read the graphs from there.
"""
import json
import os
import re

RESULT_PATH = "/app/answer.json"
HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED_PATH = os.path.join(HERE, "expected.json")
INSTANCES_PATH = os.path.join(HERE, "instances.json")

FIELDS = ("id", "feasible", "total_weight", "edges", "dual", "cut",
          "root_weights")
ID_RE = re.compile(r"\AG-\d{3}\Z")
MAX_DUAL_ENTRIES = 5000


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


def _sorted_unique_ints(x):
    return (isinstance(x, list) and all(_is_int(i) for i in x)
            and len(set(x)) == len(x) and x == sorted(x))


def _parse(obj, expected):
    """Return the submitted answers, or raise AssertionError on bad shape."""
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
        assert _sorted_unique_ints(r["edges"]) and all(x >= 0 for x in r["edges"]), (
            "entry %d: edges must be a sorted list of unique non-negative "
            "integers" % i)
        assert _sorted_unique_ints(r["cut"]) and all(x >= 0 for x in r["cut"]), (
            "entry %d: cut must be a sorted list of unique non-negative "
            "integers" % i)

        dual = r["dual"]
        assert isinstance(dual, list), "entry %d: dual must be an array" % i
        assert len(dual) <= MAX_DUAL_ENTRIES, (
            "entry %d: dual has %d entries, at most %d are accepted"
            % (i, len(dual), MAX_DUAL_ENTRIES))
        for j, item in enumerate(dual):
            assert (isinstance(item, list) and len(item) == 2), (
                "entry %d: dual item %d must be a [vertices, value] pair"
                % (i, j))
            verts, y = item
            assert _sorted_unique_ints(verts) and verts, (
                "entry %d: dual item %d needs a non-empty sorted list of "
                "unique vertices" % (i, j))
            assert _is_int(y), (
                "entry %d: dual item %d value must be an integer" % (i, j))

        rw = r["root_weights"]
        assert isinstance(rw, list), (
            "entry %d: root_weights must be an array" % i)
        assert all(x is None or _is_int(x) for x in rw), (
            "entry %d: each root_weights entry must be an integer or null" % i)

        if r["feasible"]:
            assert r["cut"] == [], (
                "entry %d: a feasible instance must not carry a cut" % i)
        else:
            assert r["total_weight"] == 0 and r["edges"] == [] and dual == [], (
                "entry %d: an instance with no arborescence must report "
                "total_weight 0, no edges and no dual" % i)
    return rows


def _primal_fault(inst, edge_ids, claimed):
    """None if `edge_ids` is a spanning arborescence of weight `claimed`."""
    by_id = {e["id"]: e for e in inst["edges"]}
    missing = [i for i in edge_ids if i not in by_id]
    if missing:
        return "edge id %d is not in this instance" % missing[0]
    chosen = [by_id[i] for i in edge_ids]
    if len(chosen) != inst["n"] - 1:
        return ("%d edges given for %d vertices; an arborescence has exactly %d"
                % (len(chosen), inst["n"], inst["n"] - 1))
    loops = [e for e in chosen if e["u"] == e["v"]]
    if loops:
        return "edge %d is a self-loop" % loops[0]["id"]
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


def _dual_fault(inst, dual, claimed):
    """None if `dual` proves no arborescence is cheaper than `claimed`."""
    n, root = inst["n"], inst["root"]
    sets = []
    for verts, y in dual:
        if y < 0:
            return "a dual value is negative"
        if any(v < 0 or v >= n for v in verts):
            return "a dual set names a vertex outside the graph"
        if root in verts:
            return "a dual set contains the root"
        if y:
            sets.append((frozenset(verts), y))

    for e in inst["edges"]:
        u, v, w = e["u"], e["v"], e["w"]
        if u == v or v == root:
            continue                    # never usable, so never constrained
        charged = sum(y for S, y in sets if v in S and u not in S)
        if charged > w:
            return ("dual charges %d to edge %d (%d->%d) of weight %d, which it "
                    "may not exceed" % (charged, e["id"], u, v, w))

    value = sum(y for _S, y in sets)
    if value != claimed:
        return ("dual value is %d but the arborescence costs %d; the proof is "
                "only complete when they are equal" % (value, claimed))
    return None


def _cut_fault(inst, cut):
    """None if `cut` proves no spanning arborescence exists.

"""
    n, root = inst["n"], inst["root"]
    if not cut:
        return "an instance with no arborescence needs a non-empty cut"
    if any(v < 0 or v >= n for v in cut):
        return "the cut names a vertex outside the graph"
    if root in cut:
        return "the cut contains the root"
    inside = set(cut)
    for e in inst["edges"]:
        if e["v"] in inside and e["u"] not in inside:
            return ("edge %d (%d->%d) enters the cut, so it does not prove "
                    "anything" % (e["id"], e["u"], e["v"]))
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


def test_answers_are_proved():
    """Criterion 2: every entry is right and carries a valid proof -- a spanning
    arborescence of the stated optimal weight together with a dual solution
    certifying that nothing is cheaper, or a set of vertices with no edge
    entering it certifying that no arborescence exists."""
    expected = _expected()
    rows = _parse(_read_result(), expected)
    instances = _instances()

    wrong = []
    for got, exp in zip(rows, expected):
        inst = instances[exp["id"]]
        if len(got["root_weights"]) != inst["n"]:
            wrong.append("%s: root_weights has %d entries, expected one per "
                         "vertex (%d)"
                         % (exp["id"], len(got["root_weights"]), inst["n"]))
            continue
        if got["root_weights"] != exp["root_weights"]:
            bad = [r for r in range(inst["n"])
                   if got["root_weights"][r] != exp["root_weights"][r]]
            wrong.append("%s: root_weights wrong for %d of %d roots (first: "
                         "root %d, reported %r, truth %r)"
                         % (exp["id"], len(bad), inst["n"], bad[0],
                            got["root_weights"][bad[0]],
                            exp["root_weights"][bad[0]]))
            continue
        if got["feasible"] != exp["feasible"]:
            wrong.append("%s: reported feasible=%s, truth is %s"
                         % (exp["id"], got["feasible"], exp["feasible"]))
            continue
        if not exp["feasible"]:
            fault = _cut_fault(inst, got["cut"])
            if fault:
                wrong.append("%s: %s" % (exp["id"], fault))
            continue
        if got["total_weight"] != exp["total_weight"]:
            wrong.append("%s: reported total weight %d, optimum is %d"
                         % (exp["id"], got["total_weight"], exp["total_weight"]))
            continue
        fault = (_primal_fault(inst, got["edges"], got["total_weight"])
                 or _dual_fault(inst, got["dual"], got["total_weight"]))
        if fault:
            wrong.append("%s: %s" % (exp["id"], fault))

    assert not wrong, ("%d of %d instances are wrong; first: %s"
                       % (len(wrong), len(expected), wrong[0]))
