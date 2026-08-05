# dynamo/reproducible-release-bundle

A small C project whose `Makefile` packages `dist/greet-1.4.2.tar.gz`. The build
is not reproducible: eleven separate leaks let the surrounding machine, clock,
locale, umask, account and filesystem into the artifact. Make the bundle
bit-identical for any rebuilder without changing what it does.

The project is synthetic. Every defect planted in it is a real, documented entry
from the catalogue the Reproducible Builds project maintains.

## Layout

    task.toml                            labels, budgets, and the three explanations
    instruction.md                       what the agent is given and asked for
    environment/Dockerfile               the single image, agent and verifier
    environment/.dockerignore            keeps all but project/ out of the build
    environment/project/                 the project, COPYed to /app
    solution/solve.sh                    oracle: rewrites the three build files
    tests/test.sh                        verifier entrypoint, hardened
    tests/pytest.ini                     pinned config, so rootdir cannot be hijacked
    tests/test_outputs.py                the four graded criteria

There is no `expected.json`, and nothing is held out in `tests/` except the
environment values. Correctness is a property of what the build does, so the
verifier builds the agent's tree itself; many different correct Makefiles pass.

## What makes it hard

- **The definition is the trap.** "Reproducible" is popularly understood as
  *the same bytes twice in the same place*. The standard is *the same bytes in a
  different directory, at a different time, from a checkout whose timestamps
  have all changed, under a different locale, timezone, umask and account, on a
  filesystem that returns directory entries in a different order*. A solver that
  builds twice in one container, sees identical output and stops has produced a
  confident, finished, wrong answer.
- **Eleven leaks, all load-bearing.** Reverting any single fix with the other
  ten in place makes the two rebuilds differ — measured, not assumed. Under
  all-or-nothing grading, finding ten of eleven scores the same as finding none.
- **The archive layer is the easy half.** `tar` and `gzip` flags are what a
  search turns up first and they address nothing embedded during compilation or
  generation: the build path in the debug info, `__DATE__` and `__TIME__`, the
  header's date, the header's record of who built it and where.
- **`SOURCE_DATE_EPOCH` is a convention, not a mechanism.** `tar`, `gzip` and
  `ar` ignore it. It has to be threaded through by hand.
- **The graded environments are held out.** The instruction names the classes
  that vary, because that is the professional standard and withholding it would
  make the task a guessing game about the verifier. The values are not given, so
  a build tuned until one locally observed difference went quiet does not pass.

## The eleven leaks

    archive        staged files' mtimes
    archive        the building account as owner/group/uname/gname
    archive        permission bits following the caller's umask
    archive        member order following the caller's collation
    package        gzip embedding the input file's name and mtime
    compile        the absolute build directory, via the debug info
    compile        __DATE__ and __TIME__
    generate       the header's date taken from the clock
    generate       the header recording the user and the machine name
    generate       the manifest's sort following the caller's collation
    build          the epoch derived from the clock rather than from the tree

`ar` is deliberately absent. binutils on this base image is built with
`--enable-deterministic-archives`, so `ar rcs` already zeroes member timestamps
and passing `D` changes nothing. The mutation battery caught it as inert and it
was dropped rather than contrived into existence with `ar rcsU`.

## Verification

Three builds, all deterministic, none visible to the agent. **A**: shallow path,
C locale, UTC, umask 022, fixed clock, root. **B**: deep path, `en_US.UTF-8`,
Australia/Adelaide, umask 002, a clock nearly six years later, an unprivileged
account in a private UTS namespace, source timestamps from another month, and a
tree materialised in the opposite order. **C**: A again, against a tree with one
string in `src/greet.c` altered.

Four criteria, all required:

1. `sha256(A) == sha256(B)` — byte equality, no tolerance.
2. `sha256(C) != sha256(A)` — the build still depends on its sources.
3. The bundle unpacks to one `greet-VERSION/` with all thirteen members, and the
   binary keeps `.debug_info`.
4. The packaged CLI still prints the expected banner, salutation and uppercase
   salutation.

Criteria 2–4 are what separate a genuine fix from the degenerate ones: an empty
or frozen bundle satisfies criterion 1 trivially.

Every copy has `build/`, `stage/`, `dist/` and `src/buildinfo.h` removed before
building. An early version did not, and reported the *unmodified* project as
perfectly reproducible, because `make` found nothing to do and both "builds"
were one stale tarball.

## Measured

    reference solution                             reward 1, about a second
    the project as shipped                         0
    each of eleven single-fix regressions          0
    debug information stripped                     0
    docs dropped from the bundle                   0
    the CLI's behaviour changed                    0
    an empty bundle                                0
    the build does nothing                         0
    a pre-baked bundle copied into place           0

The last one fails on criterion 2 alone and passes the other three, which is
exactly the case that criterion exists for.

## Dev tooling (not shipped)

Lives in `dev8/`, outside this directory:

    differ.py      builds twice under differing conditions; reports what diverges
    mutations.py   reverts each fix alone; requires every one to break the build
    controls.py    runs the real entrypoint against the oracle and the cheats

## A note on the instrument

`faketime` breaks `date -u`: with `TZ` set, its `gmtime` hook applies the local
offset, so a correct `date -u -d @EPOCH` returns local time. An earlier design
had the generated header carrying a time-of-day field, which meant the most
natural correct fix would have been graded irreproducible — a false negative
that would have looked like a verifier bug. The header now carries only a date,
which is `TZ`-robust, so no correct fix can trip on the tool.
