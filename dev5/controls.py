"""Control battery for dynamo/arborescence-battery.

Runs the REAL verifier (task5/tests/test_outputs.py under pytest) against the
oracle and against submissions that are wrong in the ways a real attempt goes
wrong -- including the library route, which is the reason the task asks for a
proof rather than just an answer.

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

import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "solve", os.path.join(HERE, "..", "task5", "solution", "solve.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


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


# ------------------------------------------------------- the library route --
def _nx_weight(nx, inst, root):
    G = nx.MultiDiGraph()
    G.add_nodes_from(range(inst["n"]))
    for e in inst["edges"]:
        if e["u"] == e["v"] or e["v"] == root:
            continue
        G.add_edge(e["u"], e["v"], key=e["id"], weight=e["w"])
    try:
        A = nx.minimum_spanning_arborescence(G, preserve_attrs=True)
    except Exception:
        return None
    return int(sum(d["weight"] for _u, _v, d in A.edges(data=True)))


def networkx_answers(instances, dual="empty", roots=True):
    """What `pip install networkx` buys, with various attempts at the proof."""
    import networkx as nx
    out = []
    for inst in instances:
        G = nx.MultiDiGraph()
        G.add_nodes_from(range(inst["n"]))
        for e in inst["edges"]:
            if e["u"] == e["v"] or e["v"] == inst["root"]:
                continue
            G.add_edge(e["u"], e["v"], key=e["id"], weight=e["w"])
        edges_t = [(e["u"], e["v"], e["w"], e["id"]) for e in inst["edges"]]
        try:
            A = nx.minimum_spanning_arborescence(G, preserve_attrs=True)
            # networkx re-keys the result, so ids are recovered by matching
            # (tail, head, weight) back to the input -- the edge-id plumbing the
            # library route still has to do for itself.
            pool = {}
            for e in inst["edges"]:
                pool.setdefault((e["u"], e["v"], e["w"]), []).append(e["id"])
            ids = []
            for u, v, d in A.edges(data=True):
                ids.append(pool[(u, v, d["weight"])].pop())
            ids.sort()
            w = int(sum(d["weight"] for _u, _v, d in A.edges(data=True)))
            row = {"id": inst["id"], "feasible": True, "total_weight": w,
                   "edges": ids, "dual": [], "cut": []}
            if dual == "real":
                d = S.dual_solution(inst["n"], inst["root"], edges_t)
                row["dual"] = [[s, y] for s, y in d]
        except Exception:
            row = {"id": inst["id"], "feasible": False, "total_weight": 0,
                   "edges": [], "dual": [],
                   "cut": S.unreachable_cut(inst["n"], edges_t, inst["root"])}
        if roots == "reference":
            row["root_weights"] = S.root_weights(inst["n"], edges_t)
        elif roots:
            row["root_weights"] = [_nx_weight(nx, inst, r)
                                   for r in range(inst["n"])]
        else:
            row["root_weights"] = [None] * inst["n"]
        out.append(row)
    return out


def main():
    instances = json.load(open(os.path.join(HERE, "instances.json")))["instances"]
    exp = json.load(open(os.path.join(HERE, "witness.json")))["answers"]
    by_iid = {i["id"]: i for i in instances}

    print("%-52s %s" % ("CONTROL", "REWARD"))
    if reward(exp) != 1:
        print("ORACLE FAILED -- every number below would be meaningless")
        return 1
    print("%-52s %d" % ("oracle (arborescence + dual + cut)", 1))

    ok = True

    def show(name, rows, want=0, **kw):
        nonlocal ok
        r = reward(rows, **kw)
        if r != want:
            ok = False
            name += "   <-- SHOULD BE %d" % want
        print("%-52s %d" % (name, r))

    # --- the library shortcut -------------------------------------------------
    show("networkx optimum, dual left empty", networkx_answers(instances))
    nx_nodual = [{k: v for k, v in a.items() if k != "dual"}
                 for a in networkx_answers(instances)]
    show("networkx optimum, dual field omitted", nx_nodual)
    # networkx gets one root's feasibility wrong (G-039 root 15: it reports no
    # arborescence where one of weight 428 exists, proved by duality), so the
    # pure-library route fails on correctness, not just on the missing proof.
    show("networkx throughout, with a real dual",
         networkx_answers(instances, dual="real"))
    # Fairness: networkx's arborescence for the designated root -- a different
    # optimum from the reference on many instances -- with a real dual and a
    # correct per-root vector must be accepted.
    show("networkx arborescence + real dual + correct per-root",
         networkx_answers(instances, dual="real", roots="reference"), want=1)

    show("networkx optimum, per-root vector left null",
         networkx_answers(instances, dual="real", roots=False))
    nx_norw = [{k: v for k, v in a.items() if k != "root_weights"}
               for a in networkx_answers(instances, dual="real")]
    show("root_weights field omitted", nx_norw)
    only_given = [json.loads(json.dumps(a)) for a in exp]
    for a, i in zip(only_given, instances):
        a["root_weights"] = [a["root_weights"][r] if r == i["root"] else None
                             for r in range(i["n"])]
    show("root_weights only for the designated root", only_given)
    off_one = [json.loads(json.dumps(a)) for a in exp]
    for a in off_one:
        for r, w in enumerate(a["root_weights"]):
            if w is not None:
                a["root_weights"][r] = w + 1
                break
        else:
            continue
        break
    show("one root weight off by one", off_one)

    # --- broken proofs on a correct answer ------------------------------------
    def tweak(fn):
        rows = [json.loads(json.dumps(a)) for a in exp]
        for a in rows:
            if a["feasible"] and a["dual"]:
                fn(a)
                break
        return rows

    show("dual with one value inflated",
         tweak(lambda a: a["dual"][0].__setitem__(1, a["dual"][0][1] + 1)))
    show("dual with one entry dropped",
         tweak(lambda a: a["dual"].pop(0)))
    show("dual with a value negated",
         tweak(lambda a: a["dual"][0].__setitem__(1, -a["dual"][0][1])))
    show("dual set containing the root", tweak(
        lambda a: a["dual"][0].__setitem__(
            0, sorted(set(a["dual"][0][0]) | {by_iid[a["id"]]["root"]}))))

    # --- broken cut certificates ---------------------------------------------
    def tweak_cut(fn):
        rows = [json.loads(json.dumps(a)) for a in exp]
        for a in rows:
            if not a["feasible"]:
                fn(a, by_iid[a["id"]])
                break
        return rows

    show("infeasible reported with an empty cut",
         tweak_cut(lambda a, i: a.__setitem__("cut", [])))
    show("cut widened until an edge enters it", tweak_cut(
        lambda a, i: a.__setitem__(
            "cut", sorted(set(a["cut"]) | {v for v in range(i["n"])
                                           if v != i["root"]} - {i["root"]}))))

    # --- schema and near misses ----------------------------------------------
    off = [json.loads(json.dumps(a)) for a in exp]
    for a in off:
        if a["feasible"]:
            a["total_weight"] += 1
            break
    show("one instance off by one", off)
    show("array reversed", list(reversed([dict(a) for a in exp])))
    show("one entry dropped", [dict(a) for a in exp[:-1]])
    show("edge lists reversed",
         [dict(a, edges=list(reversed(a["edges"]))) for a in exp])
    show("everything reported infeasible",
         [{"id": a["id"], "feasible": False, "total_weight": 0, "edges": [],
           "dual": [], "cut": [1], "root_weights": a["root_weights"]}
          for a in exp])
    show("feasible sent as 0/1 instead of boolean",
         [dict(a, feasible=1 if a["feasible"] else 0) for a in exp])
    show("symlinked output path", exp, symlink=True)
    show("nop (no file written)", [], missing=True)
    show("oracle again (stability)", exp, want=1)

    shutil.rmtree("/app", ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
