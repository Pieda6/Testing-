"""Verifier for dynamo/headerless-pcm-normalize.

Ground truth is the recovered format and canonical digest of every archive file,
held in tests/expected.json. That file is overlaid only at verification time and
is never copied into the agent's image, so the answers are not reachable from
inside the task.

The digest is what makes this airtight. Labelling a file's format correctly is
not sufficient -- the agent has to have produced the canonically converted bytes,
and a single sample rounded the wrong way changes the digest completely.
"""
import json
import os
import re

RESULT_PATH = "/app/normalized.json"
EXPECTED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "expected.json")

BIT_DEPTHS = (8, 16, 24, 32)
ENDIANNESS = ("little", "big")
LAYOUTS = ("interleaved", "planar")
MAX_PREAMBLE = 64
HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
FIELDS = ("name", "bit_depth", "endianness", "signed", "layout",
          "preamble_bytes", "sha256")


def _read_result():
    """Read /app/normalized.json, refusing to follow a symlink at the final
    path component (O_NOFOLLOW anti-alias guard)."""
    fd = os.open(RESULT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "r") as f:
            return json.load(f)
    except OSError:
        os.close(fd)
        raise


def _expected():
    with open(EXPECTED_PATH) as f:
        return json.load(f)["files"]


def _parse(obj, expected):
    """Return the submitted entries, or raise AssertionError on bad shape.

    Types are checked strictly: bit_depth and preamble_bytes must be JSON
    integers (bool is rejected, since it is an int subclass in Python), signed
    must be a JSON boolean, and the digest must be 64 lowercase hex characters.
    """
    assert isinstance(obj, dict), "normalized.json must be a JSON object"
    assert "files" in obj, "normalized.json must contain key 'files'"
    files = obj["files"]
    assert isinstance(files, list), "'files' must be a JSON array"
    assert len(files) == len(expected), (
        "expected %d entries, got %d" % (len(expected), len(files)))

    out = []
    for i, e in enumerate(files):
        assert isinstance(e, dict), "entry %d must be a JSON object" % i
        assert set(e) == set(FIELDS), (
            "entry %d has fields %s, expected %s"
            % (i, sorted(e), sorted(FIELDS)))

        assert isinstance(e["name"], str), "entry %d: name must be a string" % i

        for key in ("bit_depth", "preamble_bytes"):
            v = e[key]
            assert isinstance(v, int) and not isinstance(v, bool), (
                "entry %d: %s must be a JSON integer" % (i, key))
        assert e["bit_depth"] in BIT_DEPTHS, (
            "entry %d: bit_depth must be one of %s" % (i, list(BIT_DEPTHS)))
        assert 0 <= e["preamble_bytes"] < MAX_PREAMBLE, (
            "entry %d: preamble_bytes must be in [0, %d)" % (i, MAX_PREAMBLE))

        assert isinstance(e["signed"], bool), (
            "entry %d: signed must be a JSON boolean" % i)
        assert e["endianness"] in ENDIANNESS, (
            "entry %d: endianness must be one of %s" % (i, list(ENDIANNESS)))
        assert e["layout"] in LAYOUTS, (
            "entry %d: layout must be one of %s" % (i, list(LAYOUTS)))

        assert isinstance(e["sha256"], str), (
            "entry %d: sha256 must be a string" % i)
        assert HEX64.match(e["sha256"]), (
            "entry %d: sha256 must be 64 lowercase hex characters" % i)
        out.append(e)
    return out


def test_output_schema():
    """Criterion 1: /app/normalized.json is a JSON object whose 'files' is an
    array with one well-formed entry per archive file, in manifest order, using
    the documented field names, types and permitted values."""
    expected = _expected()
    got = _parse(_read_result(), expected)
    misordered = [i for i, (g, e) in enumerate(zip(got, expected))
                  if g["name"] != e["name"]]
    assert not misordered, (
        "%d entries are out of manifest order (first at index %d)"
        % (len(misordered), misordered[0]))


def test_all_fields_match():
    """Criterion 2: every field of every entry matches how the file was actually
    written, including the SHA-256 of the canonical bytes -- checked against
    held-out ground truth, so a plausible-looking normalisation is not enough."""
    expected = _expected()
    got = _parse(_read_result(), expected)

    wrong = []
    for g, e in zip(got, expected):
        bad = [k for k in FIELDS if g[k] != e[k]]
        if bad:
            wrong.append((e["name"], bad))
    assert not wrong, (
        "%d of %d files are wrong (first: %s, fields %s)"
        % (len(wrong), len(expected), wrong[0][0], wrong[0][1]))
