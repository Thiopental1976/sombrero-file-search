#!/bin/bash
# Publishes SHA256SUMS for a release: downloads every file of the release back from GitHub,
# hashes what users will actually download, and uploads the list (replacing an older one).
# Run it as the LAST step of a release, after every file is up (the Windows zip included).
#   packaging/sha256sums.sh v1.5.0            # compute, show and upload
#   packaging/sha256sums.sh v1.5.0 --dry-run  # compute and show only
# Users check with:  sha256sum -c SHA256SUMS --ignore-missing
set -euo pipefail
TAG=${1:?usage: sha256sums.sh <tag> [--dry-run]}
DRY=${2:-}
command -v gh >/dev/null || { echo "gh (GitHub CLI) not found" >&2; exit 1; }
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
gh release download "$TAG" --dir "$D" --pattern '*'
rm -f "$D/SHA256SUMS"
n=$(find "$D" -maxdepth 1 -type f | wc -l)
[ "$n" -gt 0 ] || { echo "release $TAG has no files" >&2; exit 1; }
L=$(mktemp)
( cd "$D" && LC_ALL=C sha256sum -- * ) > "$L"
mv "$L" "$D/SHA256SUMS"
( cd "$D" && sha256sum -c --quiet SHA256SUMS )
echo "SHA256SUMS for $TAG ($n files):"; cat "$D/SHA256SUMS"
if [ "$DRY" = "--dry-run" ]; then echo "(dry run: nothing uploaded)"; exit 0; fi
gh release upload "$TAG" "$D/SHA256SUMS" --clobber
echo "uploaded SHA256SUMS to $TAG"
