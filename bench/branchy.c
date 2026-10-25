/* Integer, branch- and data-dependent workload: quicksort + binary search + Collatz.
 * Behaves very differently from matmul under optimization. Usage: ./branchy [N] (default 3000000) */
#include <stdio.h>
#include <stdlib.h>

static unsigned state = 12345u;
static inline unsigned rnd(void) { state = state * 1664525u + 1013904223u; return state >> 8; }

static void isort(unsigned *a, long lo, long hi) {
    for (long i = lo + 1; i <= hi; i++) {
        unsigned v = a[i]; long j = i - 1;
        while (j >= lo && a[j] > v) { a[j + 1] = a[j]; j--; }
        a[j + 1] = v;
    }
}

static void qsort_u(unsigned *a, long lo, long hi) {
    while (hi - lo > 16) {
        unsigned p = a[lo + (hi - lo) / 2];
        long i = lo, j = hi;
        while (i <= j) {
            while (a[i] < p) i++;
            while (a[j] > p) j--;
            if (i <= j) { unsigned t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
        }
        if (j - lo < hi - i) { qsort_u(a, lo, j); lo = i; }
        else { qsort_u(a, i, hi); hi = j; }
    }
    isort(a, lo, hi);
}

static long bsearch_u(const unsigned *a, long n, unsigned key) {
    long lo = 0, hi = n - 1;
    while (lo <= hi) {
        long mid = lo + (hi - lo) / 2;
        if (a[mid] == key) return mid;
        if (a[mid] < key) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 3000000;
    unsigned *a = malloc(sizeof(unsigned) * n);
    if (!a) return 2;
    for (long i = 0; i < n; i++) a[i] = rnd();
    qsort_u(a, 0, n - 1);
    unsigned long long chk = 0;
    for (long i = 1; i < n; i++) if (a[i - 1] > a[i]) return 3;   /* self-check */
    for (long q = 0; q < n / 2; q++) {
        long r = bsearch_u(a, n, a[(unsigned long long)rnd() % n] + (rnd() & 1));
        chk = chk * 1099511628211ULL + (unsigned long long)(r + 1);
    }
    unsigned long long steps = 0;
    for (unsigned long long s = 1; s < 400000ULL; s++) {
        unsigned long long x = s;
        while (x != 1) { x = (x & 1) ? 3 * x + 1 : x >> 1; steps++; }
    }
    printf("%llu %llu\n", chk, steps);
    free(a);
    return 0;
}
