#!/bin/sh
# List every packaged file with its size, one per line, for share/manifest.txt.
# Takes the staging root as its only argument.
set -eu
root="$1"

cd "$root"
find . -type f ! -name manifest.txt | sed 's|^\./||' | sort | while read -r f; do
    printf '%s %s\n' "$(wc -c < "$f" | tr -d ' ')" "$f"
done
