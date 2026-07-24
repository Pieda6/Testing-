#!/usr/bin/env bash
# Verifier entrypoint. Runs plain pytest (all deps already baked into the
# image) and writes reward.txt (1/0) and ctrf.json under /logs/verifier/.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /logs/verifier

python -m pytest "${HERE}/test_outputs.py" -v \
    --ctrf /logs/verifier/ctrf.json
rc=$?

if [ "${rc}" -eq 0 ]; then
    printf '1' > /logs/verifier/reward.txt
else
    printf '0' > /logs/verifier/reward.txt
fi

exit 0
