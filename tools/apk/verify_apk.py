#!/usr/bin/env python3
"""Verify an exported Android APK before it is published.

    python tools/apk/verify_apk.py <apk> --sdk <android_sdk> [--report out.json]
        [--manifest out.json] [--expect-release] [--max-mb 250]
        [--expect-version-code N] [--expect-version-name S] [--expect-cert-sha256 HEX]

Checks (any failure exits 1):
  * the file exists, is non-empty and within the size budget
  * it is a well-formed zip with the Android essentials (manifest, dex,
    resources) and the Godot engine library for arm64-v8a only
  * package id, version code/name and native ABI match export_presets.cfg
    or the build's stamped version (read with aapt2 from the SDK build-tools)
  * the signature verifies (apksigner; v2+ scheme), a release build is not
    signed with the Android debug certificate, and when the expected signing
    certificate is given (the update key) the APK carries exactly that one -
    the condition for installing over an earlier build and keeping its data
  * the game is packaged: project settings, every content data file, the
    asset catalog, and an imported model for every asset the game uses
  * no secrets inside: no keystore/key/credential files, no private keys or
    well-known token formats, and none of the values passed in the
    SECRET_VALUES environment variable (newline separated; e.g. the release
    keystore password) appear anywhere in the archive
Writes a JSON report and a file manifest (path, size, sha256) when asked.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "assets"))
import export_filter  # noqa: E402

SECRET_NAME = re.compile(r"(\.(keystore|jks|p12|pfx|pem|key)$|(^|/)\.env$|credentials|secrets?\.(json|txt|cfg))", re.I)
SECRET_PATTERNS = [
    # A real PEM block: the header followed by base64 key material (the engine
    # binary contains bare header strings for its TLS parser).
    (re.compile(rb"-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{64,}"), "private key"),
    (re.compile(rb"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(rb"gh[pousr]_[A-Za-z0-9]{36}"), "GitHub token"),
    (re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), "Google API key"),
    (re.compile(rb"sk-(ant-)?[A-Za-z0-9_\-]{32,}"), "API secret key"),
    (re.compile(rb"(keystore|store|key)_?pass(word)?\s*[=:]\s*\"[^\"]{3,}\"", re.I), "keystore password assignment"),
]
DEBUG_CERT_DNS = ("CN=Android Debug", "CN=Godot, OU=Godot Engine")


def preset_options() -> dict:
    text = (ROOT / "export_presets.cfg").read_text(encoding="utf-8")
    opts = {}
    for m in re.finditer(r'^([a-z_/0-9\-]+)=(.*)$', text, re.M):
        opts[m.group(1)] = m.group(2).strip().strip('"')
    return opts


def run(cmd) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--sdk", default=os.environ.get("ANDROID_HOME", ""))
    ap.add_argument("--report", default="")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--expect-release", action="store_true")
    ap.add_argument("--max-mb", type=float, default=250.0)
    ap.add_argument("--expect-version-code", default="", help="default: export_presets.cfg")
    ap.add_argument("--expect-version-name", default="", help="default: export_presets.cfg")
    ap.add_argument("--expect-cert-sha256", default="", help="SHA-256 of the signing certificate (hex, colons allowed)")
    a = ap.parse_args()
    fails, notes = [], []
    apk = pathlib.Path(a.apk)
    info = {"apk": str(apk)}

    def check(ok: bool, what: str) -> bool:
        (notes if ok else fails).append(("PASS " if ok else "FAIL ") + what)
        return ok

    if not check(apk.is_file(), "APK exists"):
        return finish(a, info, fails, notes)
    size = apk.stat().st_size
    info["size_bytes"] = size
    info["size_mb"] = round(size / 1e6, 2)
    check(size > 1_000_000, "APK is not empty (%d bytes)" % size)
    check(size <= a.max_mb * 1e6, "APK within the %.0f MB budget (%.1f MB)" % (a.max_mb, size / 1e6))
    try:
        z = zipfile.ZipFile(apk)
        bad = z.testzip()
        check(bad is None, "zip structure intact" + ("" if bad is None else " (corrupt entry %s)" % bad))
    except zipfile.BadZipFile as e:
        check(False, "APK is a valid zip (%s)" % e)
        return finish(a, info, fails, notes)
    names = z.namelist()
    nameset = set(names)
    for req in ["AndroidManifest.xml", "classes.dex", "resources.arsc", "assets/project.binary"]:
        check(req in nameset, "contains " + req)
    libs = sorted({n.split("/")[1] for n in names if n.startswith("lib/") and n.count("/") >= 2})
    info["abis"] = libs
    check(libs == ["arm64-v8a"], "native code is arm64-v8a only (%s)" % ", ".join(libs))
    check(any(n.startswith("lib/arm64-v8a/libgodot_android.so") for n in names), "Godot engine library packaged")

    opts = preset_options()
    want_pkg = opts.get("package/unique_name", "")
    want_code = a.expect_version_code or opts.get("version/code", "")
    want_name = a.expect_version_name or opts.get("version/name", "")
    aapt = pathlib.Path(a.sdk) / "build-tools"
    aapt2 = sorted(aapt.glob("*/aapt2"))
    if check(bool(aapt2), "aapt2 available in the SDK"):
        badging = run([str(aapt2[-1]), "dump", "badging", str(apk)])
        m = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
        if check(m is not None, "manifest readable"):
            info["package"], info["version_code"], info["version_name"] = m.group(1), m.group(2), m.group(3)
            check(m.group(1) == want_pkg, "package id %s (expected %s)" % (m.group(1), want_pkg))
            check(m.group(2) == want_code, "version code %s (expected %s)" % (m.group(2), want_code))
            check(m.group(3) == want_name, "version name %s (expected %s)" % (m.group(3), want_name))
        nc = re.search(r"native-code: (.*)", badging)
        info["native_code"] = nc.group(1).strip() if nc else ""
        check(nc is not None and "arm64-v8a" in nc.group(1), "manifest declares arm64-v8a native code")
        sdk = re.search(r"minSdkVersion:'(\d+)'", badging)
        tsdk = re.search(r"targetSdkVersion:'(\d+)'", badging)
        info["min_sdk"] = sdk.group(1) if sdk else ""
        info["target_sdk"] = tsdk.group(1) if tsdk else ""
    signer = sorted(aapt.glob("*/apksigner"))
    if check(bool(signer), "apksigner available in the SDK"):
        out = run([str(signer[-1]), "verify", "--verbose", "--print-certs", str(apk)])
        check("Verified using v2 scheme (APK Signature Scheme v2): true" in out or
              "Verified using v3 scheme (APK Signature Scheme v3): true" in out, "signature verifies (v2/v3)")
        dn = re.search(r"Signer #1 certificate DN: (.*)", out)
        info["signer"] = dn.group(1).strip() if dn else ""
        digests = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]+)", out)
        info["cert_sha256"] = digests[0].lower() if digests else ""
        check(len(digests) == 1, "exactly one signer (%d)" % len(digests))
        if a.expect_cert_sha256:
            want = a.expect_cert_sha256.replace(":", "").strip().lower()
            check(info["cert_sha256"] == want, "signed with the update key (certificate SHA-256 %s)" % (info["cert_sha256"][:16] + "..."))
        if a.expect_release:
            check(not any(d in info["signer"] for d in DEBUG_CERT_DNS), "release build is not signed with a debug certificate")

    # Game content.
    data_files = sorted(str(p.relative_to(ROOT)).replace(os.sep, "/") for p in (ROOT / "data").rglob("*.json"))
    missing_data = [f for f in data_files if "assets/" + f not in nameset]
    check(not missing_data, "all %d content data files packaged%s" % (len(data_files), "" if not missing_data else " (missing %s)" % missing_data))
    check("assets/assets/generated/catalog.json" in nameset, "asset catalog packaged")
    imported = [n for n in names if n.startswith("assets/.godot/imported/")]
    used = sorted(export_filter.referenced())
    missing_models = [aid for aid in used if not any(n.startswith("assets/.godot/imported/%s.glb-" % aid) for n in imported)]
    check(not missing_models, "a model for all %d assets the game uses%s" % (len(used), "" if not missing_models else " (missing %s)" % missing_models))
    # Every model's textures (Godot names extracted textures <model>_<image>).
    textures = [n.rsplit("/", 1)[-1] for n in imported if n.endswith(".ctex")]
    untextured = [aid for aid in used if not any(t.startswith(aid + "_") for t in textures)]
    check(not untextured, "textures packaged for every used model%s" % ("" if not untextured else " (missing for %d: %s)" % (len(untextured), ", ".join(untextured[:6]))))
    audio = [n for n in imported if ".wav-" in n]
    check(len(audio) >= 20, "sound effects packaged (%d)" % len(audio))
    info["counts"] = {"files": len(names), "imported": len(imported), "models": len([n for n in imported if n.endswith(".scn")]),
                      "textures": len([n for n in imported if n.endswith(".ctex")]), "sounds": len(audio)}

    # Secrets.
    bad_names = [n for n in names if SECRET_NAME.search(n) and not n.startswith("META-INF/")]
    check(not bad_names, "no key or credential files (%s)" % (", ".join(bad_names[:5]) or "none"))
    secret_values = [s.encode() for s in os.environ.get("SECRET_VALUES", "").splitlines() if len(s.strip()) >= 8]
    hits = []
    for n in names:
        if n.startswith("META-INF/"):
            continue
        blob = z.read(n)
        for pat, what in SECRET_PATTERNS:
            if pat.search(blob):
                hits.append("%s in %s" % (what, n))
        for sv in secret_values:
            if sv in blob:
                hits.append("a provided secret value in %s" % n)
    check(not hits, "no secrets or tokens inside (%s)" % ("; ".join(hits[:5]) or "scanned %d files" % len(names)))
    # Size breakdown for the report.
    cats = {}
    for i in z.infolist():
        n = i.filename
        k = "native" if n.startswith("lib/") else "textures" if n.endswith(".ctex") else "models" if n.endswith(".scn") else \
            "audio" if (".wav-" in n) else "code" if n.endswith(".dex") else "other"
        cats[k] = cats.get(k, 0) + i.compress_size
    info["size_by_kind_mb"] = {k: round(v / 1e6, 2) for k, v in sorted(cats.items(), key=lambda kv: -kv[1])}
    if a.manifest:
        entries = []
        for i in z.infolist():
            entries.append({"path": i.filename, "size": i.file_size, "compressed": i.compress_size,
                            "sha256": hashlib.sha256(z.read(i.filename)).hexdigest()})
        pathlib.Path(a.manifest).write_text(json.dumps({"apk": apk.name, "sha256": sha256(apk), "files": entries}, indent=1))
    info["sha256"] = sha256(apk)
    return finish(a, info, fails, notes)


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def finish(a, info, fails, notes) -> int:
    info["checks"] = notes + fails
    info["passed"] = not fails
    for line in notes + fails:
        print(line)
    print("APK verification %s: %s" % ("PASSED" if not fails else "FAILED", info.get("apk")))
    if a.report:
        pathlib.Path(a.report).write_text(json.dumps(info, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
