#include <stdio.h>
#include <string.h>
#include "greet.h"
#include "buildinfo.h"

#define VERSION "1.4.2"

static void usage(void)
{
    fputs("usage: greet [--upper] NAME\n"
          "       greet --version\n"
          "       greet --buildinfo\n", stderr);
}

int main(int argc, char **argv)
{
    char line[256];
    int upper = 0, i;
    const char *who = 0;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--version")) {
            printf("greet %s (built %s)\n", VERSION, BUILD_DATE);
            return 0;
        }
        if (!strcmp(argv[i], "--buildinfo")) {
            printf("user %s\nhost %s\ncompiled %s %s\n",
                   BUILD_USER, BUILD_HOST, __DATE__, __TIME__);
            return 0;
        }
        if (!strcmp(argv[i], "--upper")) {
            upper = 1;
            continue;
        }
        if (argv[i][0] == '-') {
            usage();
            return 2;
        }
        who = argv[i];
    }
    if (!who) {
        usage();
        return 2;
    }
    greet_format(line, sizeof line, who, upper);
    puts(line);
    return 0;
}
