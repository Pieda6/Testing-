"""Reference solver: minimum-weight spanning arborescence, per instance.

Implements Chu-Liu/Edmonds. The parts that separate a correct implementation
from one that merely looks correct, all of which the shipped battery exercises:

  * Contraction recurses. After collapsing a cycle the reduced graph can contain
    another cycle, and that one can contain another. An implementation that
    contracts a single level returns a valid arborescence with the wrong weight.
  * Reduced weights. An edge entering a cycle is re-weighted by subtracting the
    weight of the cycle edge already entering its head. Getting the bookkeeping
    wrong changes which edge is picked several levels up.
  * Expansion drops exactly one cycle edge -- the one entering the vertex that
    the surviving external edge points at -- and keeps the rest.
  * Self-loops and edges into the root can never be used, so they are discarded
    before anything else. A self-loop is often the cheapest edge at its head.
  * Every vertex having an incoming edge does NOT mean an arborescence exists:
    a set of vertices can be mutually reachable yet cut off from the root.
    Infeasibility is detected by the recursion, not by an in-degree check.

Weights may be negative or zero; nothing here assumes otherwise.

Reads only /app/data. No answer key is consulted.
"""
import json
import sys

DATA = "/app/data/instances.json"
OUT = "/app/answer.json"


def arborescence(n, edges, root, stats=None):
    """Minimum-weight spanning arborescence of `edges` rooted at `root`.

    edges: list of (u, v, w, eid). Returns (total_weight, sorted eids) or None
    when no spanning arborescence exists.
    """
    # Cheapest incoming edge for every vertex other than the root. Self-loops
    # and edges into the root are not eligible and never enter this table.
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

    # Follow the chosen in-edges backwards; a vertex revisited on the current
    # walk closes a cycle. The root has no in-edge, so it is never on one.
    state = [0] * n                     # 0 unseen, 1 on current walk, 2 settled
    cycle = None
    for s in range(n):
        if state[s] or s == root:
            continue
        walk = []
        v = s
        while v != root and state[v] == 0:
            state[v] = 1
            walk.append(v)
            v = best[v][0]
        if v != root and state[v] == 1:
            cycle = []
            x = v
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
        total = sum(best[v][2] for v in range(n) if v != root)
        return total, sorted(best[v][3] for v in range(n) if v != root)

    if stats is not None:
        stats["depth"] = stats.get("depth", 0) + 1

    on_cycle = set(cycle)
    cycle_weight = sum(best[v][2] for v in cycle)

    # Collapse the cycle to one vertex, renumbering the survivors.
    mapped = {}
    nxt = 0
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
        if mu == mv:                    # inside the cycle, or a self-loop
            continue
        if v in on_cycle:
            # Entering the cycle: pay only the improvement over the cycle edge
            # already arriving at v.
            reduced.append((mu, mv, w - best[v][2], eid))
        else:
            reduced.append((mu, mv, w, eid))

    sub = arborescence(nxt, reduced, mapped[root], stats)
    if sub is None:
        return None
    sub_weight, sub_eids = sub

    # Exactly one edge of the sub-solution enters the contracted vertex; the
    # cycle edge arriving at its head is the one that gets dropped.
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

    # The entering edge was counted at its reduced weight, and the cycle edge it
    # displaces is exactly the discount that was applied, so the two corrections
    # cancel and the real total is the sub-total plus the whole cycle.
    return sub_weight + cycle_weight, sorted(chosen)


def solve_instance(inst):
    edges = [(e["u"], e["v"], e["w"], e["id"]) for e in inst["edges"]]
    got = arborescence(inst["n"], edges, inst["root"])
    if got is None:
        return {"id": inst["id"], "feasible": False,
                "total_weight": 0, "edges": []}
    weight, eids = got
    return {"id": inst["id"], "feasible": True,
            "total_weight": weight, "edges": eids}


def main():
    with open(DATA) as f:
        instances = json.load(f)["instances"]
    answers = [solve_instance(i) for i in instances]
    with open(OUT, "w") as f:
        json.dump({"answers": answers}, f)
    n_ok = sum(1 for a in answers if a["feasible"])
    print("solved %d instances (%d feasible, %d with no arborescence) -> %s"
          % (len(answers), n_ok, len(answers) - n_ok, OUT))


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
