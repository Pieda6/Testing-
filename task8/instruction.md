`/app` holds the `greet` project: a small C library, a CLI that links it, and a
`Makefile` that packages a release bundle at `/app/dist/greet-1.4.2.tar.gz`.

The build is not reproducible. Rebuild it on another machine and you get
different bytes, so nobody can check that the published bundle really came from
this source. **Make the bundle bit-identical for any rebuilder.**

## What reproducible means here

Not "`make` twice in the same place and compare". A rebuilder starts from the
same sources somewhere else, later, on a different machine. Your build must
produce identical bytes regardless of

- the **directory** it is built in, at any depth,
- the **wall clock** at build time, whether that is today or years from now,
- the **modification times** of the source files, which a fresh checkout resets,
- the **locale** and the **timezone** of the shell that runs it,
- the **umask** in effect,
- the **account** — user, group, machine name — doing the building,
- the **order** the filesystem happens to return directory entries in.

Your work is graded by rebuilding `/app` twice under conditions that differ in
all of the above and comparing the two bundles byte for byte. The specific
values used are not given; a build that is reproducible only against the
particular differences you happened to test is not reproducible.

`faketime`, `setpriv`, `unshare` and the `en_US.UTF-8` locale are installed, so
you can vary every one of those conditions yourself.

## What must not change

The bundle is a release, and it still has to be one.

1. **It must still be built.** The graded rebuild also runs once against a tree
   with one source string altered, and that bundle must come out *different*.
   Freezing the artifact, emptying it, or committing a copy and installing that
   are all rejected.
2. **It must still contain everything.** The archive unpacks into a single
   top-level `greet-VERSION` directory, and inside it: `greet` under `bin`,
   `libgreet.a` under `lib`, `greet.h` under `include`, `manifest.txt` under
   `share`, all seven documentation files in the `docs` directory under
   `share`, and `VERSION` and `CHANGELOG.md` at the top.
3. **The binary must stay debuggable.** The packaged `greet` must keep its
   `.debug_info`. Discarding debug information is not an acceptable way to keep
   the build directory out of the artifact.
4. **The CLI must behave as it does now**, with one correction: the version
   banner currently reports the day it was compiled, which is exactly the sort
   of thing that must go. It must report the release date recorded in
   `/app/CHANGELOG.md` instead:

        $ greet --version
        greet 1.4.2 (built 2024-11-05)
        $ greet Ada
        Hello, Ada!
        $ greet --upper Ada
        HELLO, ADA!

## Working notes

Change whatever you need to under `/app` — the `Makefile`, the scripts in
`/app/tools`, the sources. Leave the project working: `make` from a clean tree
must build everything and produce the bundle, and `make clean` must still remove
what it made. Write nothing outside `/app`.

`/app/build`, `/app/stage`, `/app/dist` and `/app/src/buildinfo.h` are outputs,
not inputs. They
are removed before each graded rebuild, so anything you leave there is ignored.
