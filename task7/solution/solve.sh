#!/usr/bin/env bash
# Oracle entrypoint. Runs the reference adjudicator, which reads only /app/data
# and writes /app/answer.json.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${HERE}/solve.py"
