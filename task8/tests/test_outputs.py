"""Verifier for dynamo/reproducible-release-bundle.

There is no answer key. Reproducibility is a property of what the build does,
not of a particular patch, so the verifier builds the agent's tree itself and
grades the result. Many different correct Makefiles pass; the only thing that
matters is whether two rebuilds under different conditions agree byte for byte.

Four things are checked, and all four are required.

  reproducible   the bundle built under environment A is byte-identical to the
                 one built under environment B
  input-sensitive a third build, from a tree with one source string changed,
                 produces a DIFFERENT bundle -- which is what stops a solution
                 that simply freezes, empties or pre-bakes the artifact from
                 satisfying the first check trivially
  complete       the bundle still contains everything a release must, and its
                 binary still carries debug information
  working        the packaged CLI still behaves as it did

The environment values below are deliberately not the ones stated in the
instruction. The instruction gives the standard and names the classes that
vary, because that is the specification a rebuilder works to; a solution that
defends against the class passes anywhere, and one that was tuned until a
locally observed difference went quiet does not.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

APP = "/app"

# Everything the build produces. Stripped from each copy before building, so a
# tree carrying stale outputs -- or a bundle committed by hand -- is rebuilt
# from source rather than graded as it stands.
GENERATED = ("build", "stage", "dist", os.path.join("src", "buildinfo.h"))

REQUIRED = (
    "bin/greet", "lib/libgreet.a", "include/greet.h", "share/manifest.txt",
    "VERSION", "CHANGELOG.md",
    "share/docs/API-index.txt", "share/docs/Changelog.txt",
    "share/docs/INSTALL", "share/docs/_meta.txt", "share/docs/api.txt",
    "share/docs/changelog-old.txt", "share/docs/install-notes.txt",
)

ENVS = {
    "A": dict(sub="opt/pkg/greet", when="2026-01-23 04:05:06",
              mtime="2026-01-20 00:00:00", lang="C", tz="UTC", umask="022",
              user="release", host="forge-01", order="forward", uid=0),
    "B": dict(sub="home/ci/agents/7/checkout/work/greet",
              when="2031-11-02 19:58:41", mtime="2031-10-28 00:00:00",
              lang="en_US.UTF-8", tz="Australia/Adelaide", umask="002",
              user="rebuild", host="verifier-99", order="reverse", uid=1001),
}
ENVS["C"] = dict(ENVS["A"], sub="opt/pkg/greet-c")


def _materialise(src, dest, order, mtime):
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


def _build(name, root, edit=None):
    """Build /app under environment `name`; return (bundle path, work dir)."""
    e = ENVS[name]
    work = os.path.join(root, e["sub"])
    _materialise(APP, work, e["order"], e["mtime"])
    if edit:
        edit(work)

    env = dict(os.environ)
    env.update(LANG=e["lang"], LC_ALL=e["lang"], TZ=e["tz"], USER=e["user"],
               LOGNAME=e["user"], HOSTNAME=e["host"], HOME=root)
    env.pop("SOURCE_DATE_EPOCH", None)

    drop = ""
    if e["uid"]:
        subprocess.run(["chown", "-R", "%d:%d" % (e["uid"], e["uid"]), root],
                       check=True)
        drop = "setpriv --reuid=%d --regid=%d --clear-groups " % (e["uid"],
                                                                  e["uid"])
    # A private UTS namespace so the machine name really differs. If the
    # sandbox forbids it the build still runs, just without that one axis.
    inner = ("cd %s && umask %s && exec %sfaketime -f '@%s' make -s all"
             % (work, e["umask"], drop, e["when"]))
    script = "hostname %s 2>/dev/null; %s" % (e["host"], inner)
    argv = ["unshare", "-u", "--", "sh", "-c", script]
    r = subprocess.run(argv, env=env, capture_output=True, text=True)
    if r.returncode != 0 and "unshare" in (r.stderr or ""):
        r = subprocess.run(["sh", "-c", inner], env=env, capture_output=True,
                           text=True)
    assert r.returncode == 0, (
        "the build failed under environment %s:\n%s\n%s"
        % (name, r.stdout[-2000:], r.stderr[-2000:]))

    dist = os.path.join(work, "dist")
    assert os.path.isdir(dist), (
        "environment %s: the build produced no dist/ directory" % name)
    found = sorted(f for f in os.listdir(dist) if f.endswith(".tar.gz"))
    assert len(found) == 1, (
        "environment %s: expected exactly one .tar.gz in dist/, found %r"
        % (name, found))
    return os.path.join(dist, found[0]), work


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _differences(a, b):
    """Where two bundles diverge, in terms a build engineer can act on."""
    out = []
    with open(a, "rb") as f:
        ha = f.read(10)
    with open(b, "rb") as f:
        hb = f.read(10)
    if ha != hb:
        out.append("the gzip header differs (it carries the input file's name "
                   "and mtime): %s vs %s" % (ha.hex(), hb.hex()))

    def members(path):
        d = {}
        with tarfile.open(path, "r:gz") as t:
            for m in t.getmembers():
                body = ""
                if m.isfile():
                    body = hashlib.sha256(
                        t.extractfile(m).read()).hexdigest()[:12]
                d[m.name] = dict(mtime=m.mtime, mode=oct(m.mode), uid=m.uid,
                                 gid=m.gid, uname=m.uname, gname=m.gname,
                                 body=body)
        return d

    ma, mb = members(a), members(b)
    if list(ma) != list(mb):
        out.append("the members are written in a different order"
                   if sorted(ma) == sorted(mb) else
                   "the member sets differ: only in A %s, only in B %s"
                   % (sorted(set(ma) - set(mb)), sorted(set(mb) - set(ma))))
    for name in sorted(set(ma) & set(mb)):
        for field in ("mtime", "mode", "uid", "gid", "uname", "gname", "body"):
            if ma[name][field] != mb[name][field]:
                out.append("%s: %s %s != %s"
                           % (name, field, ma[name][field], mb[name][field]))
    return out[:12]


def _change_a_source(work):
    """The edit environment C builds with: one string, in one source file."""
    path = os.path.join(work, "src", "greet.c")
    with open(path) as f:
        s = f.read()
    assert '"Hello, %s!"' in s, (
        "src/greet.c no longer contains the salutation template, so the build "
        "cannot be shown to depend on its sources")
    with open(path, "w") as f:
        f.write(s.replace('"Hello, %s!"', '"Greetings, %s!"', 1))


_CACHE = {}


def _bundles():
    """Build all three environments once, and reuse them across the tests."""
    if not _CACHE:
        root = tempfile.mkdtemp(prefix="verify-")
        _CACHE["root"] = root
        _CACHE["A"] = _build("A", root)
        _CACHE["B"] = _build("B", root)
        _CACHE["C"] = _build("C", root, edit=_change_a_source)
    return _CACHE


def test_bundle_is_reproducible():
    """The same source, built under different conditions, is the same bytes."""
    c = _bundles()
    a, b = c["A"][0], c["B"][0]
    if _sha(a) != _sha(b):
        detail = "\n  ".join(_differences(a, b))
        raise AssertionError(
            "the two builds produced different bundles.\n"
            "  A %s\n  B %s\n  %s" % (_sha(a), _sha(b), detail))


def test_build_depends_on_its_sources():
    """Changing a source must change the bundle: a frozen or pre-baked
    artifact is byte-identical for the wrong reason."""
    c = _bundles()
    a, third = c["A"][0], c["C"][0]
    assert _sha(a) != _sha(third), (
        "changing the salutation in src/greet.c left the bundle byte-identical "
        "(%s), so it is not being produced from the sources" % _sha(a))


def test_bundle_is_complete():
    """Everything a release must carry is still in it, and the binary still
    carries debug information."""
    c = _bundles()
    with tarfile.open(c["A"][0], "r:gz") as t:
        names = t.getnames()
    roots = set(n.split("/")[0] for n in names)
    assert len(roots) == 1, (
        "the bundle should unpack into exactly one directory, found %s"
        % sorted(roots))
    prefix = roots.pop()
    assert re.fullmatch(r"greet-\d+\.\d+\.\d+", prefix), (
        "the bundle's top-level directory should be greet-VERSION, found %r"
        % prefix)
    missing = [r for r in REQUIRED if "%s/%s" % (prefix, r) not in names]
    assert not missing, "the bundle is missing %s" % ", ".join(missing)

    out = tempfile.mkdtemp(prefix="unpack-")
    with tarfile.open(c["A"][0], "r:gz") as t:
        t.extractall(out)
    binary = os.path.join(out, prefix, "bin", "greet")
    sections = subprocess.run(["readelf", "-S", "-W", binary],
                              capture_output=True, text=True).stdout
    assert ".debug_info" in sections, (
        "the packaged binary has no .debug_info section; the release ships "
        "debuggable binaries, so stripping debug information is not a way to "
        "keep the build path out of the artifact")
    _CACHE["unpacked"] = os.path.join(out, prefix)


def test_packaged_cli_still_works():
    """The artifact's behaviour is unchanged, including the version banner,
    whose date comes from the release rather than from the build clock."""
    test_bundle_is_complete()
    binary = os.path.join(_CACHE["unpacked"], "bin", "greet")
    for args, want in ((["--version"], "greet 1.4.2 (built 2024-11-05)"),
                       (["Ada"], "Hello, Ada!"),
                       (["--upper", "Ada"], "HELLO, ADA!")):
        r = subprocess.run([binary] + args, capture_output=True, text=True)
        assert r.returncode == 0, (
            "greet %s exited %d" % (" ".join(args), r.returncode))
        assert r.stdout.strip() == want, (
            "greet %s printed %r, expected %r"
            % (" ".join(args), r.stdout.strip(), want))
