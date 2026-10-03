#!/usr/bin/env bash
# Prepare the update key - the one key every APK is signed with, so each new
# build installs over the game and keeps its save (docs/android_signing.md).
#
#   tools/ci/update_key.sh <keystore_out>
#
# From the repository secrets (passed in as environment variables), first match:
#   ANDROID_KEYSTORE_BASE64 + ANDROID_KEYSTORE_PASSWORD + ANDROID_KEY_ALIAS
#       a keystore of your own (base64);
#   ANDROID_UPDATE_SEED
#       one random password the key is derived from (tools/apk/update_key.py),
#       the same key on every run; the keystore gets a fresh random password.
# Writes the keystore (mode 600) and exports to $GITHUB_ENV: SIGNING=update,
# SIGNING_SOURCE (keystore|seed), UPDATE_KEYSTORE, UPDATE_KEY_ALIAS,
# UPDATE_KEY_PASSWORD (masked) and SIGNING_CERT_SHA256 (the certificate
# fingerprint every APK must carry - public). Exits 3 when no key is
# configured, 1 on a key that cannot be read. Nothing secret is printed.
set -euo pipefail

out="${1:?usage: update_key.sh <keystore_out>}"
java_home="${JAVA_HOME_17_X64:-${JAVA_HOME:-/usr}}"
keytool="$java_home/bin/keytool"
genv="${GITHUB_ENV:-/dev/null}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ks="${ANDROID_KEYSTORE_BASE64:-}"
kp="${ANDROID_KEYSTORE_PASSWORD:-}"
ka="${ANDROID_KEY_ALIAS:-}"
seed="${ANDROID_UPDATE_SEED:-}"

if [[ -n "$ks" || -n "$kp" || -n "$ka" ]]; then
  if [[ -z "$ks" || -z "$kp" || -z "$ka" ]]; then
    echo "::error title=Signing secrets incomplete::ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD and ANDROID_KEY_ALIAS go together (or set ANDROID_UPDATE_SEED alone)"
    exit 1
  fi
  echo "::add-mask::$kp"
  printf '%s' "$ks" | base64 --decode > "$out"
  password="$kp"
  alias="$ka"
  source="keystore"
elif [[ -n "$seed" ]]; then
  password="$(openssl rand -hex 24)"
  echo "::add-mask::$password"
  if ! derived="$(KEYSTORE_PASSWORD="$password" python3 "$here/tools/apk/update_key.py" --out "$out" --alias minermania)"; then
    echo "::error title=ANDROID_UPDATE_SEED unusable::Use a random password of 20 or more characters (docs/android_signing.md)"
    exit 1
  fi
  alias="minermania"
  source="seed"
else
  exit 3
fi
chmod 600 "$out"

# Java (which Godot signs with) must read it and see the expected certificate.
cert="$(KEYSTORE_PASSWORD="$password" "$keytool" -list -v -keystore "$out" -storepass:env KEYSTORE_PASSWORD -alias "$alias" 2>/dev/null \
  | sed -n 's/^[[:space:]]*SHA256: //p' | head -1 | tr -d ': ' | tr 'A-F' 'a-f')" || true
if [[ ${#cert} -ne 64 ]]; then
  rm -f "$out"
  echo "::error title=Update key unreadable::Check ANDROID_KEYSTORE_PASSWORD and ANDROID_KEY_ALIAS"
  exit 1
fi
if [[ $source == seed && "$cert" != "$derived" ]]; then
  rm -f "$out"
  echo "::error title=Update key mismatch::the keystore does not carry the derived certificate"
  exit 1
fi

{
  echo "SIGNING=update"
  echo "SIGNING_SOURCE=$source"
  echo "UPDATE_KEYSTORE=$out"
  echo "UPDATE_KEY_ALIAS=$alias"
  echo "UPDATE_KEY_PASSWORD=$password"
  echo "SIGNING_CERT_SHA256=$cert"
} >> "$genv"
echo "Update key ready (from the $source secret), certificate SHA-256 $cert"
