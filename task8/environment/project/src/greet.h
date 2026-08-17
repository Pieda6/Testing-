#ifndef GREET_H
#define GREET_H

/* Write a salutation for `who` into `out` (at most `n` bytes, always
   NUL-terminated). Returns the number of bytes that would have been written. */
int greet_format(char *out, unsigned long n, const char *who, int upper);

/* The salutation template, without the name. */
const char *greet_template(void);

/* Uppercase `s` in place, ASCII only. */
void greet_upcase(char *s);

#endif
