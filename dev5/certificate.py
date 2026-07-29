"""Polynomial-time proof that the shipped answer key is optimal.

At the sizes shipped, no exponential oracle can re-derive the optimum, so the key
is proved instead of recomputed, using LP duality for the arborescence polytope.

    minimise    sum_e w_e x_e
    subject to  x(delta^-(S)) >= 1   for every non-empty S contained in V \\ {r}
                x >= 0

    dual: maximise sum_S y_S  subject to  sum_{S : e enters S} y_S <= w_e,  y >= 0

Any spanning arborescence A covers every such S at least once, so for any
dual-feasible y,  w(A) >= sum_S y_S. If some arborescence attains that bound it
is optimal. Chu-Liu/Edmonds produces exactly such a y as a by-product: the amount
subtracted at each reduction step is the dual value of the set being reduced, and
the sets form a laminar family.

Negative weights are handled by shifting every weight up by a constant. Every
spanning arborescence has exactly n-1 edges, so a uniform shift moves every
candidate by the same amount and cannot change which one is cheapest.

The checker does not trust the producer. If the solver were wrong, the y it
emitted would fail dual feasibility or leave a duality gap, and this would say so.
"""


def dual_certificate(n0, root0, edges0):
    """Run the reduce-and-contract form of Edmonds', recording the dual.

    Returns (laminar, shift) with laminar a list of (frozenset of original
    vertices, y value), or None when no arborescence exists.
    """
    usable = [(u, v, w, eid) for (u, v, w, eid) in edges0
              if u != v and v != root0]
    shift = 0
    if usable:
        lowest = min(w for (_u, _v, w, _e) in usable)
        shift = max(0, -lowest)
    cur = [(u, v, w + shift, eid) for (u, v, w, eid) in usable]

    node_set = [frozenset([v]) for v in range(n0)]
    n, root = n0, root0
    laminar = []

    while True:
        m = [None] * n
        for u, v, w, _eid in cur:
            if v == root:
                continue
            if m[v] is None or w < m[v]:
                m[v] = w
        for v in range(n):
            if v != root and m[v] is None:
                return None                     # a vertex cannot be entered

        for v in range(n):
            if v != root:
                laminar.append((node_set[v], m[v]))
        cur = [(u, v, w - (0 if v == root else m[v]), eid)
               for (u, v, w, eid) in cur]

        pick = {}
        for u, v, w, _eid in cur:
            if v != root and w == 0 and v not in pick:
                pick[v] = u

        cycle = None
        state = [0] * n
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
            return laminar, shift

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


def check(n, root, edges, arb_edge_ids, claimed_weight):
    """Verify that `arb_edge_ids` is an optimal arborescence of `claimed_weight`.

    Returns None on success, or a string saying what failed.
    """
    by_id = {eid: (u, v, w) for (u, v, w, eid) in edges}
    if any(i not in by_id for i in arb_edge_ids):
        return "answer references an edge id that does not exist"
    chosen = [by_id[i] for i in arb_edge_ids]

    # --- the primal object really is a spanning arborescence -----------------
    if len(chosen) != n - 1:
        return "%d edges for %d vertices" % (len(chosen), n)
    if any(u == v for u, v, _w in chosen):
        return "a self-loop was used"
    heads = [v for _u, v, _w in chosen]
    if root in heads:
        return "an edge points at the root"
    if len(set(heads)) != len(heads):
        return "two edges point at the same vertex"
    parent = {v: u for u, v, _w in chosen}
    for v in range(n):
        if v == root:
            continue
        seen, x = set(), v
        while x != root:
            if x in seen or x not in parent:
                return "vertex %d is not reachable from the root" % v
            seen.add(x)
            x = parent[x]
    if sum(w for _u, _v, w in chosen) != claimed_weight:
        return "edge weights do not sum to the claimed total"

    # --- the dual proves nothing cheaper exists ------------------------------
    got = dual_certificate(n, root, edges)
    if got is None:
        return "no arborescence exists, yet one was supplied"
    laminar, shift = got

    if any(y < 0 for _S, y in laminar):
        return "dual solution has a negative component"
    if any(root in S for S, _y in laminar):
        return "a dual set contains the root"

    # Dual feasibility: for every usable edge, the sets it enters may not charge
    # more than its (shifted) weight.
    load = {}
    for S, y in laminar:
        if y:
            load[S] = load.get(S, 0) + y
    for u, v, w, _eid in edges:
        if u == v or v == root:
            continue
        charged = sum(y for S, y in load.items() if v in S and u not in S)
        if charged > w + shift:
            return ("dual infeasible on edge %d->%d: charged %d against weight %d"
                    % (u, v, charged, w + shift))

    dual_value = sum(load.values())
    primal_value = claimed_weight + (n - 1) * shift
    if dual_value != primal_value:
        return ("duality gap: arborescence costs %d but the dual bound is %d"
                % (primal_value, dual_value))
    return None
