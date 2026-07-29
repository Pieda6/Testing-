"""Differential test of the reference solver against two independent oracles.

This is what establishes that the shipped answer key is right. The reference
solver is Chu-Liu/Edmonds; it is checked against

  * exhaustive enumeration (brute.py) on small graphs -- every arborescence is
    listed and the cheapest wins, with no algorithmic reasoning at all; and
  * a subset DP in C (dp.c) on larger graphs -- exact, and built on a completely
    different recurrence with no notion of a cycle or a contraction.

Graphs are drawn to include the awkward shapes on purpose: self-loops, edges
into the root, parallel edges, negative and zero weights, dense cheap cycles
that force contraction to recurse, and vertex groups cut off from the root.
"""
import hashlib
import importlib.util
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brute as B  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "solve", os.path.join(HERE, "..", "task5", "solution", "solve.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
DP = os.path.join(HERE, "dp")


def rnd(seed, counter, nbits=32):
    b = hashlib.sha256(seed + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def make(seed, idx, nlo, nhi):
    idx = str(idx)
    n = nlo + rnd(seed, "n%s" % idx) % (nhi - nlo + 1)
    root = rnd(seed, "r%s" % idx) % n
    flav = rnd(seed, "f%s" % idx) % 16
    lo = -18 if flav & 4 else 0
    edges = []

    def add(u, v, w):
        edges.append((u, v, w, len(edges)))

    if (flav & 8) and n >= 5:
        # A group reachable only from inside itself.
        k = 2 + rnd(seed, "k%s" % idx) % 3
        group = [v for v in range(n) if v != root][:k]
        rest = [v for v in range(n) if v != root and v not in group]
        for i, v in enumerate(group):
            add(group[(i + 1) % len(group)], v, lo + rnd(seed, "gw%s_%d" % (idx, i)) % 40)
        for i, v in enumerate(rest):
            add(root if i == 0 else rest[i - 1], v,
                lo + rnd(seed, "rw%s_%d" % (idx, i)) % 40)
    else:
        m = n + 1 + rnd(seed, "m%s" % idx) % (2 * n)
        for k in range(m):
            add(rnd(seed, "u%s_%d" % (idx, k)) % n,
                rnd(seed, "v%s_%d" % (idx, k)) % n,
                lo + rnd(seed, "w%s_%d" % (idx, k)) % 40)
        if flav & 16 or True:
            # A few very cheap edges make low-weight cycles, which is what makes
            # contraction recurse.
            for k in range(1 + rnd(seed, "cn%s" % idx) % 4):
                add(rnd(seed, "cu%s_%d" % (idx, k)) % n,
                    rnd(seed, "cv%s_%d" % (idx, k)) % n,
                    lo + rnd(seed, "cw%s_%d" % (idx, k)) % 5)
    if flav & 1:
        for k in range(1 + rnd(seed, "sn%s" % idx) % 3):
            v = rnd(seed, "sv%s_%d" % (idx, k)) % n
            add(v, v, lo - 5 + rnd(seed, "sw%s_%d" % (idx, k)) % 10)
    if flav & 2:
        u = rnd(seed, "iu%s" % idx) % n
        if u != root:
            add(u, root, lo - 9 + rnd(seed, "iw%s" % idx) % 6)
    return n, root, edges


def dp_weight(n, root, edges):
    payload = ["%d %d %d" % (n, root, len(edges))]
    payload += ["%d %d %d" % (u, v, w) for u, v, w, _ in edges]
    r = subprocess.run([DP], input="\n".join(payload) + "\n",
                       capture_output=True, text=True)
    out = r.stdout.strip()
    return None if out == "INFEASIBLE" else int(out)


def main():
    seed = b"difftest/v1"
    bad = 0

    n_small = 0
    for idx in range(2500):
        n, root, edges = make(seed, idx, 3, 8)
        if B.search_space(n, edges, root) > 200_000:
            continue
        got = S.arborescence(n, edges, root)
        exp = B.brute(n, edges, root)
        n_small += 1
        gw = None if got is None else got[0]
        ew = None if exp is None else exp[0]
        if gw != ew:
            bad += 1
            print("  MISMATCH vs brute force: n=%d root=%d %r" % (n, root, edges))
            print("    edmonds=%r brute=%r" % (gw, ew))
            if bad > 3:
                return 1
    print("vs exhaustive enumeration: %d graphs, %d mismatches" % (n_small, bad))

    bad2 = 0
    n_big = 0
    for idx in range(400):
        n, root, edges = make(seed, "big%d" % idx, 12, 20)
        got = S.arborescence(n, edges, root)
        gw = None if got is None else got[0]
        ew = dp_weight(n, root, edges)
        n_big += 1
        if gw != ew:
            bad2 += 1
            print("  MISMATCH vs subset DP: n=%d root=%d" % (n, root))
            print("    edmonds=%r dp=%r" % (gw, ew))
            print("    %r" % (edges,))
            if bad2 > 3:
                return 1
        if got is not None:
            # The returned edge set must actually be an arborescence of that weight.
            by_id = {e[3]: e for e in edges}
            chosen = [by_id[i] for i in got[1]]
            assert len(chosen) == n - 1, "wrong edge count"
            heads = [e[1] for e in chosen]
            assert len(set(heads)) == len(heads) and root not in heads
            assert all(e[0] != e[1] for e in chosen)
            parent = {e[1]: e[0] for e in chosen}
            for v in range(n):
                if v == root:
                    continue
                seen, x = set(), v
                while x != root:
                    assert x not in seen and x in parent, "not connected to root"
                    seen.add(x)
                    x = parent[x]
            assert sum(e[2] for e in chosen) == got[0], "weights do not sum"
    print("vs subset DP (C):          %d graphs, %d mismatches" % (n_big, bad2))
    print("witness structure checked on every feasible case")
    return 1 if (bad or bad2) else 0


if __name__ == "__main__":
    raise SystemExit(main())
