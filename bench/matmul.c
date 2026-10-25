/* Dense matrix multiply (naive ijk). Regular loops: responds strongly to
 * vectorization, unrolling, and loop passes. Usage: ./matmul [N]  (default 640) */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 640;
    double *A = malloc(sizeof(double) * (size_t)n * n);
    double *B = malloc(sizeof(double) * (size_t)n * n);
    double *C = malloc(sizeof(double) * (size_t)n * n);
    if (!A || !B || !C) return 2;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            A[(size_t)i * n + j] = (double)((i * 7 + j * 3) % 11);
            B[(size_t)i * n + j] = (double)((i * 5 + j * 2) % 13);
        }
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            double s = 0.0;
            for (int k = 0; k < n; k++) s += A[(size_t)i * n + k] * B[(size_t)k * n + j];
            C[(size_t)i * n + j] = s;
        }
    /* integer-valued doubles keep every sum exact, so output is identical across builds */
    long long chk = 0;
    for (size_t idx = 0; idx < (size_t)n * n; idx++) chk = (chk * 31 + (long long)C[idx]) % 1000000007LL;
    printf("%lld\n", chk);
    free(A); free(B); free(C);
    return 0;
}
