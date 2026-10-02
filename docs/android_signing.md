# Android updates that keep the save

Android installs a new APK over the installed game - keeping its data, the
save included - only when all three hold:

1. the package id is the same (`com.minermania.mm3d`, fixed in
   `export_presets.cfg`);
2. the version code is not lower: every build's code is the minutes since
   2020-01-01 of its commit (`tools/apk/set_version.py`), so a newer commit
   always installs over an older one;
3. **the APK is signed with the same key.** Every CI build (and every
   release) is signed with one *update key* kept in the repository secrets -
   never in the repository, which is public.

The Android workflow's summary says which key signed each build and shows
the certificate fingerprint; with the update key every build shows the same
one. Its device test installs each build over the running game and, once
the previous build carries the same key, updates that build with a saved
claim to the new one - the claim must still be there.

## Set up the update key (once, about five minutes)

1. **Create the key** on your computer with Java's `keytool` (part of any JDK
   or Android Studio). It asks for a password - pick a long one:

   ```sh
   keytool -genkeypair -v -keystore minermania-update.p12 -storetype PKCS12 \
     -alias minermania -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Miner Mania 3D"
   ```

   Without Java, OpenSSL makes the same kind of file (it asks for the
   password at the second command):

   ```sh
   openssl req -x509 -newkey rsa:4096 -sha256 -days 10000 -nodes \
     -subj "/CN=Miner Mania 3D" -keyout key.pem -out cert.pem
   openssl pkcs12 -export -inkey key.pem -in cert.pem -name minermania -out minermania-update.p12
   rm key.pem cert.pem
   ```

2. **Turn the file into text** (base64):

   - Linux: `base64 -w0 minermania-update.p12 > minermania-update.b64`
   - macOS: `base64 -i minermania-update.p12 -o minermania-update.b64`
   - Windows (PowerShell):
     `[Convert]::ToBase64String([IO.File]::ReadAllBytes("minermania-update.p12")) | Set-Content minermania-update.b64`

3. **Add three repository secrets** on GitHub: the repository > Settings >
   Secrets and variables > Actions > New repository secret:

   | Name | Value |
   | --- | --- |
   | `ANDROID_KEYSTORE_BASE64` | the content of `minermania-update.b64` |
   | `ANDROID_KEYSTORE_PASSWORD` | the password |
   | `ANDROID_KEY_ALIAS` | `minermania` |

4. **Keep `minermania-update.p12` and its password safe** (a password
   manager and a backup copy). A build signed with any other key can never
   update the installed game. Delete the `.b64` file.

The next Android run says "signed with the update key". The release
workflow signs with the same key.

## Switching from a build signed with a one-off key

Builds made before the update key was set up were each signed with their
own one-off key, so the first update-key build cannot be installed over
them (Android: "App not installed - package conflicts with an existing
package"). Uninstall that one once; from then on every build installs over
the previous one.

To keep the claim on the phone through that one uninstall, copy the save off
first. CI builds are debuggable, so a computer with `adb` and USB debugging
on the phone can read the game's files:

```sh
adb exec-out run-as com.minermania.mm3d cat files/saves/slot0.save > slot0.save
# uninstall the game, install the new APK, open it once and close it, then:
adb push slot0.save /data/local/tmp/slot0.save
adb shell "cat /data/local/tmp/slot0.save | run-as com.minermania.mm3d sh -c 'mkdir -p files/saves && cat > files/saves/slot0.save'"
adb shell rm /data/local/tmp/slot0.save
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
