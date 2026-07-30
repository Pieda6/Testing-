`/app/data/instances.json` holds fifty directed graphs. For each one, find the
cheapest way to reach every vertex from a designated root and prove nothing
cheaper exists, or prove no such structure exists at all.

## The input

`instances` is an array. Each entry has `id` (e.g. `"G-007"`), `n` vertices
numbered `0` to `n-1`, a `root`, and `edges`: objects
`{"id": <int>, "u": <int>, "v": <int>, "w": <int>}` meaning an edge from `u` to
`v` of weight `w`. Weights are non-negative. Edge ids are unique within an
instance, numbered from `0` in listing order, and name one specific listed edge
rather than a `(u, v, w)` combination.

The graphs contain self-loops, parallel edges, and edges pointing at the root.
None of that is an error. Where parallel edges share tail, head and weight, any
one of them may be named.

## What to compute

A **spanning arborescence rooted at `root`** is a subset `A` of the edges where

1. every vertex other than `root` is the head of exactly one edge in `A`, and
2. every vertex is reachable from `root` along edges of `A`.

Find one of minimum total weight. These conditions imply `root` is the head of no
edge in `A`, and no edge of `A` has equal head and tail.

Also report the minimum total weight from **every** root `0` to `n-1`, using
`null` for any root admitting no spanning arborescence. Only the designated root
needs a proof.

### Proving an arborescence is cheapest

Every spanning arborescence contains at least one edge entering every non-empty
vertex set that excludes the root, or that set would be unreachable. So supply
values `y(S) >= 0` on some such sets, with the property that for every edge `e`,
the total of `y(S)` over the sets `S` that `e` enters — head inside `S`, tail
outside — is at most `w(e)`. Then every spanning arborescence costs at least the
sum of your `y(S)`, so an arborescence whose weight equals that sum cannot be
beaten. Sets you omit count as `y(S) = 0`. Give these in `dual`, at most 5000
entries per instance.

### Proving none exists

Give a non-empty set of vertices, none of them the root, with no edge of the
graph entering it. Nothing can reach them, so no spanning arborescence exists.
Give it in `cut`.

## Output

Write `/app/answer.json`: an object whose `answers` value is an array with one
entry per instance, in the same order as `instances.json`.

    {"answers": [
      {"id": "G-001", "feasible": true, "total_weight": 37,
       "edges": [0, 2, 5, 9], "dual": [[[1, 4, 7], 5], [[4], 12]],
       "cut": [], "root_weights": [37, null, 41, 39, null, 44]},
      {"id": "G-002", "feasible": false, "total_weight": 0, "edges": [],
       "dual": [], "cut": [3, 8, 11],
       "root_weights": [null, 52, null, null, 61, 58]}
    ]}

`feasible` is a JSON boolean. When `true`: `total_weight` is the minimum weight
as an integer, `edges` lists the arborescence's edge ids sorted ascending, `dual`
is the proof above as `[vertices, value]` pairs with vertices sorted ascending
and value a non-negative integer, and `cut` is empty. When `false`:
`total_weight` is `0`, `edges` and `dual` are empty, and `cut` holds the vertices
described above, sorted ascending. Infeasible instances use this same shape and
count once each, like the rest.

`root_weights` is present either way: exactly `n` entries, one per root in order,
each an integer or `null`. When the instance is feasible, `root_weights[root]`
equals `total_weight`.

Write no other files. Write `/app/answer.json` once you have an entry for every
instance and overwrite it as you refine it; a missing file scores zero.

Several arborescences may share the minimum weight, and several proofs may
certify one — any correct combination is accepted.

All fifty entries must be correct: matching feasibility, an edge set that is a
spanning arborescence summing to the reported minimum total, a `dual` satisfying
the conditions above and summing to it or a `cut` with no entering edge, and
`root_weights` right for every root.
