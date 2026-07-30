Fifty directed graphs are given in `/app/data/instances.json`. For each one,
find the cheapest way to reach every vertex from a designated root, and prove
that nothing cheaper exists — or prove that no such structure exists at all.

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

The graphs are not tidy. Across the battery you will find self-loops, several
edges sharing the same tail and head, and edges pointing at the root. None of
that is an error in the data; handle it. Where several parallel edges share the
same tail, head and weight, any one of them may be named — they are
interchangeable.

## What to compute

For each instance, find a **minimum-weight spanning arborescence rooted at
`root`**: a subset `A` of the edges such that

1. every vertex other than `root` is the head of **exactly one** edge in `A`
   (that is, exactly one edge of `A` points at it), and
2. every vertex can be reached from `root` by following edges of `A` forwards,

and whose total weight — the sum of `w` over the edges in `A` — is as small as
possible. Note that these two conditions together mean `root` is the head of no
edge in `A`, and that no edge of `A` has the same head and tail.

Report the minimum total weight from **every** root `0` through `n-1` as well,
using `null` for any root from which no spanning arborescence exists. Only the
designated root needs a proof.

An answer on its own is not enough. Each instance must come with a proof, and
the proof is what is checked.

### Proving an arborescence is the cheapest

Every spanning arborescence must contain at least one edge entering **every**
non-empty set of vertices that does not contain the root — otherwise the
vertices in that set could never be reached. Suppose you supply numbers `y(S) ≥ 0`
attached to some such sets, with the property that for every edge `e` of the
graph, the total of `y(S)` over the sets `S` that `e` enters (head inside `S`,
tail outside) is at most `w(e)`. Then every spanning arborescence costs at least
the sum of all your `y(S)`. So if you also exhibit an arborescence whose weight
equals that sum, it cannot be beaten.

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
       "dual": [[[1, 4, 7], 5], [[4], 12], [[7], 3]],
       "cut": [],
       "root_weights": [37, null, 41, 39, null, 44]},
      {"id": "G-002", "feasible": false, "total_weight": 0, "edges": [],
       "dual": [], "cut": [3, 8, 11],
       "root_weights": [null, 52, null, null, 61, 58]}
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
order, each an integer or `null`. When the instance is feasible,
`root_weights[root]` equals `total_weight`.

Instances with no arborescence are represented this way throughout and count
once each, exactly like the rest. Write no other files.

Write `/app/answer.json` as soon as you have an entry for every instance and
overwrite it as you refine it. A missing file scores zero.

Several arborescences may share the minimum weight, and several proofs may
certify one; any correct combination is accepted.

The graphs have 30 to 38 vertices, which is small to look at and large to search:
trying every choice of one incoming edge per vertex runs to more than 10^14
possibilities on the smallest instance here, and holding one value per subset of
vertices would need more memory than this container has. A method that scales is
required.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and is a JSON object whose `answers` value is an
   array with exactly one well-formed entry per instance, in the order they
   appear in `instances.json`, using the field names, types and value formats
   described above.
2. Every entry is right and proved — for a feasible instance the edges form a
   spanning arborescence whose weights sum to the reported total, that total is
   the minimum achievable, and the `dual` values satisfy the conditions above
   and sum to it; for an infeasible instance the `cut` is a non-empty set of
   non-root vertices with no edge entering it. `root_weights` is correct for
   every root of every instance. All fifty must be correct.
