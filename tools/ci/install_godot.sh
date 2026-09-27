#!/usr/bin/env bash
# Install the pinned Godot editor for headless import validation.
#
#   tools/ci/install_godot.sh <install_dir>
#
# Downloads the official Linux x86_64 editor zip, verifies the SHA-512 listed
# in the release's SHA512-SUMS.txt, and prints the binary path. Fails loudly
# on any mismatch.
set -euo pipefail

GODOT_VERSION="4.7.2"
GODOT_SHA512="9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65"
ARCHIVE="Godot_v${GODOT_VERSION}-stable_linux.x86_64.zip"
URL="https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/${ARCHIVE}"

dest="${1:?usage: install_godot.sh <install_dir>}"
mkdir -p "$dest"
bin="$dest/Godot_v${GODOT_VERSION}-stable_linux.x86_64"

if [[ ! -x "$bin" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "Downloading $URL" >&2
  curl --fail --location --retry 4 --retry-delay 5 --silent --show-error -o "$tmp/$ARCHIVE" "$URL"
  echo "${GODOT_SHA512}  $tmp/$ARCHIVE" | sha512sum --check --strict >&2
  unzip -q -o "$tmp/$ARCHIVE" -d "$dest"
  chmod +x "$bin"
fi

version="$("$bin" --headless --version 2>/dev/null | tail -n 1)"
if [[ "$version" != "${GODOT_VERSION}.stable"* ]]; then
  echo "error: expected Godot ${GODOT_VERSION}, got '${version}'" >&2
  exit 1
fi
echo "Godot $version" >&2
echo "$bin"
