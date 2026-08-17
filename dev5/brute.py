"""Independent exhaustive oracle. Shares no structure with Edmonds'.

A spanning arborescence rooted at r assigns every other vertex exactly one
incoming edge such that following those edges backwards from any vertex reaches
r. So enumerate every assignment, discard the ones that close a cycle, and keep
the cheapest. This is exponential and only usable because the shipped instances
are deliberately small -- which is the point: it validates the fast solver
without borrowing any of its reasoning.

Also reports how many distinct optimal arborescences exist, which is what pins
the answer to a single edge set.
"""
from itertools import product


def brute(n, edges, root, cap=4_000_000):
    """Return (weight, sorted eids, n_optima) or None. Raises on cap overflow."""
    incoming = {v: [] for v in range(n) if v != root}
    for u, v, w, eid in edges:
        if v == root or u == v:
            continue
        incoming[v].append((u, v, w, eid))

    verts = sorted(incoming)
    if any(not incoming[v] for v in verts):
        return None

    total = 1
    for v in verts:
        total *= len(incoming[v])
        if total > cap:
            raise ValueError("search space %d exceeds cap" % total)

    best = None
    best_set = None
    count = 0
    for combo in product(*(incoming[v] for v in verts)):
        parent = {}
        for u, v, _w, _e in combo:
            parent[v] = u
        ok = True
        for v in verts:
            seen = set()
            x = v
            while x != root:
                if x in seen:
                    ok = False
                    break
                seen.add(x)
                x = parent[x]
            if not ok:
                break
        if not ok:
            continue
        w = sum(e[2] for e in combo)
        if best is None or w < best:
            best = w
            best_set = sorted(e[3] for e in combo)
            count = 1
        elif w == best:
            count += 1
    if best is None:
        return None
    return best, best_set, count


def search_space(n, edges, root):
    incoming = {v: 0 for v in range(n) if v != root}
    for u, v, _w, _e in edges:
        if v == root or u == v:
            continue
        incoming[v] += 1
    total = 1
    for v in incoming:
        if incoming[v] == 0:
            return 0
        total *= incoming[v]
    return total
