#!/usr/bin/env bash
# Install the Android export templates of the pinned Godot release.
#
#   tools/ci/install_godot_templates.sh [cache_dir]
#
# Downloads the official export template archive from the Godot GitHub
# release, verifies it against the SHA-512 in the release's SHA512-SUMS.txt,
# and installs only the Android templates where the editor looks for them
# (~/.local/share/godot/export_templates/<version>). cache_dir keeps the
# extracted templates between CI runs. Prints the templates directory.
set -euo pipefail

GODOT_VERSION="4.7.2"
TPZ="Godot_v${GODOT_VERSION}-stable_export_templates.tpz"
TPZ_SHA512="ca4d71c4d7b81dfc15d1a98baa07534aa95b03fdda78a0075b06672e1648d2e5f40980c9adc28d23e1b92e732ee7bf3461997aa804af74ec2fcd7a93ccb84079"
URL="https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/${TPZ}"
FILES=(android_debug.apk android_release.apk version.txt)

cache="${1:-}"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/godot/export_templates/${GODOT_VERSION}.stable"
mkdir -p "$dest"

have_all() {
  local dir="$1"
  for f in "${FILES[@]}"; do [[ -s "$dir/$f" ]] || return 1; done
}

if [[ -n "$cache" ]] && have_all "$cache"; then
  cp "${FILES[@]/#/$cache/}" "$dest/"
elif ! have_all "$dest"; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "Downloading $URL" >&2
  curl --fail --location --retry 4 --retry-delay 5 --silent --show-error -o "$tmp/$TPZ" "$URL"
  echo "${TPZ_SHA512}  $tmp/$TPZ" | sha512sum --check --strict >&2
  unzip -q -j -o "$tmp/$TPZ" "${FILES[@]/#/templates/}" -d "$dest"
  if [[ -n "$cache" ]]; then
    mkdir -p "$cache"
    cp "${FILES[@]/#/$dest/}" "$cache/"
  fi
fi

version="$(tr -d '[:space:]' < "$dest/version.txt")"
if [[ "$version" != "${GODOT_VERSION}.stable" ]]; then
  echo "error: templates are '$version', expected ${GODOT_VERSION}.stable" >&2
  exit 1
fi
echo "$dest"
