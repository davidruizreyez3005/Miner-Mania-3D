#!/usr/bin/env bash
# Install the pinned Blender LTS for headless asset builds.
#
#   tools/ci/install_blender.sh <install_dir>
#
# Downloads the official Linux tarball, verifies it against the pinned SHA-256
# (from https://download.blender.org/release/Blender4.5/blender-4.5.14.sha256),
# extracts it and prints the binary path. An existing, verified install is
# reused (CI caches <install_dir>). Fails loudly on any mismatch.
set -euo pipefail

BLENDER_VERSION="4.5.14"
BLENDER_SERIES="4.5"
BLENDER_SHA256="9ba871ff2ecd36526b77432745980b7e6664ecd0c7ca11c48849073dcfe06da3"
ARCHIVE="blender-${BLENDER_VERSION}-linux-x64.tar.xz"
URL="https://download.blender.org/release/Blender${BLENDER_SERIES}/${ARCHIVE}"

dest="${1:?usage: install_blender.sh <install_dir>}"
mkdir -p "$dest"
bin="$dest/blender-${BLENDER_VERSION}-linux-x64/blender"

if [[ ! -x "$bin" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "Downloading $URL" >&2
  curl --fail --location --retry 4 --retry-delay 5 --silent --show-error -o "$tmp/$ARCHIVE" "$URL"
  echo "${BLENDER_SHA256}  $tmp/$ARCHIVE" | sha256sum --check --strict >&2
  tar -xJf "$tmp/$ARCHIVE" -C "$dest"
fi

version="$("$bin" --background --factory-startup --version 2>/dev/null)"
version="${version%%$'\n'*}"          # first line (no `| head`: SIGPIPE under pipefail)
if [[ "$version" != "Blender ${BLENDER_VERSION}"* ]]; then
  echo "error: expected Blender ${BLENDER_VERSION}, got '${version}'" >&2
  exit 1
fi
echo "$version" >&2
echo "$bin"
