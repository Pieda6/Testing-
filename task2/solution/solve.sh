#!/usr/bin/env bash
# Golden solution entrypoint for dynamo/headerless-pcm-normalize.
# Real logic lives in solve.py (recovers each asset's sample format from the
# signal, then emits canonical digests); this script just invokes it. No seed,
# generator, or answer key is consulted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${HERE}/solve.py"
