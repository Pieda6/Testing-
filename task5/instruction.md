Fifty directed graphs are given in `/app/data/instances.json`. For each one,
find the cheapest way to reach every vertex from a designated root, or determine
that no such structure exists.

## The input

`/app/data/instances.json` is a JSON object whose `instances` value is an array.
Each entry has:

- `id` — the instance identifier, e.g. `"G-007"`
- `n` — the number of vertices, which are numbered `0` through `n-1`
- `root` — the root vertex
- `edges` — an array of directed edges, each `{"id": <int>, "u": <int>,
  "v": <int>, "w": <int>}`, meaning an edge from `u` to `v` of weight `w`.
  Edge ids are unique within an instance and are numbered from `0` in the order
  the edges are listed.

The graphs are not tidy. Across the battery you will find self-loops, several
edges sharing the same endpoints, edges pointing at the root, and weights that
are negative or zero as well as positive. None of that is an error in the data;
handle it.

## What to compute

For each instance, find a **minimum-weight spanning arborescence rooted at
`root`**: a subset `A` of the edges such that

1. every vertex other than `root` is the head of **exactly one** edge in `A`
   (that is, exactly one edge of `A` points at it), and
2. every vertex can be reached from `root` by following edges of `A` forwards,

and whose total weight — the sum of `w` over the edges in `A` — is as small as
possible. Note that these two conditions together mean `root` is the head of no
edge in `A`, and that no edge of `A` has the same head and tail.

If no subset satisfies both conditions, the instance has no spanning
arborescence and must be reported as such.

An instance may have more than one arborescence of minimum weight. Any one of
them is accepted: what is checked is that the edges you give really do form a
spanning arborescence, that their weights sum to the total you report, and that
the total is the smallest achievable. Reporting a valid arborescence that is not
the cheapest is wrong.

The graphs have 30 to 38 vertices, which is small to look at and large to search:
trying every choice of one incoming edge per vertex runs to more than 10^14
possibilities on the smallest instance here, and holding one value per subset of
vertices would need more memory than this container has. A method that scales is
required.

## Output

Write `/app/answer.json`, a JSON object whose `answers` value is an array with
one entry per instance, **in the same order as `instances.json`**:

    {"answers": [
      {"id": "G-001", "feasible": true, "total_weight": 37,
       "edges": [0, 2, 5, 9]},
      {"id": "G-002", "feasible": false, "total_weight": 0, "edges": []}
    ]}

`feasible` is a JSON boolean — `true` when the instance has a spanning
arborescence, `false` when it does not. When it is `true`, `total_weight` is the
weight of the minimum arborescence as an integer (it may be negative or zero),
and `edges` lists the ids of the edges in that arborescence, sorted ascending.
When it is `false`, `total_weight` is `0` and `edges` is empty. Write no other
files.

Write `/app/answer.json` as soon as you have an answer for every instance and
overwrite it as you refine it. A missing file scores zero.

Your submission is correct when both of the following hold:

1. `/app/answer.json` exists and is a JSON object whose `answers` value is an
   array with exactly one well-formed entry per instance, in the order they
   appear in `instances.json`, using the field names, types and value formats
   described above.
2. Every entry is right — feasibility matches, the edges listed form a spanning
   arborescence of the graph, their weights sum to the total reported, and that
   total is the minimum achievable. All fifty must be correct.
