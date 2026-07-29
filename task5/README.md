# dynamo/arborescence-battery

Compute the minimum-weight spanning arborescence of fifty directed graphs with a
certificate of optimality, or prove that none exists.

**Category:** Mathematics and Formal Reasoning
**Sub-category:** Algorithms and Optimization theory

## The task

The agent is given fifty directed graphs of 30 to 38 vertices in
`/app/data/instances.json`. For each one it must find a minimum-weight spanning
arborescence rooted at a designated vertex — a set of edges giving every other
vertex exactly one parent, with every vertex reachable from the root, of least
total weight — or determine that the graph admits none. Thirty-eight of the fifty
are feasible; twelve are not.

An answer alone is not enough. Every entry must carry its own proof:

- **feasible** — the arborescence together with a dual solution: non-negative
  values on sets of non-root vertices, charging no edge more than its weight and
  summing to the weight of the arborescence. Since every spanning arborescence
  contains an edge entering every such set, this lower-bounds all arborescences,
  so matching the bound proves optimality.
- **infeasible** — a non-empty set of non-root vertices with no edge entering it,
  which proves nothing can reach them from the root.

Results go to `/app/answer.json`. Grading is all-or-nothing across all fifty.

## Why it is hard

Giving each vertex its cheapest incoming edge is what undirected intuition
suggests and is wrong whenever those choices close a cycle; it gets 8 of 50 right.
Chu-Liu/Edmonds is needed, and its contraction step is easy to implement almost
correctly — contracting a single level scores 19 of 50, contracting two but not
three scores 31. Feasibility is not an in-degree test: eight instances give every
vertex an incoming edge while leaving a group cut off from the root, and an
in-degree check scores 42 of 50.

The certificate is what stops a library from settling it.
`networkx.minimum_spanning_arborescence` solves the whole battery correctly in
0.3 seconds and scores 0 here, because the dual has to come from understanding
the algorithm rather than calling it — the amount subtracted at each reduction
step *is* the dual value of the set that vertex represents.

Sizing removes the brute-force routes on every instance: enumerating one incoming
edge per vertex runs to 10^14 combinations at the smallest and 10^24 at the
largest, and an exact subset DP would need 4.3 GB of state on the smallest
instance against a 2 GB container.

## Layout

```
task.toml                      task metadata and resource limits
instruction.md                 what the agent is told
environment/Dockerfile         the single image, for both agent and verifier
environment/data/              instances.json — the only input the agent gets
solution/solve.sh              oracle entrypoint
solution/solve.py              reference solver, primal + dual + cut
tests/test.sh                  verifier entrypoint, writes reward.txt
tests/test_outputs.py          certificate verification
tests/expected.json            held-out optimum per instance
tests/instances.json           trusted copy of the graphs
```

`tests/` is overlaid only at verification time and is never in the agent's image.
The trusted copy of the graphs matters because `/app/data` is writable by the
agent, so the verifier must not read them from there.

## Verification

Correctness is checked by certificate, so any optimal arborescence with any valid
proof is accepted rather than one blessed edge set. The submitted edges are
re-examined against the graph, the dual is checked for non-negativity and for the
covering constraint on every edge, and its value must equal the arborescence
weight. The held-out optimum is checked too, so an answer must be both provably
optimal and equal to the known value. The result is read with `O_NOFOLLOW` so a
symlinked output path cannot alias another file.

The answer key was established three ways: differential testing of the reference
solver against exhaustive enumeration on 2500 small graphs and against an exact
subset DP in C on 400 larger ones, with zero mismatches; and every shipped answer
proved optimal by the same duality argument the verifier applies, using a checker
that does not trust the solver.

The data is synthetic and generated deterministically from a fixed seed via
SHA-256, so the inputs are byte-identical on every run and platform.
