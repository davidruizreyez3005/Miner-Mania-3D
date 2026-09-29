#!/usr/bin/env bash
# Install what the on-device test needs next to the SDK from
# install_android_sdk.sh: the Android Emulator and an Android 15 (API 35)
# x86_64 "Google APIs" system image. The image runs x86_64 builds natively and
# translates ARM code (ro.product.cpu.abilist includes arm64-v8a), so the
# arm64-v8a APK we ship runs on it too - as far as its ndk_translation (0.2.3)
# covers the engine's instructions; the API 30 image's 0.2.2 stopped on one.
#
#   tools/ci/install_android_emulator.sh <sdk_dir>
#
# Archives come from Google's official repository
# (https://dl.google.com/android/repository/repository2-3.xml and
# .../sys-img/google_apis/sys-img2-3.xml) and are verified against Google's
# published SHA-1 *and* a pinned SHA-256; any mismatch fails the install.
set -euo pipefail

BASE="https://dl.google.com/android/repository"
EMU_ZIP="emulator-linux_x64-15917651.zip"          # emulator 37.1.11 (stable channel)
EMU_SHA1="1b1f78891abf8ec268264356e1365c25519e8379"
EMU_SHA256="95771e0ae431897b2a4bd2d97fa095f29a8b0624a7b216baf529f9306161c266"
IMG_ZIP="x86_64-35_r09.zip"                          # system-images;android-35;google_apis;x86_64 r9
IMG_SHA1="0103e6dab21290c4b9d16550a3ce99476f884eef"
IMG_SHA256="c67b9ba0ff5bc0eb6d046871bfa228af14d4d47b02f0cdae94f048e511b7566e"
IMG_DIR="system-images/android-35/google_apis"

sdk="${1:?usage: install_android_emulator.sh <sdk_dir>}"
mkdir -p "$sdk"

fetch() {  # fetch <url> <zip> <sha1> <sha256> <tmpdir>
  local url="$1" zip="$2" sha1="$3" sha256="$4" tmp="$5"
  echo "Downloading $url" >&2
  curl --fail --location --retry 4 --retry-delay 5 --silent --show-error -o "$tmp/$zip" "$url"
  echo "$sha1  $tmp/$zip" | sha1sum --check --strict >&2
  echo "$sha256  $tmp/$zip" | sha256sum --check --strict >&2
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if [[ ! -x "$sdk/emulator/emulator" ]]; then
  fetch "$BASE/$EMU_ZIP" "$EMU_ZIP" "$EMU_SHA1" "$EMU_SHA256" "$tmp"
  rm -rf "$sdk/emulator"
  unzip -q -o "$tmp/$EMU_ZIP" -d "$sdk"
  rm -f "$tmp/$EMU_ZIP"
fi

if [[ ! -s "$sdk/$IMG_DIR/x86_64/system.img" ]]; then
  fetch "$BASE/sys-img/google_apis/$IMG_ZIP" "$IMG_ZIP" "$IMG_SHA1" "$IMG_SHA256" "$tmp"
  rm -rf "$sdk/$IMG_DIR/x86_64"
  mkdir -p "$sdk/$IMG_DIR"
  unzip -q -o "$tmp/$IMG_ZIP" -d "$sdk/$IMG_DIR"
  rm -f "$tmp/$IMG_ZIP"
fi

# The emulator looks for a platforms directory next to the system images.
mkdir -p "$sdk/platforms"
grep -q "arm64-v8a" "$sdk/$IMG_DIR/x86_64/build.prop" || {
  echo "error: the system image does not translate arm64-v8a code" >&2
  exit 1
}
"$sdk/emulator/emulator" -version 2>/dev/null | head -1 >&2
