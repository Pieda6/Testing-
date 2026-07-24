#!/usr/bin/env bash
# Golden solution entrypoint for dynamo/ecdsa-nonce-lattice.
# Real logic lives in solve.py (a Hidden Number Problem lattice attack); this
# script just invokes it. No seed, generator, or answer key is consulted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${HERE}/solve.py"
