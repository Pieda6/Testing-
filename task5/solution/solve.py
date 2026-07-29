"""Reference solver: minimum-weight spanning arborescence, with proof.

For each instance this produces either

  * an arborescence together with a dual solution proving no arborescence is
    cheaper, or
  * a set of vertices with no edge entering it, proving no arborescence exists.

The primal comes from Chu-Liu/Edmonds. The dual comes out of the same algorithm
almost for free, which is the point of the task: the amount subtracted from a
vertex's incoming edges at each reduction step IS the dual value of the set that
vertex currently represents, and the sets built up by successive contractions
form a laminar family. Running the algorithm in its reduce-then-contract form
makes that correspondence explicit.

Why the dual proves optimality. Every spanning arborescence must contain at least
one edge entering every non-empty set of vertices that excludes the root -- else
that set is unreachable. So for any y >= 0 satisfying, for every edge e, the sum
of y over the sets that e enters is at most w(e), every arborescence A costs at
least the sum of all y. Exhibiting an arborescence whose weight equals that sum
therefore proves it optimal, with no search and nothing to trust.

The parts that separate a correct implementation from one that merely looks
correct, all of which the shipped battery exercises:

  * Contraction recurses. After collapsing a cycle the reduced graph can contain
    another cycle, and that one can contain another.
  * Reduced weights. An edge entering a cycle is re-weighted by subtracting the
    weight of the cycle edge already entering its head.
  * Expansion drops exactly one cycle edge -- the one entering the vertex that
    the surviving external edge points at -- and keeps the rest.
  * Self-loops and edges into the root can never be used and are discarded first.
    A self-loop is often the cheapest edge at its head.
  * Every vertex having an incoming edge does NOT mean an arborescence exists: a
    group of vertices can be mutually reachable yet cut off from the root. That
    is what the cut certificate reports.

Reads only /app/data. No answer key is consulted.
"""
import json
import sys

DATA = "/app/data/instances.json"
OUT = "/app/answer.json"


# ---------------------------------------------------------------- primal ----
def arborescence(n, edges, root, stats=None):
    """Minimum-weight spanning arborescence, as (weight, sorted edge ids).

    edges: list of (u, v, w, eid). Returns None when none exists.
    """
    best = [None] * n
    for e in edges:
        u, v, w, eid = e
        if v == root or u == v:
            continue
        cur = best[v]
        if cur is None or w < cur[2] or (w == cur[2] and eid < cur[3]):
            best[v] = e
    for v in range(n):
        if v != root and best[v] is None:
            return None

    state = [0] * n                     # 0 unseen, 1 on current walk, 2 settled
    cycle = None
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

    if cycle is None:
        return (sum(best[v][2] for v in range(n) if v != root),
                sorted(best[v][3] for v in range(n) if v != root))

    if stats is not None:
        stats["depth"] = stats.get("depth", 0) + 1

    on_cycle = set(cycle)
    cycle_weight = sum(best[v][2] for v in cycle)

    mapped, nxt = {}, 0
    for v in range(n):
        if v not in on_cycle:
            mapped[v] = nxt
            nxt += 1
    super_v = nxt
    nxt += 1
    for v in on_cycle:
        mapped[v] = super_v

    reduced = []
    for u, v, w, eid in edges:
        mu, mv = mapped[u], mapped[v]
        if mu == mv:
            continue
        if v in on_cycle:
            reduced.append((mu, mv, w - best[v][2], eid))
        else:
            reduced.append((mu, mv, w, eid))

    sub = arborescence(nxt, reduced, mapped[root], stats)
    if sub is None:
        return None
    sub_weight, sub_eids = sub

    by_id = {e[3]: e for e in edges}
    entered = None
    for eid in sub_eids:
        u, v, _w, _ = by_id[eid]
        if v in on_cycle and u not in on_cycle:
            entered = v
            break

    chosen = set(sub_eids)
    for v in cycle:
        if v != entered:
            chosen.add(best[v][3])
    return sub_weight + cycle_weight, sorted(chosen)


# ------------------------------------------------------------------ dual ----
def dual_solution(n0, root0, edges0):
    """The laminar dual produced by reduce-and-contract.

    Returns a list of (sorted vertex list, y) with y > 0, or None if no
    arborescence exists.
    """
    cur = [(u, v, w, eid) for (u, v, w, eid) in edges0
           if u != v and v != root0]
    node_set = [frozenset([v]) for v in range(n0)]
    n, root = n0, root0
    out = []

    while True:
        m = [None] * n
        for _u, v, w, _eid in cur:
            if v == root:
                continue
            if m[v] is None or w < m[v]:
                m[v] = w
        for v in range(n):
            if v != root and m[v] is None:
                return None

        for v in range(n):
            if v != root and m[v]:
                out.append((sorted(node_set[v]), m[v]))
        cur = [(u, v, w - (0 if v == root else m[v]), eid)
               for (u, v, w, eid) in cur]

        pick = {}
        for u, v, w, _eid in cur:
            if v != root and w == 0 and v not in pick:
                pick[v] = u

        cycle, state = None, [0] * n
        for s in range(n):
            if s == root or state[s]:
                continue
            walk, v = [], s
            while v != root and state[v] == 0:
                state[v] = 1
                walk.append(v)
                v = pick[v]
            if v != root and state[v] == 1:
                cycle, x = [], v
                while True:
                    cycle.append(x)
                    x = pick[x]
                    if x == v:
                        break
            for x in walk:
                state[x] = 2
            if cycle:
                break
        if cycle is None:
            return out

        on = set(cycle)
        mapped, nxt = {}, 0
        for v in range(n):
            if v not in on:
                mapped[v] = nxt
                nxt += 1
        sup = nxt
        nxt += 1
        for v in on:
            mapped[v] = sup

        merged = frozenset().union(*(node_set[v] for v in on))
        new_set = [None] * nxt
        for v in range(n):
            if v not in on:
                new_set[mapped[v]] = node_set[v]
        new_set[sup] = merged

        cur = [(mapped[u], mapped[v], w, eid) for (u, v, w, eid) in cur
               if mapped[u] != mapped[v]]
        node_set, root, n = new_set, mapped[root], nxt


# ------------------------------------------------------------------- cut ----
def unreachable_cut(n, edges, root):
    """Vertices not reachable from the root. No edge can enter this set."""
    adj = {}
    for u, v, _w, _eid in edges:
        if u == v or v == root:
            continue
        adj.setdefault(u, []).append(v)
    seen = {root}
    stack = [root]
    while stack:
        x = stack.pop()
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return sorted(v for v in range(n) if v not in seen)


# ------------------------------------------------------------------ main ----
def solve_instance(inst):
    edges = [(e["u"], e["v"], e["w"], e["id"]) for e in inst["edges"]]
    got = arborescence(inst["n"], edges, inst["root"])
    if got is None:
        return {"id": inst["id"], "feasible": False, "total_weight": 0,
                "edges": [], "dual": [],
                "cut": unreachable_cut(inst["n"], edges, inst["root"])}
    weight, eids = got
    dual = dual_solution(inst["n"], inst["root"], edges)
    return {"id": inst["id"], "feasible": True, "total_weight": weight,
            "edges": eids, "dual": [[s, y] for s, y in dual], "cut": []}


def main():
    with open(DATA) as f:
        instances = json.load(f)["instances"]
    answers = [solve_instance(i) for i in instances]
    with open(OUT, "w") as f:
        json.dump({"answers": answers}, f)
    n_ok = sum(1 for a in answers if a["feasible"])
    print("solved %d instances (%d optimal arborescences with duals, "
          "%d cut certificates) -> %s"
          % (len(answers), n_ok, len(answers) - n_ok, OUT))


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
