"""Verifier for dynamo/ecdsa-nonce-lattice.

Ground truth is the signer's PUBLIC key Q, embedded here as an immutable
constant. Q is public information; recovering d with d*G == Q is exactly the
task's discrete-log problem, so no correct-but-cheating answer can exist and no
private key is stored anywhere in the agent's image. The check is independent
of the agent-writable corpus at /app/data.
"""
import json
import os

# --- secp256k1 (self-contained; no dependency on agent-writable code) -------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

# Protected ground truth: the signer's public key Q (immutable input).
QX = 0xCA4F86738C9200C6545B1659A1F22125724CB1C7E47F4312585A4E144931DC3A
QY = 0x2CCC6753043927FDE8B8ADECA2DF06FE3D6038B572507B7670D5627F25A2D8DF

RESULT_PATH = "/app/result.json"


def _inv(x, m):
    return pow(x % m, -1, m)


def _padd(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x1, y1 = a
    x2, y2 = b
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if a == b:
        lam = (3 * x1 * x1) * _inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * _inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _mul(k, pt):
    k %= N
    r = None
    a = pt
    while k:
        if k & 1:
            r = _padd(r, a)
        a = _padd(a, a)
        k >>= 1
    return r


G = (GX, GY)
Q = (QX, QY)


def _read_result():
    """Read /app/result.json, refusing to follow a symlink at the final path
    component (O_NOFOLLOW anti-alias guard)."""
    fd = os.open(RESULT_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "r") as f:
            return json.load(f)
    except OSError:
        os.close(fd)
        raise


def _parse_private_key(obj):
    """Return d as int, or raise AssertionError if the shape is wrong.

    The value must be a hex *string* (JSON numbers, floats, NaN, and Infinity
    are all rejected)."""
    assert isinstance(obj, dict), "result.json must be a JSON object"
    assert "private_key" in obj, "result.json must contain key 'private_key'"
    val = obj["private_key"]
    assert isinstance(val, str), "'private_key' must be a hex string, not a number"
    assert not isinstance(val, bool)
    s = val.strip()
    s = s[2:] if s.lower().startswith("0x") else s
    assert s and all(c in "0123456789abcdefABCDEF" for c in s), \
        "'private_key' must be a valid hexadecimal string"
    d = int(s, 16)
    # Defensive: reject non-finite sentinels should the field ever be numeric.
    assert isinstance(d, int) and not isinstance(d, float)
    return d


def test_result_schema():
    """Criterion 1: /app/result.json exists, is a JSON object, and its
    'private_key' decodes to an integer d with 1 <= d < n."""
    obj = _read_result()
    d = _parse_private_key(obj)
    assert 1 <= d < N, "private key must satisfy 1 <= d < n"


def test_recovered_key_matches_public_key():
    """Criterion 2: the recovered d is the real private key, i.e. d*G == Q,
    verified by independent scalar multiplication on secp256k1."""
    obj = _read_result()
    d = _parse_private_key(obj)
    assert 1 <= d < N
    assert _mul(d, G) == Q, "d*G does not equal the signer's public key Q"
