#!/usr/bin/env bash
# Install the minimal Android SDK Godot needs to export an APK without
# Gradle: build-tools (apksigner, zipalign, aapt2) and platform-tools.
#
#   tools/ci/install_android_sdk.sh <sdk_dir>
#
# Archives come from Google's official repository
# (https://dl.google.com/android/repository/repository2-3.xml) and are
# verified against Google's published SHA-1 *and* a pinned SHA-256; any
# mismatch fails the install. Prints the SDK path.
set -euo pipefail

BASE="https://dl.google.com/android/repository"
BT_VERSION="35.0.0"
BT_ZIP="build-tools_r35_linux.zip"
BT_SHA1="2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc"
BT_SHA256="bd3a4966912eb8b30ed0d00b0cda6b6543b949d5ffe00bea54c04c81e1561d88"
PT_ZIP="platform-tools_r37.0.1-linux.zip"
PT_SHA1="477254aa5f903c15cf51001717bdf347fb6b53e0"
PT_SHA256="d230f13842f60f782a8645f9c813f8f845bf36089ea7289f28c48f17979313f1"

sdk="${1:?usage: install_android_sdk.sh <sdk_dir>}"
mkdir -p "$sdk"

fetch() {  # fetch <zip> <sha1> <sha256> <tmpdir>
  local zip="$1" sha1="$2" sha256="$3" tmp="$4"
  echo "Downloading $BASE/$zip" >&2
  curl --fail --location --retry 4 --retry-delay 5 --silent --show-error -o "$tmp/$zip" "$BASE/$zip"
  echo "$sha1  $tmp/$zip" | sha1sum --check --strict >&2
  echo "$sha256  $tmp/$zip" | sha256sum --check --strict >&2
}

if [[ ! -x "$sdk/build-tools/$BT_VERSION/apksigner" || ! -x "$sdk/platform-tools/adb" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  fetch "$BT_ZIP" "$BT_SHA1" "$BT_SHA256" "$tmp"
  fetch "$PT_ZIP" "$PT_SHA1" "$PT_SHA256" "$tmp"
  rm -rf "$sdk/build-tools/$BT_VERSION" "$sdk/platform-tools"
  mkdir -p "$sdk/build-tools"
  unzip -q -o "$tmp/$BT_ZIP" -d "$tmp/bt"
  mv "$tmp/bt/android-15" "$sdk/build-tools/$BT_VERSION"
  unzip -q -o "$tmp/$PT_ZIP" -d "$sdk"
  # Licences are accepted by using the official archives' terms.
  mkdir -p "$sdk/licenses"
fi

"$sdk/build-tools/$BT_VERSION/apksigner" --version >&2
echo "$sdk"
