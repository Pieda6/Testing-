#!/usr/bin/env bash
# Golden solution entrypoint for dynamo/exec-calendar-triage.
# Real logic lives in solve.py (applies the booking policy in order and takes
# the earliest feasible slot for each request); this script just invokes it.
# No seed, generator, or answer key is consulted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${HERE}/solve.py"
