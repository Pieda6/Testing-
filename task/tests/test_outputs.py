"""Verifier for dynamo/legacy-tag-forge.

Ground truth is the 60 correct challenge tags, held in tests/expected_tags.json.
That file is overlaid only at verification time and is never copied into the
agent's image, so the answers are not reachable from inside the task. The
challenge records share no input vector with any sample, so the tags cannot be
looked up -- they can only be produced by recovering the tag function.
"""
import json
import os

RESULT_PATH = "/app/tags.json"
EXPECTED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "expected_tags.json")
TAG_BITS = 32


def _read_result():
    """Read /app/tags.json, refusing to follow a symlink at the final path
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
        return [int(t, 16) for t in json.load(f)["tags"]]


def _parse_tags(obj, n_expected):
    """Return the submitted tags as ints, or raise AssertionError on bad shape.

    Each entry must be a hex *string*; JSON numbers, floats, NaN and Infinity
    are all rejected."""
    assert isinstance(obj, dict), "tags.json must be a JSON object"
    assert "tags" in obj, "tags.json must contain key 'tags'"
    tags = obj["tags"]
    assert isinstance(tags, list), "'tags' must be a JSON array"
    assert len(tags) == n_expected, (
        "expected %d tags, got %d" % (n_expected, len(tags)))
    out = []
    for i, v in enumerate(tags):
        assert isinstance(v, str), (
            "tag %d must be a hex string, not a number" % i)
        assert not isinstance(v, bool)
        s = v.strip()
        s = s[2:] if s.lower().startswith("0x") else s
        assert s and all(c in "0123456789abcdefABCDEF" for c in s), (
            "tag %d is not valid hexadecimal" % i)
        t = int(s, 16)
        assert isinstance(t, int) and not isinstance(t, float)
        assert 0 <= t < (1 << TAG_BITS), (
            "tag %d does not fit in %d bits" % (i, TAG_BITS))
        out.append(t)
    return out


def test_output_schema():
    """Criterion 1: /app/tags.json is a JSON object whose 'tags' is an array of
    one 32-bit hex string per challenge record, in order."""
    expected = _expected()
    obj = _read_result()
    _parse_tags(obj, len(expected))


def test_all_tags_match():
    """Criterion 2: every forged tag equals the tag the archive's own function
    would produce for that challenge record -- checked against held-out ground
    truth, so fitting the samples is not sufficient."""
    expected = _expected()
    got = _parse_tags(_read_result(), len(expected))
    wrong = [i for i, (g, e) in enumerate(zip(got, expected)) if g != e]
    assert not wrong, (
        "%d of %d tags are wrong (first wrong index %d)"
        % (len(wrong), len(expected), wrong[0]))
