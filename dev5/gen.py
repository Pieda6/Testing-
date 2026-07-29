"""Deterministic instance generator for dynamo/arborescence-battery.

Fixed seed => byte-identical output on every run and platform. All randomness
comes from SHA-256 of a fixed seed plus a counter; no PRNG library is involved.

Sizing is deliberate. Vertices run from 30 to 38, which puts both brute-force
routes out of reach on every single instance. Enumerating one incoming edge per
vertex runs to 10^14 combinations at the smallest and 10^24 at the largest. The
exact subset DP needs one value per subset of vertices, so even the smallest
instance here wants 2^30 four-byte entries -- 4.3 GB against the container's
2 GB -- and the largest wants a terabyte. Neither shortcut is available at any
size in the battery. The intended algorithm runs in milliseconds.

The battery is not a random sample. Candidates are generated, classified by
which part of the algorithm they exercise, then selected to fill coverage quotas:

  acyclic            the cheapest in-edges already form an arborescence
  depth1/2/3         contraction recurses one / two / three or more levels
  infeasible_missing some vertex has no incoming edge at all
  infeasible_cut     every vertex has an incoming edge, yet a group of vertices
                     is mutually reachable and cut off from the root -- the case
                     an in-degree check calls feasible
  selfloop_min       some vertex's cheapest incoming edge is a self-loop
  into_root          an edge into the root is cheaper than every edge used
  zero               the optimum uses a zero-weight edge

Emits instances.json only. The generator never computes the shipped answer key;
that comes from the reference solver and is then re-derived by the independent
subset DP in dp.c before it is allowed to ship.
"""
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_spec = importlib.util.spec_from_file_location(
    "solve", os.path.join(HERE, "..", "task5", "solution", "solve.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

SEED = b"dynamo/arborescence-battery/v5"
N_INSTANCES = 50
POOL = 1500
N_LO, N_HI = 30, 38

QUOTAS = [
    ("depth3", 9),
    ("infeasible_cut", 6),
    ("depth2", 10),
    ("infeasible_missing", 4),
    ("depth1", 11),
    ("acyclic", 4),
    ("selfloop_min", 2),
    ("into_root", 2),
]


def det_int(counter, nbits=32):
    b = hashlib.sha256(SEED + counter.encode()).digest()
    return int.from_bytes(b[:8], "big") & ((1 << nbits) - 1)


def build_candidate(idx):
    n = N_LO + det_int("n%d" % idx) % (N_HI - N_LO + 1)
    root = det_int("r%d" % idx) % n
    flav = det_int("f%d" % idx) % 16
    self_loops = bool(flav & 1)
    into_root = bool(flav & 2)
    wide = bool(flav & 4)          # wider weight spread
    cut = bool(flav & 8)
    missing = (det_int("ms%d" % idx) % 7) == 0

    # Non-negative throughout: the LP dual the answer must carry requires
    # non-negative costs, so shipping negative weights would make the
    # certificate ill-posed rather than merely harder.
    lo = 0
    hi = 90 if wide else 60
    edges = []

    def add(u, v, w):
        edges.append({"id": len(edges), "u": u, "v": v, "w": w})

    others = [v for v in range(n) if v != root]

    # A spanning skeleton so that most vertices are genuinely reachable.
    for i, v in enumerate(others):
        u = root if i == 0 else others[det_int("sk%d_%d" % (idx, i)) % i]
        add(u, v, lo + det_int("sw%d_%d" % (idx, i)) % (hi - lo))

    m = 2 * n + det_int("m%d" % idx) % (2 * n)
    for k in range(m):
        u = det_int("u%d_%d" % (idx, k)) % n
        v = det_int("v%d_%d" % (idx, k)) % n
        add(u, v, lo + det_int("w%d_%d" % (idx, k)) % (hi - lo))

    # Cheap edges arranged in short cycles. These are what make the cheapest
    # in-edge choices close a loop, and make contraction recurse.
    for c in range(2 + det_int("nc%d" % idx) % 4):
        size = 2 + det_int("cs%d_%d" % (idx, c)) % 4
        ring = []
        for j in range(size):
            ring.append(others[det_int("cv%d_%d_%d" % (idx, c, j)) % len(others)])
        for j in range(size):
            a, b = ring[j], ring[(j + 1) % size]
            if a != b:
                add(a, b, lo + det_int("cw%d_%d_%d" % (idx, c, j)) % 6)

    if cut:
        # A group whose only incoming edges come from inside the group.
        k = 3 + det_int("gk%d" % idx) % 4
        group = others[:k]
        gset = set(group)
        edges = [e for e in edges if not (e["v"] in gset and e["u"] not in gset)]
        for i, e in enumerate(edges):
            e["id"] = i
        for j, v in enumerate(group):
            add(group[(j + 1) % len(group)], v,
                lo + det_int("gw%d_%d" % (idx, j)) % (hi - lo))

    if missing and not cut:
        victim = others[det_int("mv%d" % idx) % len(others)]
        edges = [e for e in edges if e["v"] != victim]
        for i, e in enumerate(edges):
            e["id"] = i

    if self_loops:
        for k in range(1 + det_int("sn%d" % idx) % 3):
            v = det_int("sv%d_%d" % (idx, k)) % n
            add(v, v, det_int("slw%d_%d" % (idx, k)) % 5)
    if into_root:
        u = det_int("iu%d" % idx) % n
        if u != root:
            add(u, root, det_int("iw%d" % idx) % 4)

    return {"n": n, "root": root, "edges": edges}


def classify(cand, res, depth):
    tags = set()
    n, root = cand["n"], cand["root"]

    if res is None:
        eligible = {v: 0 for v in range(n) if v != root}
        for e in cand["edges"]:
            if e["v"] != root and e["u"] != e["v"]:
                eligible[e["v"]] += 1
        tags.add("infeasible_missing" if any(c == 0 for c in eligible.values())
                 else "infeasible_cut")
        return tags

    tags.add({0: "acyclic", 1: "depth1", 2: "depth2"}.get(depth, "depth3"))
    by_id = {e["id"]: e for e in cand["edges"]}
    weights = [by_id[i]["w"] for i in res[1]]
    if any(w == 0 for w in weights):
        tags.add("zero")
    for e in cand["edges"]:
        if e["u"] == e["v"]:
            rivals = [x["w"] for x in cand["edges"]
                      if x["v"] == e["v"] and x["u"] != x["v"]]
            if rivals and e["w"] < min(rivals):
                tags.add("selfloop_min")
    into = [e["w"] for e in cand["edges"] if e["v"] == root]
    if into and weights and min(into) < min(weights):
        tags.add("into_root")
    return tags


def main():
    pool = []
    for idx in range(POOL):
        cand = build_candidate(idx)
        tup = [(e["u"], e["v"], e["w"], e["id"]) for e in cand["edges"]]
        stats = {}
        res = S.arborescence(cand["n"], tup, cand["root"], stats)
        pool.append((cand, classify(cand, res, stats.get("depth", 0))))

    chosen, taken = [], set()
    for tag, want in QUOTAS:
        got = 0
        for i, (_c, tags) in enumerate(pool):
            if got >= want:
                break
            if i in taken or tag not in tags:
                continue
            taken.add(i)
            chosen.append(i)
            got += 1
        if got < want:
            print("  WARNING: only %d/%d for %s" % (got, want, tag))
    for i in range(len(pool)):
        if len(chosen) >= N_INSTANCES:
            break
        if i not in taken:
            taken.add(i)
            chosen.append(i)

    chosen.sort()
    instances, coverage = [], {}
    for k, i in enumerate(chosen[:N_INSTANCES]):
        cand, tags = pool[i]
        instances.append({"id": "G-%03d" % (k + 1), "n": cand["n"],
                          "root": cand["root"], "edges": cand["edges"]})
        for t in tags:
            coverage[t] = coverage.get(t, 0) + 1

    with open(os.path.join(HERE, "instances.json"), "w") as f:
        json.dump({"instances": instances}, f, indent=1)
        f.write("\n")

    print("instances: %d" % len(instances))
    for t in sorted(coverage):
        print("  %-20s %d" % (t, coverage[t]))
    print("vertices %d..%d | edges %d..%d | total edges %d"
          % (min(i["n"] for i in instances), max(i["n"] for i in instances),
             min(len(i["edges"]) for i in instances),
             max(len(i["edges"]) for i in instances),
             sum(len(i["edges"]) for i in instances)))


if __name__ == "__main__":
    main()
