"""Independent validation of the shipped answer key.

For every shipped instance this re-derives the optimal weight with the subset DP
in dp.c -- a different algorithm, in a different language, sharing no code with
the reference solver -- and separately checks that the reference solver's edge
set really is a spanning arborescence of exactly that weight.

Those two together are what make the key trustworthy: the DP proves no cheaper
arborescence exists, and the structural check proves the claimed weight is
actually attained by a real arborescence.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DP = os.path.join(HERE, "dp")


def dp_weight(inst):
    payload = ["%d %d %d" % (inst["n"], inst["root"], len(inst["edges"]))]
    payload += ["%d %d %d" % (e["u"], e["v"], e["w"]) for e in inst["edges"]]
    r = subprocess.run([DP], input="\n".join(payload) + "\n",
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("dp failed on %s: %s" % (inst["id"], r.stderr))
    out = r.stdout.strip()
    return None if out == "INFEASIBLE" else int(out)


def check_structure(inst, edge_ids, claimed):
    """Is this edge set a spanning arborescence of weight `claimed`?"""
    by_id = {e["id"]: e for e in inst["edges"]}
    if any(i not in by_id for i in edge_ids):
        return "references an edge id that does not exist"
    chosen = [by_id[i] for i in edge_ids]
    if len(chosen) != inst["n"] - 1:
        return "%d edges for %d vertices" % (len(chosen), inst["n"])
    if any(e["u"] == e["v"] for e in chosen):
        return "uses a self-loop"
    heads = [e["v"] for e in chosen]
    if inst["root"] in heads:
        return "an edge points at the root"
    if len(set(heads)) != len(heads):
        return "two edges share a head"
    parent = {e["v"]: e["u"] for e in chosen}
    for v in range(inst["n"]):
        if v == inst["root"]:
            continue
        seen, x = set(), v
        while x != inst["root"]:
            if x in seen or x not in parent:
                return "vertex %d does not reach the root" % v
            seen.add(x)
            x = parent[x]
    if sum(e["w"] for e in chosen) != claimed:
        return "edge weights sum to %d, not %d" % (
            sum(e["w"] for e in chosen), claimed)
    return None


def main(inst_path, key_path, witness_path):
    instances = json.load(open(inst_path))["instances"]
    key = json.load(open(key_path))["answers"]
    witness = json.load(open(witness_path))["answers"]

    if not (len(instances) == len(key) == len(witness)):
        print("FAIL: length mismatch")
        return 1

    errs = []
    n_feasible = 0
    t0 = time.time()
    for inst, k, w in zip(instances, key, witness):
        if inst["id"] != k["id"] or inst["id"] != w["id"]:
            errs.append("%s: id mismatch across files" % inst["id"])
            continue
        opt = dp_weight(inst)

        if opt is None:
            if k["feasible"]:
                errs.append("%s: subset DP says no arborescence exists, key "
                            "says feasible" % inst["id"])
            elif k["total_weight"] != 0:
                errs.append("%s: infeasible entry carries a weight" % inst["id"])
            continue

        n_feasible += 1
        if not k["feasible"]:
            errs.append("%s: key says infeasible, but an arborescence of "
                        "weight %d exists" % (inst["id"], opt))
            continue
        if k["total_weight"] != opt:
            errs.append("%s: key weight %d, subset DP optimum %d"
                        % (inst["id"], k["total_weight"], opt))
        bad = check_structure(inst, w["edges"], k["total_weight"])
        if bad:
            errs.append("%s: reference witness %s" % (inst["id"], bad))

    print("checked %d instances (%d with an arborescence, %d without) in %.1fs"
          % (len(instances), n_feasible, len(instances) - n_feasible,
             time.time() - t0))
    if errs:
        print("\n%d PROBLEMS:" % len(errs))
        for e in errs[:40]:
            print("  -", e)
        return 1
    print("every optimum re-derived by the independent subset DP; every "
          "reference witness is a real arborescence of the stated weight")
    return 0


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "instances.json"
    b = sys.argv[2] if len(sys.argv) > 2 else "expected.json"
    c = sys.argv[3] if len(sys.argv) > 3 else "witness.json"
    raise SystemExit(main(a, b, c))
