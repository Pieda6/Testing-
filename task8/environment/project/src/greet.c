#include <stdio.h>
#include <string.h>
#include "greet.h"

static const char TEMPLATE[] = "Hello, %s!";

const char *greet_template(void)
{
    return TEMPLATE;
}

int greet_format(char *out, unsigned long n, const char *who, int upper)
{
    int wrote = snprintf(out, n, TEMPLATE, who);
    if (upper)
        greet_upcase(out);
    return wrote;
}
