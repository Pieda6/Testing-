"""Control battery for dynamo/arborescence-battery.

Runs the REAL verifier (task5/tests/test_outputs.py under pytest) against the
oracle and against a set of implementations that are wrong in the specific ways
a competent-but-hasty implementation of Edmonds' goes wrong. Every number quoted
in task.toml comes from here.

The oracle is checked first. If it does not score 1.0 the harness is broken and
nothing else it prints means anything.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "..", "task5", "tests")
OUT = "/app/answer.json"


# --------------------------------------------------------------------------
# A parameterised solver. Each flag turns a correct step into a plausible bug.
# --------------------------------------------------------------------------
def arb(n, edges, root, drop_selfloops=True, drop_into_root=True,
        reweight=True, max_depth=None, expand_correct=True, depth=0):
    best = [None] * n
    for e in edges:
        u, v, w, eid = e
        if drop_into_root and v == root:
            continue
        if drop_selfloops and u == v:
            continue
        if v == root and not drop_into_root and u == root:
            continue
        cur = best[v]
        if cur is None or w < cur[2] or (w == cur[2] and eid < cur[3]):
            best[v] = e
    for v in range(n):
        if v != root and best[v] is None:
            return None

    state = [0] * n
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

    def greedy():
        return (sum(best[v][2] for v in range(n) if v != root),
                sorted(best[v][3] for v in range(n) if v != root))

    if cycle is None:
        return greedy()
    if max_depth is not None and depth >= max_depth:
        return greedy()                       # stops contracting too early

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
        if v in on_cycle and reweight:
            reduced.append((mu, mv, w - best[v][2], eid))
        else:
            reduced.append((mu, mv, w, eid))

    sub = arb(nxt, reduced, mapped[root], drop_selfloops, drop_into_root,
              reweight, max_depth, expand_correct, depth + 1)
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
    if not expand_correct:
        entered = cycle[0]                    # drops the wrong cycle edge

    chosen = set(sub_eids)
    for v in cycle:
        if v != entered:
            chosen.add(best[v][3])
    return sub_weight + cycle_weight, sorted(chosen)


def run_solver(instances, fn):
    out = []
    for inst in instances:
        tup = [(e["u"], e["v"], e["w"], e["id"]) for e in inst["edges"]]
        got = fn(inst, tup)
        if got is None:
            out.append({"id": inst["id"], "feasible": False,
                        "total_weight": 0, "edges": []})
        else:
            out.append({"id": inst["id"], "feasible": True,
                        "total_weight": got[0], "edges": got[1]})
    return out


def variant(**kw):
    return lambda inst, tup: arb(inst["n"], tup, inst["root"], **kw)


def greedy_min_in(inst, tup):
    """The naive 'directed MST': cheapest incoming edge per vertex, no more."""
    n, root = inst["n"], inst["root"]
    best = {}
    for u, v, w, eid in tup:
        if v == root or u == v:
            continue
        if v not in best or w < best[v][2]:
            best[v] = (u, v, w, eid)
    if any(v not in best for v in range(n) if v != root):
        return None
    return (sum(e[2] for e in best.values()),
            sorted(e[3] for e in best.values()))


def greedy_selfloops(inst, tup):
    """Naive greedy that forgets a self-loop can never be an in-edge."""
    n, root = inst["n"], inst["root"]
    best = {}
    for u, v, w, eid in tup:
        if v == root:
            continue
        if v not in best or w < best[v][2]:
            best[v] = (u, v, w, eid)
    if any(v not in best for v in range(n) if v != root):
        return None
    return (sum(e[2] for e in best.values()),
            sorted(e[3] for e in best.values()))


def greedy_into_root(inst, tup):
    """Naive greedy that also gives the root an incoming edge."""
    n, root = inst["n"], inst["root"]
    best = {}
    for u, v, w, eid in tup:
        if u == v:
            continue
        if v not in best or w < best[v][2]:
            best[v] = (u, v, w, eid)
    if any(v not in best for v in range(n) if v != root):
        return None
    return (sum(e[2] for e in best.values()),
            sorted(e[3] for e in best.values()))


def indegree_feasible(inst, tup):
    """Reports feasible whenever every vertex has an incoming edge."""
    got = arb(inst["n"], tup, inst["root"])
    if got is not None:
        return got
    n, root = inst["n"], inst["root"]
    have = {v for u, v, _w, _e in tup if v != root and u != v}
    if all(v in have for v in range(n) if v != root):
        return greedy_min_in(inst, tup)
    return None


def nonneg_only(inst, tup):
    """Assumes weights are non-negative and discards the rest."""
    return arb(inst["n"], [e for e in tup if e[2] >= 0], inst["root"])


def undirected_mst(inst, tup):
    """Ignores direction and returns a minimum spanning tree."""
    n, root = inst["n"], inst["root"]
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
    if len(chosen) != n - 1:
        return None
    return total, sorted(chosen)


WRONG = [
    ("naive cheapest in-edge, no contraction", greedy_min_in),
    ("contracts only one level", variant(max_depth=1)),
    ("contracts only two levels", variant(max_depth=2)),
    ("no reduced weights on contraction", variant(reweight=False)),
    ("expansion drops the wrong cycle edge", variant(expand_correct=False)),
    ("naive greedy, self-loops not excluded", greedy_selfloops),
    ("naive greedy, root given an in-edge", greedy_into_root),
    ("feasible whenever every vertex has an in-edge", indegree_feasible),
    ("assumes non-negative weights", nonneg_only),
    ("undirected MST instead", undirected_mst),
]


# --------------------------------------------------------------------------
def reward(rows, symlink=False, missing=False):
    os.makedirs("/app", exist_ok=True)
    for p in (OUT, OUT + ".real"):
        if os.path.islink(p) or os.path.exists(p):
            os.remove(p)
    if not missing:
        if symlink:
            with open(OUT + ".real", "w") as f:
                json.dump({"answers": rows}, f)
            os.symlink(OUT + ".real", OUT)
        else:
            with open(OUT, "w") as f:
                json.dump({"answers": rows}, f)
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         os.path.join(TESTS, "test_outputs.py"),
         "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True)
    return 1 if r.returncode == 0 else 0


def main():
    instances = json.load(open(os.path.join(HERE, "instances.json")))["instances"]
    exp = json.load(open(os.path.join(HERE, "witness.json")))["answers"]

    print("%-46s %6s  %s" % ("CONTROL", "REWARD", "instances correct"))
    if reward(exp) != 1:
        print("ORACLE FAILED -- every number below would be meaningless")
        return 1
    print("%-46s %6d  %d/%d" % ("oracle", 1, len(exp), len(exp)))

    ok = True
    for name, fn in WRONG:
        rows = run_solver(instances, fn)
        r = reward(rows)
        same = sum(1 for a, b in zip(rows, exp) if a == b)
        if r != 0:
            ok = False
            name += "   <-- SHOULD BE 0"
        print("%-46s %6d  %d/%d" % (name, r, same, len(exp)))

    print()
    # Keep the claimed weight but hand in a different edge set: the certificate
    # check has to re-examine the graph to catch this.
    by_iid = {i["id"]: i for i in instances}
    swapped = [dict(a) for a in exp]
    for a in swapped:
        if not a["feasible"]:
            continue
        inst = by_iid[a["id"]]
        used = set(a["edges"])
        spare = [e["id"] for e in inst["edges"] if e["id"] not in used]
        if not spare:
            continue
        a["edges"] = sorted(used - {max(used)} | {spare[0]})
        break

    near = [dict(a) for a in exp]
    for a in near:
        if a["feasible"]:
            a["total_weight"] += 1
            break
    variants = [
        ("one instance off by one", near),
        ("array reversed", list(reversed([dict(a) for a in exp]))),
        ("one entry dropped", [dict(a) for a in exp[:-1]]),
        ("edge lists reversed",
         [dict(a, edges=list(reversed(a["edges"]))) for a in exp]),
        ("everything reported infeasible",
         [{"id": a["id"], "feasible": False, "total_weight": 0, "edges": []}
          for a in exp]),
        ("feasible sent as 0/1 instead of boolean",
         [dict(a, feasible=1 if a["feasible"] else 0) for a in exp]),
        ("an edge swapped for another real edge", swapped),
    ]
    for name, rows in variants:
        r = reward(rows)
        if r != 0:
            ok = False
            name += "   <-- SHOULD BE 0"
        print("%-46s %6d" % (name, r))
    print("%-46s %6d" % ("symlinked output path", reward(exp, symlink=True)))
    print("%-46s %6d" % ("nop (no file written)", reward([], missing=True)))
    print("%-46s %6d" % ("oracle again (stability)", reward(exp)))
    shutil.rmtree("/app", ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
