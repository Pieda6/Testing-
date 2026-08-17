`/app/data/instances.json` holds fifty directed graphs. For each one, find the
cheapest way to reach every vertex from a designated root and prove nothing
cheaper exists, or prove no such structure exists at all.

## The input

`/app/data/instances.json` is a JSON object whose `instances` value is an array.
Each entry has:

- `id` — the instance identifier, e.g. `"G-007"`
- `n` — the number of vertices, which are numbered `0` through `n-1`
- `root` — the root vertex
- `edges` — an array of directed edges, each `{"id": <int>, "u": <int>,
  "v": <int>, "w": <int>}`, meaning an edge from `u` to `v` of weight `w`.
  Weights are non-negative. Edge ids are unique within an instance, are numbered
  from `0` in the order the edges are listed, and identify one specific listed
  edge rather than a `(u, v, w)` combination.

The graphs contain self-loops, parallel edges, and edges pointing at the root;
none of that is an error. Where parallel edges share tail, head and weight, any
one of them may be named.

## What to compute

For each instance, find a **minimum-weight spanning arborescence rooted at
`root`**: a subset `A` of the edges such that

1. every vertex other than `root` is the head of **exactly one** edge in `A`
   (that is, exactly one edge of `A` points at it), and
2. every vertex can be reached from `root` by following edges of `A` forwards,

and whose total weight — the sum of `w` over the edges in `A` — is as small as
possible. Note that these two conditions together mean `root` is the head of no
edge in `A`, and that no edge of `A` has the same head and tail.

Also report the minimum weight from every root `0` to `n-1`, `null` where none
exists; only the designated root needs a proof.

An answer on its own is not enough. Each instance must come with a proof, and
the proof is what is checked.

### Proving an arborescence is the cheapest

Every spanning arborescence contains at least one edge entering **every**
non-empty set of vertices excluding the root, or that set would be unreachable.
So supply numbers `y(S) ≥ 0` on some such sets, such that for every edge `e` the
total of `y(S)` over the sets `S` that `e` enters (head inside `S`, tail outside)
is at most `w(e)`. Then every spanning arborescence costs at least the sum of your
`y(S)`, so an arborescence whose weight equals that sum cannot be beaten.

Supply those sets and values in the `dual` field. Sets that you do not mention
are taken to have `y(S) = 0`. At most 5000 entries per instance are accepted.

### Proving no arborescence exists

Give a non-empty set of vertices, none of them the root, with **no edge of the
graph entering it** — no edge whose head is inside the set and whose tail is
outside. Nothing can ever reach those vertices from the root, so no spanning
arborescence exists. Supply it in the `cut` field.

## Output

Write `/app/answer.json`, a JSON object whose `answers` value is an array with
one entry per instance, **in the same order as `instances.json`**:

    {"answers": [
      {"id": "G-001", "feasible": true, "total_weight": 37,
       "edges": [0, 2, 5, 9],
       "dual": [[[1, 4, 7], 5], [[4], 12]],
       "cut": [], "root_weights": [37, null, 41]},
      {"id": "G-002", "feasible": false, "total_weight": 0, "edges": [],
       "dual": [], "cut": [3, 8, 11], "root_weights": [null, 52, 61]}
    ]}

`feasible` is a JSON boolean — `true` when the instance has a spanning
arborescence, `false` when it does not.

When it is `true`: `total_weight` is the weight of the minimum arborescence as an
integer, `edges` lists the ids of the edges in that arborescence sorted
ascending, `dual` is the proof described above as a list of `[vertices, value]`
pairs with the vertices sorted ascending and the value a non-negative integer,
and `cut` is empty.

When it is `false`: `total_weight` is `0`, `edges` and `dual` are empty, and
`cut` holds the vertices of the empty-entering-set described above, sorted
ascending.

`root_weights` is present either way: exactly `n` entries, one per root in
order, each an integer or `null`.

Infeasible instances use this shape and count once each, like the rest. Write no
other files.

Write `/app/answer.json` as soon as you have an entry for every instance and
overwrite it as you refine it. A missing file scores zero.

Several arborescences may share the minimum weight, and several proofs may
certify one; any correct combination is accepted.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and is a JSON object whose `answers` value is an
   array with exactly one well-formed entry per instance, in the order they
   appear in `instances.json`, using the field names, types and value formats
   described above.
2. Every entry is right and proved — for a feasible instance the edges form a
   spanning arborescence whose weights sum to the reported total, that total is
   the minimum achievable, and the `dual` values satisfy the conditions above
   and sum to it; for an infeasible instance the `cut` is a non-empty set of
   non-root vertices with no edge entering it; and `root_weights` is right for
   every root. All fifty must be correct.
