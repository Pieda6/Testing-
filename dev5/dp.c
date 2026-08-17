/* Independent exact solver: subset DP over reachable vertex sets.
 *
 * Shares no idea with Chu-Liu/Edmonds -- there is no cycle, no contraction and
 * no reduced weight anywhere in here. An arborescence rooted at r can be built
 * by repeatedly attaching a new vertex to one already attached (take the
 * vertices in any order consistent with distance from the root), so
 *
 *     f[{r}]      = 0
 *     f[S + {v}]  = min over u in S of  f[S] + w(u -> v)
 *
 * and the optimum is f[all vertices]. That is exponential in n, which is why it
 * is written in C and used only at authoring time to check the shipped answer
 * key -- but it is exact, and being exact by a different route is the point.
 *
 * stdin:  n root m, then m lines of "u v w"
 * stdout: "INFEASIBLE" or the optimal total weight
 */
#include <stdio.h>
#include <stdlib.h>

#define INF 1000000000

int main(void) {
    int n, root, m;
    if (scanf("%d %d %d", &n, &root, &m) != 3) return 2;

    int *eu = malloc(sizeof(int) * (size_t)m);
    int *ev = malloc(sizeof(int) * (size_t)m);
    int *ew = malloc(sizeof(int) * (size_t)m);
    int *head = malloc(sizeof(int) * (size_t)n);
    int *next = malloc(sizeof(int) * (size_t)m);
    if (!eu || !ev || !ew || !head || !next) return 3;

    for (int i = 0; i < n; i++) head[i] = -1;
    int kept = 0;
    for (int i = 0; i < m; i++) {
        int u, v, w;
        if (scanf("%d %d %d", &u, &v, &w) != 3) return 2;
        if (u == v || v == root) continue;      /* can never be in an arborescence */
        eu[kept] = u; ev[kept] = v; ew[kept] = w;
        next[kept] = head[v];
        head[v] = kept;
        kept++;
    }

    size_t ns = (size_t)1 << n;
    int *f = malloc(sizeof(int) * ns);
    if (!f) return 3;
    for (size_t s = 0; s < ns; s++) f[s] = INF;
    f[(size_t)1 << root] = 0;

    for (size_t s = 0; s < ns; s++) {
        if (!((s >> root) & 1)) continue;
        int base = f[s];
        if (base >= INF) continue;
        for (int v = 0; v < n; v++) {
            if ((s >> v) & 1) continue;
            int best = INF;
            for (int k = head[v]; k != -1; k = next[k]) {
                if ((s >> eu[k]) & 1) {
                    if (ew[k] < best) best = ew[k];
                }
            }
            if (best >= INF) continue;
            size_t t = s | ((size_t)1 << v);
            if (base + best < f[t]) f[t] = base + best;
        }
    }

    int ans = f[ns - 1];
    if (ans >= INF) printf("INFEASIBLE\n");
    else printf("%d\n", ans);
    return 0;
}
