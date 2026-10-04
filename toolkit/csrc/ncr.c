/* ncr.c - negotiated-congestion (PathFinder) maze router on a multi-layer 0.05 mm grid.
 *
 * grid:    L layers x H rows x W cols, cell index c = y*W + x, layer-cell  lc = l*N + c
 * state:   s = lc*9 + d      d = arrival direction 0..7, 8 = none (start / after via)
 * static legality comes from Python per net (EDT of foreign copper):  ltrk[L*N], lvia[N]
 * shared congestion:  occ[L*N]  = number of routed objects whose (inflated) footprint covers the cell
 *                     hist[L*N] = PathFinder history cost
 * An object A conflicts with B when a cell of A's check-disc (radius rA, strict) lies in B's footprint
 * (radius rB + 0.5 cell, inclusive) - i.e. centre distance < rA + rB (+ half a cell of safety).
 * Build: gcc -O3 -shared -fPIC -o libncr.so ncr.c -lm
 */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

static int W, H, L, N;
static int16_t *occ;
static float *hist;
static float *gs, *glen;
static int32_t *prv, *gen, *stamp, *gmark, *ccache_gen, *vcache_gen;
static float *ccache, *vcache;
static int curgen = 0, curstamp = 0;
static float hweight = 1.0f;
void ncr_set_hw(float w) { hweight = w; }

typedef struct { float f; int32_t s; } HN;
static HN *heap = 0;
static int hn = 0, hcap = 0;

static void hpush(float f, int32_t s) {
    if (hn == hcap) { hcap = hcap ? hcap * 2 : 1 << 16; heap = realloc(heap, sizeof(HN) * hcap); }
    int i = hn++;
    while (i > 0) {
        int p = (i - 1) >> 1;
        if (heap[p].f <= f) break;
        heap[i] = heap[p]; i = p;
    }
    heap[i].f = f; heap[i].s = s;
}
static HN hpop(void) {
    HN top = heap[0], last = heap[--hn];
    int i = 0;
    for (;;) {
        int a = 2 * i + 1, b = a + 1, m = i;
        float fm = last.f;
        if (a < hn && heap[a].f < fm) { m = a; fm = heap[a].f; }
        if (b < hn && heap[b].f < fm) { m = b; }
        if (m == i) break;
        heap[i] = heap[m]; i = m;
    }
    if (hn) heap[i] = last;
    return top;
}

/* disc offset tables */
typedef struct { int n; int *dx, *dy; } Disc;
static Disc mkdisc(float r, int inclusive) {
    Disc d; int R = (int)ceilf(r) + 1, k = 0;
    d.dx = malloc(sizeof(int) * (2 * R + 1) * (2 * R + 1)); d.dy = malloc(sizeof(int) * (2 * R + 1) * (2 * R + 1));
    for (int y = -R; y <= R; y++)
        for (int x = -R; x <= R; x++) {
            float q = (float)(x * x + y * y);
            if (inclusive ? (q <= r * r + 1e-4f) : (q < r * r - 1e-4f) || (x == 0 && y == 0)) { d.dx[k] = x; d.dy[k] = y; k++; }
        }
    d.n = k; return d;
}
static void freedisc(Disc *d) { free(d->dx); free(d->dy); }

int ncr_init(int w, int h, int l) {
    W = w; H = h; L = l; N = W * H;
    size_t S = (size_t)L * N * 9;
    occ = calloc((size_t)L * N, sizeof(int16_t));
    hist = calloc((size_t)L * N, sizeof(float));
    stamp = calloc((size_t)L * N, sizeof(int32_t));
    gmark = calloc((size_t)L * N, sizeof(int32_t));
    ccache = calloc((size_t)L * N, sizeof(float));
    ccache_gen = calloc((size_t)L * N, sizeof(int32_t));
    vcache = calloc((size_t)N, sizeof(float));
    vcache_gen = calloc((size_t)N, sizeof(int32_t));
    gs = malloc(S * sizeof(float));
    glen = malloc(S * sizeof(float));
    prv = malloc(S * sizeof(int32_t));
    gen = calloc(S, sizeof(int32_t));
    return (occ && hist && gs && prv && gen) ? 0 : -1;
}

void ncr_reset(void) {
    memset(occ, 0, sizeof(int16_t) * (size_t)L * N);
    memset(hist, 0, sizeof(float) * (size_t)L * N);
}

float *ncr_hist(void) { return hist; }
int16_t *ncr_occ(void) { return occ; }

/* cells: sequence of layer-cells of a routed object; a via is two consecutive entries with the same c.
   Marks (delta=+1) or unmarks (delta=-1) the footprint, counting each grid cell once per call. */
void ncr_mark(const int32_t *cells, int n, float rtrk, float rvia, int delta) {
    Disc dt = mkdisc(rtrk + 0.5f, 1), dv = mkdisc(rvia + 0.5f, 1);
    curstamp++;
    for (int i = 0; i < n; i++) {
        int lc = cells[i]; if (lc < 0) continue;
        int l = lc / N, c = lc % N, x = c % W, y = c / W;
        int isvia = (i + 1 < n && cells[i + 1] >= 0 && cells[i + 1] % N == c && cells[i + 1] / N != l) ||
                    (i > 0 && cells[i - 1] >= 0 && cells[i - 1] % N == c && cells[i - 1] / N != l);
        if (isvia) {
            for (int ll = 0; ll < L; ll++)
                for (int k = 0; k < dv.n; k++) {
                    int xx = x + dv.dx[k], yy = y + dv.dy[k];
                    if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
                    int q = ll * N + yy * W + xx;
                    if (stamp[q] == curstamp) continue;
                    stamp[q] = curstamp; occ[q] += delta;
                }
        }
        for (int k = 0; k < dt.n; k++) {
            int xx = x + dt.dx[k], yy = y + dt.dy[k];
            if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
            int q = l * N + yy * W + xx;
            if (stamp[q] == curstamp) continue;
            stamp[q] = curstamp; occ[q] += delta;
        }
    }
    freedisc(&dt); freedisc(&dv);
}

/* number of cells of an (unmarked) object that conflict with the marked ones; adds hadd to hist there */
int ncr_conflicts(const int32_t *cells, int n, float rtrk, float rvia, float hadd) {
    Disc dt = mkdisc(rtrk, 0), dv = mkdisc(rvia, 0);
    int bad = 0;
    for (int i = 0; i < n; i++) {
        int lc = cells[i]; if (lc < 0) continue;
        int l = lc / N, c = lc % N, x = c % W, y = c / W;
        int isvia = (i + 1 < n && cells[i + 1] >= 0 && cells[i + 1] % N == c && cells[i + 1] / N != l);
        int hit = 0;
        for (int k = 0; k < dt.n && !hit; k++) {
            int xx = x + dt.dx[k], yy = y + dt.dy[k];
            if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
            if (occ[l * N + yy * W + xx] > 0) hit = 1;
        }
        if (isvia)
            for (int ll = 0; ll < L && !hit; ll++)
                for (int k = 0; k < dv.n && !hit; k++) {
                    int xx = x + dv.dx[k], yy = y + dv.dy[k];
                    if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
                    if (occ[ll * N + yy * W + xx] > 0) hit = 1;
                }
        if (hit) {
            bad++;
            if (hadd > 0) {
                for (int k = 0; k < dt.n; k++) {
                    int xx = x + dt.dx[k], yy = y + dt.dy[k];
                    if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
                    hist[l * N + yy * W + xx] += hadd / dt.n * 4.0f;
                }
                if (isvia) for (int ll = 0; ll < L; ll++) hist[ll * N + c] += hadd;
            }
        }
    }
    freedisc(&dt); freedisc(&dv);
    return bad;
}

static const int DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};

/* A* from any src layer-cell to any dst layer-cell inside the window [x0,x1)x[y0,y1).
   Returns the number of layer-cells written to out (src..dst), -1 no path, -2 out too small, -3 expansion cap */
int ncr_route(const uint8_t *ltrk, const uint8_t *lvia, int x0, int y0, int x1, int y1,
              const int32_t *src, int ns, const int32_t *dst, int nd,
              float rtrk, float rvia, const float *lcost, float via_cost, float bend45, float bend90,
              float pres_fac, float hist_w, const float *cmul, float maxlen, int max_exp, int32_t *out, int outcap) {
    Disc dt = mkdisc(rtrk, 0), dv = mkdisc(rvia, 0);
    curgen++;
    int gx0 = W, gy0 = H, gx1 = -1, gy1 = -1;
    for (int i = 0; i < nd; i++) {
        gmark[dst[i]] = curgen;
        int c = dst[i] % N, x = c % W, y = c / W;
        if (x < gx0) gx0 = x; if (x > gx1) gx1 = x; if (y < gy0) gy0 = y; if (y > gy1) gy1 = y;
    }
    float lmin = 1e9f;
    for (int l = 0; l < L; l++) if (lcost[l] < lmin) lmin = lcost[l];
    hn = 0;
#define HEUR(x, y) ({ int ddx = (x) < gx0 ? gx0 - (x) : ((x) > gx1 ? (x) - gx1 : 0); \
                      int ddy = (y) < gy0 ? gy0 - (y) : ((y) > gy1 ? (y) - gy1 : 0); \
                      int mx = ddx > ddy ? ddx : ddy, mn = ddx > ddy ? ddy : ddx; \
                      (mx + 0.41421f * mn) * lmin * hweight; })
#define HLEN(x, y) ({ int ddx = (x) < gx0 ? gx0 - (x) : ((x) > gx1 ? (x) - gx1 : 0); \
                      int ddy = (y) < gy0 ? gy0 - (y) : ((y) > gy1 ? (y) - gy1 : 0); \
                      int mx = ddx > ddy ? ddx : ddy, mn = ddx > ddy ? ddy : ddx; \
                      (mx + 0.41421f * mn); })
    for (int i = 0; i < ns; i++) {
        int lc = src[i], c = lc % N, x = c % W, y = c / W;
        if (x < x0 || x >= x1 || y < y0 || y >= y1) continue;
        int s = lc * 9 + 8;
        gen[s] = curgen; gs[s] = 0; prv[s] = -1; glen[s] = 0;
        hpush(HEUR(x, y), s);
    }
    int exp = 0, found = -1;
    while (hn) {
        HN t = hpop();
        int s = t.s, lc = s / 9, d = s % 9, l = lc / N, c = lc % N, x = c % W, y = c / W;
        float g = gs[s];
        if (t.f - HEUR(x, y) > g + 1e-3f) continue;      /* stale */
        if (gmark[lc] == curgen) { found = s; break; }
        if (++exp > max_exp) { freedisc(&dt); freedisc(&dv); return -3; }
        /* planar moves */
        for (int nd_ = 0; nd_ < 8; nd_++) {
            int turn = 0;
            if (d < 8) { turn = abs(nd_ - d); if (turn > 4) turn = 8 - turn; if (turn > 2) continue; }
            int xx = x + DX[nd_], yy = y + DY[nd_];
            if (xx < x0 || yy < y0 || xx >= x1 || yy >= y1) continue;
            int nlc = l * N + yy * W + xx;
            if (!ltrk[nlc]) continue;
            /* congestion cost of the cell (cached per call) */
            float pc;
            if (ccache_gen[nlc] == curgen) pc = ccache[nlc];
            else {
                int m = 0;
                for (int k = 0; k < dt.n; k++) {
                    int ax = xx + dt.dx[k], ay = yy + dt.dy[k];
                    if (ax < 0 || ay < 0 || ax >= W || ay >= H) continue;
                    int o = occ[l * N + ay * W + ax];
                    if (o > m) m = o;
                }
                pc = (1.0f + hist_w * hist[nlc]) * (1.0f + pres_fac * m);
                ccache[nlc] = pc; ccache_gen[nlc] = curgen;
            }
            float step = ((DX[nd_] && DY[nd_]) ? 1.41421f : 1.0f) * lcost[l] * pc;
            if (cmul) step *= cmul[nlc];
            if (turn == 1) step += bend45; else if (turn == 2) step += bend90;
            float ng = g + step;
            float nl = glen[s] + ((DX[nd_] && DY[nd_]) ? 1.41421f : 1.0f);
            if (maxlen > 0 && nl + HLEN(xx, yy) > maxlen) continue;
            int ns_ = nlc * 9 + nd_;
            if (gen[ns_] != curgen || ng < gs[ns_]) {
                gen[ns_] = curgen; gs[ns_] = ng; prv[ns_] = s; glen[ns_] = nl;
                hpush(ng + HEUR(xx, yy), ns_);
            }
        }
        /* via (through, any layer pair) */
        if (lvia && lvia[c]) {
            float vc;
            if (vcache_gen[c] == curgen) vc = vcache[c];
            else {
                int m = 0; float hh = 0;
                for (int ll = 0; ll < L; ll++) {
                    for (int k = 0; k < dv.n; k++) {
                        int ax = x + dv.dx[k], ay = y + dv.dy[k];
                        if (ax < 0 || ay < 0 || ax >= W || ay >= H) continue;
                        int o = occ[ll * N + ay * W + ax];
                        if (o > m) m = o;
                    }
                    if (hist[ll * N + c] > hh) hh = hist[ll * N + c];
                }
                vc = via_cost * (1.0f + hist_w * hh) * (1.0f + pres_fac * m);
                vcache[c] = vc; vcache_gen[c] = curgen;
            }
            for (int nl = 0; nl < L; nl++) {
                if (nl == l) continue;
                int nlc = nl * N + c;
                if (!ltrk[nlc] || lcost[nl] > 50.0f) continue;
                float ng = g + vc;
                int ns_ = nlc * 9 + 8;
                if (gen[ns_] != curgen || ng < gs[ns_]) {
                    gen[ns_] = curgen; gs[ns_] = ng; prv[ns_] = s; glen[ns_] = glen[s];
                    hpush(ng + HEUR(x, y), ns_);
                }
            }
        }
    }
    freedisc(&dt); freedisc(&dv);
    if (found < 0) return -1;
    int n = 0;
    for (int s = found; s >= 0; s = prv[s]) n++;
    if (n > outcap) return -2;
    int i = n;
    for (int s = found; s >= 0; s = prv[s]) out[--i] = s / 9;
    return n;
}
