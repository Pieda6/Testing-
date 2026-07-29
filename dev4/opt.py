"""Exact optimiser for the objective in core.py, plus heuristic rivals."""
import sys
import time

import core as C


def _counts_key(n):
    return (-n[0], -n[1], -n[2])


def max_counts(w, reqs, order=None, deadline=None):
    """Best achievable (n1, n2, n3), lexicographically. Exhaustive with bound."""
    seq = order or sorted(reqs, key=lambda r: (r["priority"], r["id"]))
    m = len(seq)
    # suffix[i] = how many of each priority remain from i onward
    suffix = [(0, 0, 0)] * (m + 1)
    for i in range(m - 1, -1, -1):
        a, b, c = suffix[i + 1]
        p = seq[i]["priority"]
        suffix[i] = (a + (p == 1), b + (p == 2), c + (p == 3))

    best = [(0, 0, 0)]
    nodes = [0]

    def rec(i, st, n):
        nodes[0] += 1
        if deadline and nodes[0] % 4096 == 0 and time.time() > deadline:
            raise TimeoutError
        if i == m:
            if _counts_key(n) < _counts_key(best[0]):
                best[0] = n
            return
        a, b, c = suffix[i]
        bound = (n[0] + a, n[1] + b, n[2] + c)
        if _counts_key(bound) >= _counts_key(best[0]):
            return
        req = seq[i]
        p = req["priority"]
        for di, day, start in C.slots_for(w, st, req):
            nxt = st.clone()
            C.place(w, nxt, req, di, day, start)
            rec(i + 1, nxt, (n[0] + (p == 1), n[1] + (p == 2), n[2] + (p == 3)))
        rec(i + 1, st, n)

    rec(0, C.State(w), (0, 0, 0))
    return best[0], nodes[0]


def achievable(w, st, seq, i, n, target, suffix, deadline):
    """Can the tail from i still reach `target` counts, given counts n so far?"""
    if _counts_key(n) <= _counts_key(target):
        return True
    if i == len(seq):
        return False
    a, b, c = suffix[i]
    if _counts_key((n[0] + a, n[1] + b, n[2] + c)) > _counts_key(target):
        return False
    if deadline and time.time() > deadline:
        raise TimeoutError
    req = seq[i]
    p = req["priority"]
    for di, day, start in C.slots_for(w, st, req):
        nxt = st.clone()
        C.place(w, nxt, req, di, day, start)
        if achievable(w, nxt, seq, i + 1,
                      (n[0] + (p == 1), n[1] + (p == 2), n[2] + (p == 3)),
                      target, suffix, deadline):
            return True
    return achievable(w, st, seq, i + 1, n, target, suffix, deadline)


def solve_exact(w, deadline=None):
    """The unique optimum: best counts, then lexicographic by request id."""
    reqs = w.R
    target, nodes = max_counts(w, reqs, deadline=deadline)

    seq = sorted(reqs, key=lambda r: r["id"])
    m = len(seq)
    suffix = [(0, 0, 0)] * (m + 1)
    for i in range(m - 1, -1, -1):
        a, b, c = suffix[i + 1]
        p = seq[i]["priority"]
        suffix[i] = (a + (p == 1), b + (p == 2), c + (p == 3))

    st = C.State(w)
    n = (0, 0, 0)
    out = {}
    for i, req in enumerate(seq):
        p = req["priority"]
        chosen = None
        for di, day, start in C.slots_for(w, st, req):
            trial = st.clone()
            C.place(w, trial, req, di, day, start)
            n2 = (n[0] + (p == 1), n[1] + (p == 2), n[2] + (p == 3))
            if achievable(w, trial, seq, i + 1, n2, target, suffix, deadline):
                chosen = (di, day, start)
                break
        if chosen is None:
            out[req["id"]] = None
            continue
        di, day, start = chosen
        going = C.place(w, st, req, di, day, start)
        n = (n[0] + (p == 1), n[1] + (p == 2), n[2] + (p == 3))
        out[req["id"]] = (day, start, going)
    return target, out, nodes


def heuristic(w, order_key, lookahead=0, candidates=1):
    """Greedy / look-ahead rivals -- the implementations an agent reaches for."""
    seq = sorted(w.R, key=order_key)
    st = C.State(w)
    out = {}

    def fill(state, queue):
        k = 0
        for r in queue:
            s = C.slots_for(w, state, r)
            if not s:
                continue
            C.place(w, state, r, *s[0])
            k += 1
        return k

    for i, req in enumerate(seq):
        s = C.slots_for(w, st, req)
        if not s:
            out[req["id"]] = None
            continue
        if lookahead:
            best = None
            for cand in s[:candidates]:
                trial = st.clone()
                C.place(w, trial, req, *cand)
                kept = fill(trial, seq[i + 1:i + 1 + lookahead])
                if best is None or kept > best[0]:
                    best = (kept, cand)
            cand = best[1]
        else:
            cand = s[0]
        going = C.place(w, st, req, *cand)
        out[req["id"]] = (cand[1], cand[2], going)
    return out


def counts_of(w, out):
    n = [0, 0, 0]
    for r in w.R:
        if out.get(r["id"]):
            n[r["priority"] - 1] += 1
    return tuple(n)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    w = C.World(d)
    print("requests: %d" % len(w.R))
    t = time.time()
    target, out, nodes = solve_exact(w, deadline=time.time() + 900)
    print("exact optimum %s in %.1fs (%d nodes)" % (target, time.time() - t, nodes))
    for name, kw in [("greedy id order", dict(order_key=lambda r: r["id"])),
                     ("greedy priority", dict(order_key=lambda r: (r["priority"], r["id"]))),
                     ("look-ahead 6/8", dict(order_key=lambda r: (r["priority"], -len(r["required"]), r["id"]),
                                             lookahead=8, candidates=6))]:
        h = heuristic(w, **kw)
        same = sum(1 for r in w.R if h.get(r["id"]) == out.get(r["id"]))
        print("  %-18s counts %s  matches optimum on %d/%d rows"
              % (name, counts_of(w, h), same, len(w.R)))
