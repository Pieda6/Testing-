"""How many instances each plausible-but-wrong implementation still gets right.

Measures the primal only (feasibility and optimal weight), which is what the
difficulty figures in task.toml quote. Every one of these also fails the proof,
so their reward is 0 regardless; this isolates how wrong the answer itself is.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def arb(n, edges, root, drop_selfloops=True, drop_into_root=True,
        reweight=True, max_depth=None, expand_correct=True, depth=0):
    best = [None] * n
    for e in edges:
        u, v, w, eid = e
        if drop_into_root and v == root:
            continue
        if drop_selfloops and u == v:
            continue
        cur = best[v]
        if cur is None or w < cur[2] or (w == cur[2] and eid < cur[3]):
            best[v] = e
    for v in range(n):
        if v != root and best[v] is None:
            return None

    state, cycle = [0] * n, None
    for s in range(n):
        if state[s] or s == root:
            continue
        walk, v = [], s
        while v != root and state[v] == 0:
            state[v] = 1
            walk.append(v)
            v = best[v][0]
        if v != root and state[v] == 1:
            cycle, x = [], v
            while True:
                cycle.append(x)
                x = best[x][0]
                if x == v:
                    break
        for x in walk:
            state[x] = 2
        if cycle:
            break

    def greedy():
        return (sum(best[v][2] for v in range(n) if v != root),
                sorted(best[v][3] for v in range(n) if v != root))

    if cycle is None:
        return greedy()
    if max_depth is not None and depth >= max_depth:
        return greedy()

    on, cw = set(cycle), sum(best[v][2] for v in cycle)
    mapped, nxt = {}, 0
    for v in range(n):
        if v not in on:
            mapped[v] = nxt
            nxt += 1
    sup = nxt
    nxt += 1
    for v in on:
        mapped[v] = sup

    reduced = []
    for u, v, w, eid in edges:
        mu, mv = mapped[u], mapped[v]
        if mu == mv:
            continue
        reduced.append((mu, mv, w - best[v][2] if (v in on and reweight) else w,
                        eid))

    sub = arb(nxt, reduced, mapped[root], drop_selfloops, drop_into_root,
              reweight, max_depth, expand_correct, depth + 1)
    if sub is None:
        return None
    sw, seids = sub
    by_id = {e[3]: e for e in edges}
    entered = None
    for eid in seids:
        u, v, _w, _ = by_id[eid]
        if v in on and u not in on:
            entered = v
            break
    if not expand_correct:
        entered = cycle[0]
    chosen = set(seids)
    for v in cycle:
        if v != entered:
            chosen.add(best[v][3])
    return sw + cw, sorted(chosen)


def greedy_min_in(n, root, tup, selfloops=False, into_root=False):
    best = {}
    for u, v, w, eid in tup:
        if not into_root and v == root:
            continue
        if not selfloops and u == v:
            continue
        if v not in best or w < best[v][2]:
            best[v] = (u, v, w, eid)
    if any(v not in best for v in range(n) if v != root):
        return None
    return (sum(e[2] for e in best.values()),
            sorted(e[3] for e in best.values()))


def indegree_feasible(n, root, tup):
    got = arb(n, tup, root)
    if got is not None:
        return got
    have = {v for u, v, _w, _e in tup if v != root and u != v}
    if all(v in have for v in range(n) if v != root):
        return greedy_min_in(n, root, tup)
    return None


def undirected_mst(n, root, tup):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    chosen, total = [], 0
    for u, v, w, eid in sorted(tup, key=lambda e: (e[2], e[3])):
        if u == v:
            continue
        a, b = find(u), find(v)
        if a == b:
            continue
        parent[a] = b
        chosen.append(eid)
        total += w
    return (total, sorted(chosen)) if len(chosen) == n - 1 else None


VARIANTS = [
    ("undirected MST instead", lambda n, r, t: undirected_mst(n, r, t)),
    ("cheapest in-edge, self-loops not excluded",
     lambda n, r, t: greedy_min_in(n, r, t, selfloops=True)),
    ("cheapest in-edge, root given an in-edge",
     lambda n, r, t: greedy_min_in(n, r, t, into_root=True)),
    ("cheapest in-edge, no contraction", lambda n, r, t: greedy_min_in(n, r, t)),
    ("no reduced weights on contraction",
     lambda n, r, t: arb(n, t, r, reweight=False)),
    ("contracts only one level", lambda n, r, t: arb(n, t, r, max_depth=1)),
    ("expansion drops the wrong cycle edge",
     lambda n, r, t: arb(n, t, r, expand_correct=False)),
    ("contracts only two levels", lambda n, r, t: arb(n, t, r, max_depth=2)),
    ("feasible whenever every vertex has an in-edge",
     lambda n, r, t: indegree_feasible(n, r, t)),
]


def main():
    inst = json.load(open(os.path.join(HERE, "instances.json")))["instances"]
    key = {a["id"]: a for a in
           json.load(open(os.path.join(HERE, "expected.json")))["answers"]}
    sys.path.insert(0, os.path.join(HERE, "..", "task5", "tests"))
    import test_outputs as T

    print("%-46s %s" % ("WRONG IMPLEMENTATION", "instances correct"))
    for name, fn in VARIANTS:
        right = 0
        for i in inst:
            t = [(e["u"], e["v"], e["w"], e["id"]) for e in i["edges"]]
            got = fn(i["n"], i["root"], t)
            k = key[i["id"]]
            if got is None:
                right += not k["feasible"]
                continue
            # Right means: the instance really is feasible, the weight is the
            # optimum, and the edge set really is an arborescence of that weight.
            if not k["feasible"] or got[0] != k["total_weight"]:
                continue
            if T._primal_fault(i, got[1], got[0]) is None:
                right += 1
        print("%-46s %d/%d" % (name, right, len(inst)))


if __name__ == "__main__":
    main()
