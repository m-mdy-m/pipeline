#include <stdio.h>

static int add(int a, int b) { return a + b; }

int main(void) {
    if (add(2, 3) != 5) {
        fputs("bad sum\n", stderr);
        return 1;
    }
    puts("ok");
    return 0;
}
