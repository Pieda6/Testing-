#!/usr/bin/env bash
# Golden solution entrypoint for dynamo/legacy-tag-forge.
# Real logic lives in solve.py (recovers the archive's affine GF(2) tag map by
# randomised clean-basis search); this script just invokes it. No seed,
# generator, or answer key is consulted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${HERE}/solve.py"
