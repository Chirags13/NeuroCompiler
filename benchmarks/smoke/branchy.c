#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 3000000;
    if (n < 1000 || n > 50000000) return 2;

    unsigned long long acc = 0;
    for (int i = 1; i <= n; ++i) {
        if ((i % 3) == 0) acc += (unsigned long long)i * 17;
        else if ((i % 5) == 0) acc ^= (unsigned long long)i * 31;
        else if ((i & 1) == 0) acc += (unsigned long long)(i >> 1);
        else acc ^= (unsigned long long)(i * 7);
    }

    printf("%llu\n", acc);
    return 0;
}
