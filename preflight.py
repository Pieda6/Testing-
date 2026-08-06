"""Pre-flight check of a task directory against the mechanical parts of the
Dynamo rubric and the diversity taxonomy.

Run this before uploading. It cannot judge whether a task is hard or novel --
that is what the review model is for -- but every criterion that can be decided
by reading the files is checked here, and those are the ones that have actually
cost us runs: a stray upload link on line 1, an out-of-vocabulary label, a field
Harbor does not recognise, ground truth reachable from the agent image.

    python3 preflight.py task7
"""
import os
import re
import sys
import tomllib

OBJECTIVES = set("""implement fix configure analyze transform validate optimize
migrate refactor test debug build_or_package deploy_or_operate
recover_or_repair_artifact generate compare_or_select secure_or_harden
automate_workflow""".split())

ARTIFACTS = set("""codebase single_script_or_program test_suite_or_benchmark
build_system_or_package_metadata configuration_file shell_environment
service_or_daemon container_or_virtual_environment database_or_structured_store
dataset_or_tabular_file text_or_log_file document_or_report
archive_or_compressed_artifact binary_executable_or_library media_artifact
model_or_checkpoint hardware_or_firmware_artifact
network_endpoint_or_protocol_artifact
repository_history_or_version_control_state security_artifact
mathematical_or_scientific_model generated_output_artifact""".split())

CATEGORIES = {
    "software_engineering", "debugging_and_repair",
    "build_dependency_and_release_management",
    "systems_infrastructure_and_operations", "data_processing_and_etl",
    "data_querying_and_databases", "data_science_and_reporting",
    "machine_learning_and_ai", "model_training_and_ml_infrastructure",
    "security", "scientific_computing_and_domain_science",
    "mathematics_and_formal_reasoning",
    "hardware_embedded_and_low_level_systems", "file_and_media_operations",
    "games_puzzles_and_interactive_simulation",
    "regulated_knowledge_work_and_business_operations",
}

META_FIELDS = {"category", "subcategory", "task_objective", "artifact_type",
               "expert_time_estimate_hours", "model_tested", "agent_tested",
               "avg_at_8", "difficulty_explanation", "solution_explanation",
               "verification_explanation", "author_name", "author_email",
               "author_organization", "domain", "tags"}
ROOT_FIELDS = {"schema_version", "task", "metadata", "verifier", "agent",
               "environment", "solution", "source", "artifacts"}
SECTION_FIELDS = {
    "verifier": {"timeout_sec", "env", "user", "environment_mode",
                 "environment"},
    "agent": {"timeout_sec", "user"},
    "environment": {"build_timeout_sec", "docker_image", "cpus", "memory_mb",
                    "storage_mb", "gpus", "gpu_types", "allow_internet", "env",
                    "skills_dir", "mcp_servers", "healthcheck"},
    "solution": {"env"},
}

FAILS, NOTES = [], []


def fail(criterion, msg):
    FAILS.append("%-28s %s" % (criterion, msg))


def note(criterion, msg):
    NOTES.append("%-28s %s" % (criterion, msg))


def norm(s):
    return s.lower().replace(" ", "_").replace("-", "_")


def read(path):
    with open(path) as f:
        return f.read()


def check_markdown(root):
    """instruction_concision, typos: the failure modes that have actually bitten."""
    for rel in ["instruction.md"] + [
            os.path.join(dp, fn)[len(root) + 1:]
            for dp, _dn, fns in os.walk(os.path.join(root, "environment"))
            for fn in fns if fn.endswith(".md")]:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        text = read(path)
        first = text.splitlines()[0] if text.splitlines() else ""
        if rel == "instruction.md":
            # The upstream static check rejects any path in instruction.md that
            # is not absolute under /app, and rejects it as a FAIL. It caught
            # three on task8 and cost a review round-trip, so this is a failure
            # here too rather than a note. Paths inside an archive or another
            # container have no /app form -- name their parts separately.
            relpaths = sorted(set(
                t for t in re.findall(r"`([^`]+)`", text)
                if "/" in t and not t.startswith(("/", "http", "$"))))
            if relpaths:
                fail("instruction_absolute_paths",
                     "relative paths (must be absolute under /app, or reworded "
                     "if they name something inside an archive): %s"
                     % ", ".join(relpaths))
        if "user-attachments" in text:
            fail("instruction_concision",
                 "%s carries a GitHub upload link (drag-and-drop artifact); "
                 "first line is %r" % (rel, first[:60]))
        if re.search(r"you have \d+ seconds|time budget|within \d+ minutes",
                     text, re.I):
            fail("instruction_concision", "%s states a time budget" % rel)

    path = os.path.join(root, "instruction.md")
    if os.path.exists(path):
        text = read(path)
        # a bare filename is fine once its absolute path has been given -- both
        # tasks that passed every criterion do exactly that
        absolute = set(re.findall(r"`(/[\w./-]+)`", text))
        for m in re.finditer(r"`([^`\n]+)`", text):
            tok = m.group(1)
            if not re.match(r"^(?:\./)?[\w./-]+\.(json|csv|md|txt|py|db)$", tok):
                continue
            if tok.startswith("/"):
                continue
            if any(a.endswith("/" + tok) for a in absolute):
                continue
            note("instruction_concision",
                 "instruction.md names %r and never gives its absolute path"
                 % tok)


def check_toml(root):
    path = os.path.join(root, "task.toml")
    if not os.path.exists(path):
        fail("task_toml_schema", "no task.toml")
        return None
    with open(path, "rb") as f:
        doc = tomllib.load(f)

    extra = set(doc) - ROOT_FIELDS
    if extra:
        fail("task_toml_schema", "unrecognised root field(s): %s"
             % ", ".join(sorted(extra)))
    for sec, allowed in SECTION_FIELDS.items():
        bad = set(doc.get(sec, {})) - allowed
        if bad:
            fail("task_toml_schema", "unrecognised [%s] field(s): %s"
                 % (sec, ", ".join(sorted(bad))))

    name = doc.get("task", {}).get("name")
    if not name:
        fail("task_name", "[task].name missing")
    else:
        if "/" not in name:
            fail("task_name", "%r lacks the org/ prefix" % name)
        else:
            tail = name.split("/", 1)[1]
            if len(tail.split("-")) > 3:
                fail("task_name", "%r name part is more than 3 words" % tail)
            if tail != tail.lower():
                fail("task_name", "%r is not kebab-case" % tail)
    for k in set(doc.get("task", {})) - {"name", "description"}:
        note("task_toml_schema",
             "[task].%s is not in the rubric's enumerated field list" % k)

    m = doc.get("metadata", {})
    bad = set(m) - META_FIELDS
    if bad:
        fail("task_toml_schema", "unrecognised [metadata] field(s): %s"
             % ", ".join(sorted(bad)))
    if norm(m.get("category", "")) not in CATEGORIES:
        fail("accurate_taxonomy_labels",
             "category %r is not in the taxonomy" % m.get("category"))
    for v in m.get("task_objective", []):
        if norm(v) not in OBJECTIVES:
            fail("accurate_taxonomy_labels", "task_objective %r invalid" % v)
    for v in m.get("artifact_type", []):
        if norm(v) not in ARTIFACTS:
            fail("accurate_taxonomy_labels", "artifact_type %r invalid" % v)
    if not m.get("expert_time_estimate_hours"):
        fail("expert_time_estimate", "0 or missing")
    for k in ("difficulty_explanation", "solution_explanation",
              "verification_explanation"):
        if not m.get(k, "").strip():
            fail(k + "_quality", "empty")
    if re.search(r"pass@\d|pass rate|benchmark score|the model (solved|failed)",
                 m.get("difficulty_explanation", ""), re.I):
        fail("difficulty_explanation_quality",
             "cites experimental results rather than intrinsic difficulty")
    if "artifacts" not in doc:
        fail("verifier_configuration", "no top-level `artifacts`")
    elif any(k in doc.get("verifier", {}) for k in ("artifacts",)):
        fail("verifier_configuration", "`artifacts` nested under [verifier]")
    return doc


def check_docker(root):
    path = os.path.join(root, "environment", "Dockerfile")
    if not os.path.exists(path):
        note("verifier_configuration", "no environment/Dockerfile (non-Harbor?)")
        return
    text = read(path)
    for pat, msg in (
            (r"^\s*COPY\s+.*\bsolution\b", "COPYs solution/ into the image"),
            (r"^\s*COPY\s+.*\btests\b", "COPYs tests/ into the image")):
        if re.search(pat, text, re.M):
            fail("environment_hygiene", msg)
    if "apt-get install" in text:
        if "apt-get update" not in text:
            fail("environment_hygiene", "apt-get install without apt-get update")
        if "rm -rf /var/lib/apt/lists" not in text:
            fail("environment_hygiene", "apt lists not cleaned")
    for pkg in re.findall(r"pip install[^\n]*", text):
        for tok in re.findall(r"\b([A-Za-z][\w.-]+)(?:==|\s|$)", pkg):
            if tok.startswith(("no-", "break-", "--")) or tok in (
                    "pip", "install", "RUN", "rm", "rf", "apt", "get", "python3"):
                continue                      # flags, not packages
            if tok + "==" not in pkg:
                note("environment_hygiene", "pip package %r looks unpinned" % tok)

    sh = os.path.join(root, "tests", "test.sh")
    if os.path.exists(sh):
        t = read(sh)
        for pat in (r"apt-get", r"pip install", r"curl[^\n]*\|\s*sh", r"uvx"):
            if re.search(pat, t):
                fail("verifier_configuration",
                     "tests/test.sh installs tooling at verify time (%s)" % pat)


def check_anti_cheat(root):
    env = os.path.join(root, "environment")
    for dp, _dn, fns in os.walk(env):
        for fn in fns:
            if fn in ("expected.json", "truth.json", "answer.json",
                      "solution.json"):
                fail("anti_cheat", "%s is reachable by the agent"
                     % os.path.join(dp, fn)[len(root) + 1:])
    tests = os.path.join(root, "tests")
    if os.path.isdir(tests) and not any(
            f.startswith("expected") for f in os.listdir(tests)):
        note("anti_cheat", "no expected.* in tests/ -- is ground truth held out?")


def check_files(root):
    junk = []
    for dp, dn, fns in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for fn in fns:
            if fn.endswith((".pyc", ".bak", ".orig", ".swp", ".tmp")) or \
                    fn in (".DS_Store",) or fn.startswith("scratch"):
                junk.append(os.path.join(dp, fn)[len(root) + 1:])
    if junk:
        fail("no_extraneous_files", "cruft: %s" % ", ".join(junk))
    if os.path.exists(os.path.join(root, "README.md")):
        note("task_readme",
             "a README is present and will be graded; it is optional, and "
             "must add reviewer context without duplicating task content")


def main(root):
    check_markdown(root)
    check_toml(root)
    check_docker(root)
    check_anti_cheat(root)
    check_files(root)

    print("pre-flight: %s" % root)
    if FAILS:
        print("\nFAIL")
        for f in FAILS:
            print("  " + f)
    else:
        print("\nno mechanical failures")
    if NOTES:
        print("\nnotes")
        for n in NOTES:
            print("  " + n)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "task7"))
