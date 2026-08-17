"""Every fix in the reference solution, reverted one at a time.

A planted source of irreproducibility is only worth planting if removing its
fix brings the build back down. Anything that survives its own reversion is an
inert rule: it is in the solution, it is described in the instruction, and it
costs the agent nothing to miss. This is the check that finds those.

Each entry below undoes exactly one fix in the solved tree and expects the two
environments to diverge again.
"""
import io
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import differ                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOLVE = os.path.join(HERE, "..", "task8", "solution", "solve.sh")
WORK = "/tmp/mut"

MUTATIONS = [
    ("the epoch comes from the clock again", "Makefile",
     "SOURCE_DATE_EPOCH := $(shell date -u -d '$(RELEASE_DATE) 00:00:00' +%s)",
     "SOURCE_DATE_EPOCH := $(shell date +%s)"),
    ("the epoch is no longer exported to the compiler", "Makefile",
     "\nexport SOURCE_DATE_EPOCH\n", "\n"),
    ("the build path is back in the debug info", "Makefile",
     " -ffile-prefix-map=$(CURDIR)=.", ""),
    # No `ar` entry: binutils on this base image is built with
    # --enable-deterministic-archives, so `ar rcs` already zeroes member
    # timestamps, uid and gid. Passing D changes nothing and reverting it
    # changes nothing -- measured, not assumed -- so no such source is planted.
    ("the archive member order follows the caller's locale", "Makefile",
     "find $(PREFIX) | LC_ALL=C sort", "find $(PREFIX) | sort"),
    ("the archive keeps the staged files' mtimes", "Makefile",
     "\t\t    --mtime=@$(SOURCE_DATE_EPOCH) \\\n", ""),
    ("the archive records the building account", "Makefile",
     "\t\t    --owner=0 --group=0 --numeric-owner \\\n", ""),
    ("permission bits follow the caller's umask", "Makefile",
     " \\\n\t\t    --mode=go-w", ""),
    ("gzip embeds the input name and mtime", "Makefile",
     "gzip -n -9", "gzip -9"),
    ("the header's date comes from the clock", "tools/gen-buildinfo.sh",
     'echo "#define BUILD_DATE \\"$(date -u -d "@$SOURCE_DATE_EPOCH" '
     '+%Y-%m-%d)\\""',
     'echo "#define BUILD_DATE \\"$(date +%Y-%m-%d)\\""'),
    ("the header records who built it and where", "tools/gen-buildinfo.sh",
     "echo '#define BUILD_USER \"reproducible\"'\n"
     "echo '#define BUILD_HOST \"reproducible\"'",
     'echo "#define BUILD_USER \\"${USER:-$(id -un)}\\""\n'
     'echo "#define BUILD_HOST \\"$(hostname)\\""'),
    ("the manifest's sort follows the caller's locale", "tools/gen-manifest.sh",
     "| LC_ALL=C sort |", "| sort |"),
]


def solved_tree(dest):
    """A fresh copy of the shipped project with the reference fix applied."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(differ.PROJECT, dest)
    script = io.open(SOLVE, encoding="utf-8").read().replace(
        "\ncd /app\n", "\ncd %s\n" % dest)
    subprocess.run(["bash", "-c", script], check=True)


def main():
    solved_tree(WORK)
    a, b = differ.build("A", WORK), differ.build("B", WORK)
    if not a or not b or differ.sha(a) != differ.sha(b):
        print("the reference solution is not reproducible; nothing to mutate")
        return 2
    print("reference solution reproducible: %s\n" % differ.sha(a)[:16])

    inert = []
    for label, rel, old, new in MUTATIONS:
        solved_tree(WORK)
        path = os.path.join(WORK, rel)
        s = io.open(path, encoding="utf-8").read()
        if old not in s:
            print("  %-52s COULD NOT APPLY (pattern missing in %s)"
                  % (label, rel))
            inert.append(label)
            continue
        io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))

        x, y = differ.build("A", WORK), differ.build("B", WORK)
        if x is None or y is None:
            print("  %-52s BUILD BROKE (not a difficulty signal)" % label)
            inert.append(label)
        elif differ.sha(x) == differ.sha(y):
            print("  %-52s INERT -- still reproducible" % label)
            inert.append(label)
        else:
            print("  %-52s breaks it" % label)

    print()
    if inert:
        print("%d of %d fixes are not load-bearing: %s"
              % (len(inert), len(MUTATIONS), "; ".join(inert)))
        return 1
    print("all %d fixes are load-bearing -- reverting any one of them alone "
          "makes the bundle differ" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
