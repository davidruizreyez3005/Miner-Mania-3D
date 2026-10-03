# Android updates that keep the save

Android installs a new APK over the installed game - keeping its data, the
save included - only when all three hold:

1. the package id is the same (`com.minermania.mm3d`, fixed in
   `export_presets.cfg`);
2. the version code is not lower: every build's code is the minutes since
   2020-01-01 of its commit (`tools/apk/set_version.py`), so a newer commit
   always installs over an older one;
3. **the APK is signed with the same key.** Every CI build (and every
   release) is signed with one *update key* that comes from the repository
   secrets - never from the repository, which is public.

The Android workflow's summary says which key signed each build and shows
the certificate fingerprint; with the update key every build shows the same
one. Its device test installs each build over the running game and, once
the previous build carries the same key, updates that build with a saved
claim to the new one - the claim must still be there.

## Set up the update key (once, one minute, works from a phone)

The key is derived from one secret, a random password: the same password
gives the same key on every run (`tools/apk/update_key.py`), so there is no
key file to create, convert or upload.

1. **Make a random password** of 20 or more characters - let your password
   manager generate one (or type a long string of random words and
   characters). **Save it in your password manager:** it *is* the game's
   signing key. Anyone with it could sign an update of your game, and
   without it no build can ever update the installed game again.
2. **Add it as a repository secret** on GitHub (the mobile website works):
   the repository > **Settings** > **Secrets and variables** > **Actions** >
   **New repository secret**:

   | Name | Secret |
   | --- | --- |
   | `ANDROID_UPDATE_SEED` | the password |

3. **Build once with it:** push a commit, or open **Actions** > **Android** >
   **Run workflow** on your branch. The run's summary now says "signed with
   the update key from ANDROID_UPDATE_SEED" and shows the certificate
   fingerprint every later build will carry.

The release workflow signs with the same key.

## Switching from a build signed with a one-off key

Builds made before the update key existed were each signed with their own
one-off key, and those keys are gone, so no new build can be installed over
them (Android: "App not installed - package conflicts with an existing
package"). Uninstall that build once and install the first build with the
update key; from then on every build installs over the previous one and
keeps the save.

Uninstalling deletes the save of that old build. To keep the claim, copy the
save off the phone first - CI builds are debuggable, so a computer with
`adb` and USB debugging on the phone can read the game's files:

```sh
adb exec-out run-as com.minermania.mm3d cat files/saves/slot0.save > slot0.save
# uninstall the game, install the new APK, open it once and close it, then:
adb push slot0.save /data/local/tmp/slot0.save
adb shell "cat /data/local/tmp/slot0.save | run-as com.minermania.mm3d sh -c 'mkdir -p files/saves && cat > files/saves/slot0.save'"
adb shell rm /data/local/tmp/slot0.save
```

## A keystore of your own (optional)

To sign with an existing keystore instead (for example a Google Play upload
key), add these three secrets; they take precedence over
`ANDROID_UPDATE_SEED` - and changing the key means one more uninstall:

| Name | Secret |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | the keystore file in base64 (`base64 -w0 my.keystore`) |
| `ANDROID_KEYSTORE_PASSWORD` | its password |
| `ANDROID_KEY_ALIAS` | the key's alias |

The update key itself can also be written to a keystore on your computer
(Python 3 and OpenSSL), for example to register it somewhere:

```sh
ANDROID_UPDATE_SEED='the password' KEYSTORE_PASSWORD='a keystore password' \
  python tools/apk/update_key.py --out minermania-update.p12
```

## Other safety nets

- **Keep app data on uninstall**: Android 10 and later ask whether to keep
  the game's data when it is uninstalled (`retain_data_on_uninstall`).
  Keep it, and installing a build with the update key again picks the mine
  up where it was.
- **Android backup** is allowed (`user_data_backup/allow`): with Google
  backup on, a new phone or a reinstall can restore the save.
- **Older builds**: Android refuses to install an older build over a newer
  one; wait for a newer build instead of uninstalling.
- Saves carry a format version and are migrated on load (`SaveCodec`), and
  a damaged save falls back to the previous one.
