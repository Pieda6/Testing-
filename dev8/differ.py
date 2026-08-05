"""Build the project twice under deliberately different conditions and say
whether the release bundle came out bit-identical -- and if not, where.

This is the instrument the whole task is measured with, so it is written once
here and the verifier uses the same construction. Each environment varies an
axis that a real rebuilder varies:

    build path        the tree is unpacked somewhere else
    wall clock        the rebuild happens years later
    file mtimes       the checkout is fresh, so every source file is newer
    locale            the rebuilder's shell is not in the C locale
    timezone          nor in UTC
    umask             nor using the same default permissions
    user and host     nor on the same machine, under the same account
    directory order   nor with the files laid down in the same order

Nothing here is exotic. Every one of these is on the Reproducible Builds
project's list of things that break real packages.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "..", "task8", "environment", "project")

ENVS = {
    "A": dict(root="/tmp/rb/a", sub="greet",
              when="2025-03-04 09:12:33", mtime="2025-03-01 00:00:00",
              lang="C", tz="UTC", umask="022",
              user="alice", host="build-a", order="forward", uid=0),
    "B": dict(root="/tmp/rb/b", sub="srv/releases/ci/workspace/greet",
              when="2028-07-19 22:41:05", mtime="2028-07-01 00:00:00",
              lang="en_US.UTF-8", tz="Asia/Tokyo", umask="002",
              user="bob", host="rebuilder-b", order="reverse", uid=1000),
}


# Everything the build itself produces. Stripped from the copy before building,
# so that a tree carrying stale outputs -- or a pre-baked bundle committed by
# hand -- is rebuilt from source rather than graded as it stands.
GENERATED = ("build", "stage", "dist", os.path.join("src", "buildinfo.h"))


def materialise(src, dest, order, mtime):
    """Lay the tree down under `dest`, creating entries in `order` so that the
    directories' readdir order differs between environments."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    for cur, dirs, files in os.walk(src):
        rel = os.path.relpath(cur, src)
        if any(rel == g or rel.startswith(g + os.sep) for g in GENERATED):
            dirs[:] = []
            continue
        out = os.path.normpath(os.path.join(dest, rel))
        os.makedirs(out, exist_ok=True)
        dirs.sort(reverse=(order == "reverse"))
        for name in sorted(files, reverse=(order == "reverse")):
            if os.path.normpath(os.path.join(rel, name)) in GENERATED:
                continue
            shutil.copy2(os.path.join(cur, name), os.path.join(out, name))
    subprocess.run(["find", dest, "-exec", "touch", "-d", mtime, "{}", "+"],
                   check=True)


def build(name, src=PROJECT, extra=None):
    """Materialise and build under environment `name`; return the bundle path."""
    e = ENVS[name]
    work = os.path.join(e["root"], e["sub"])
    materialise(src, work, e["order"], e["mtime"])
    if extra:
        extra(work)
    env = dict(os.environ)
    env.update(LANG=e["lang"], LC_ALL=e["lang"], TZ=e["tz"], USER=e["user"],
               LOGNAME=e["user"], HOSTNAME=e["host"], HOME=e["root"])
    env.pop("SOURCE_DATE_EPOCH", None)
    drop = ""
    if e["uid"]:
        subprocess.run(["chown", "-R", "%d:%d" % (e["uid"], e["uid"]), work],
                       check=True)
        drop = "setpriv --reuid=%d --regid=%d --clear-groups " % (e["uid"],
                                                                  e["uid"])
    script = ("hostname %s && cd %s && umask %s && "
              "exec %sfaketime -f '@%s' make -s all"
              % (e["host"], work, e["umask"], drop, e["when"]))
    r = subprocess.run(["unshare", "-u", "--", "sh", "-c", script],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("build %s failed:\n%s\n%s\n" % (name, r.stdout,
                                                         r.stderr))
        return None
    dist = os.path.join(work, "dist")
    bundles = [f for f in os.listdir(dist) if f.endswith(".tar.gz")]
    if len(bundles) != 1:
        sys.stderr.write("build %s produced %d bundles\n" % (name,
                                                             len(bundles)))
        return None
    return os.path.join(dist, bundles[0])


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def members(path):
    """Every member's metadata and content digest, keyed by name."""
    out = {}
    with tarfile.open(path, "r:gz") as t:
        for m in t.getmembers():
            body = ""
            if m.isfile():
                body = hashlib.sha256(t.extractfile(m).read()).hexdigest()[:12]
            out[m.name] = dict(order=len(out), mtime=m.mtime, mode=oct(m.mode),
                               uid=m.uid, gid=m.gid, uname=m.uname,
                               gname=m.gname, size=m.size, body=body)
    return out


def report(a, b):
    """What differs between two bundles, as a list of human-readable lines."""
    lines = []
    with open(a, "rb") as f:
        ha = f.read(10)
    with open(b, "rb") as f:
        hb = f.read(10)
    if ha[:10] != hb[:10]:
        lines.append("gzip header differs: %s vs %s  (name and mtime fields)"
                     % (ha.hex(), hb.hex()))
    ma, mb = members(a), members(b)
    if list(ma) != list(mb):
        if sorted(ma) == sorted(mb):
            lines.append("member ORDER differs (first divergence at index %d)"
                         % next(i for i, (x, y) in
                                enumerate(zip(ma, mb)) if x != y))
        else:
            lines.append("member SET differs: only in A %s / only in B %s"
                         % (sorted(set(ma) - set(mb)), sorted(set(mb) - set(ma))))
    for name in sorted(set(ma) & set(mb)):
        x, y = ma[name], mb[name]
        for field in ("mtime", "mode", "uid", "gid", "uname", "gname", "body",
                      "size"):
            if x[field] != y[field]:
                lines.append("%-44s %-6s %s != %s"
                             % (name, field, x[field], y[field]))
    return lines


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else PROJECT
    a, b = build("A", src), build("B", src)
    if not a or not b:
        return 2
    if sha(a) == sha(b):
        print("REPRODUCIBLE  sha256 %s" % sha(a))
        return 0
    print("NOT reproducible")
    print("  A %s" % sha(a))
    print("  B %s" % sha(b))
    for line in report(a, b):
        print("   ", line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
