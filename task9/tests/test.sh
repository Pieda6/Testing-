#!/usr/bin/env bash
# Verifier entrypoint. Runs plain pytest (all deps already baked into the image)
# and writes reward.txt (1/0) and ctrf.json under /logs/verifier/.
#
# Hardened so that a submission cannot grade itself. The agent may write
# anywhere under /app, and the verifier is invoked with /app as its working
# directory, so every path by which agent-written files could reach the
# verifier's Python process is closed here:
#
#   * we run from a fresh directory of our own making, never from /app, so
#     nothing the agent wrote is in the working directory at all;
#   * python runs with -I, which keeps the working directory and the user site
#     directory off sys.path and ignores every PYTHON* variable, so a file named
#     json.py or pytest.py cannot shadow the module the verifier imports;
#   * the config file and the conftest cut-off are pinned to this directory, so
#     a pytest.ini or a conftest.py planted anywhere above it cannot inject a
#     plugin or get executed inside the verifier;
#   * the cache provider is off, so pytest writes nothing outside /logs;
#   * the two output files are removed before being written, so a symlink left
#     in their place is deleted rather than followed, and each is written whole
#     and then moved into position.
#
# The compiler the verifier drives is invoked by absolute path from the test
# module, and the harness runs with a PATH of its own, so a wrapper script left
# on the agent's PATH is not consulted either.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/ctrf.json

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
cd "${WORK}" || exit 1

python3 -I -m pytest "${HERE}/test_outputs.py" -rA \
    -c "${HERE}/pytest.ini" \
    --confcutdir="${HERE}" \
    -p no:cacheprovider \
    --ctrf "${WORK}/ctrf.json"
rc=$?

[ -f "${WORK}/ctrf.json" ] && mv "${WORK}/ctrf.json" /logs/verifier/ctrf.json

if [ "${rc}" -eq 0 ]; then
    printf '1' > "${WORK}/reward.txt"
else
    printf '0' > "${WORK}/reward.txt"
fi
mv "${WORK}/reward.txt" /logs/verifier/reward.txt

exit 0
