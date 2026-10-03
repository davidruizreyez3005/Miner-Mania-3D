#!/usr/bin/env python3
"""The update key: the Android signing key, derived from one secret.

Android installs an APK over the installed game - keeping its save - only
when both are signed with the same key, so every build needs one key that
never changes, and it must never be committed (the repository is public).
Instead of storing a keystore, CI keeps a single secret, the seed (the
repository secret ANDROID_UPDATE_SEED: a random password of 20 or more
characters), and derives the key from it on every run. The same seed always
gives the same RSA key and the same self-signed certificate, byte for byte,
so every build carries the same signature. Whoever holds the seed holds the key: keep it like a
password (a password manager is its backup).

    ANDROID_UPDATE_SEED=... KEYSTORE_PASSWORD=... \\
        python tools/apk/update_key.py --out update.p12 [--alias minermania]
    python tools/apk/update_key.py --self-test

Writes a PKCS#12 keystore (with the openssl command) protected by
KEYSTORE_PASSWORD and prints the certificate's SHA-256 - public: it is what
every APK must carry. The seed is only read from the environment, never from
the command line. Standard library only. The derivation is fixed ("v1"):
changing anything in it would change the key and stop updates installing.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DOMAIN = b"MinerMania3D update key v1"
E = 65537
PRIME_BITS = 1536                        # RSA-3072
SUBJECT = "Miner Mania 3D"
NOT_BEFORE = "260101000000Z"             # UTCTime 2026-01-01
NOT_AFTER = "21251231235959Z"            # GeneralizedTime 2125-12-31
MIN_SEED = 16
TEST_SEED = "self-test seed, not a real key: correct horse battery staple"


def _small_primes(limit: int) -> list[int]:
    sieve = bytearray([1]) * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return [i for i in range(limit + 1) if sieve[i]]


SMALL_PRIMES = _small_primes(4000)


def _stream(seed: bytes, label: bytes, n: int) -> bytes:
    return hashlib.shake_256(DOMAIN + b"\0" + label + b"\0" + seed).digest(n)


def _probable_prime(n: int) -> bool:
    for p in SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in SMALL_PRIMES[:40]:          # fixed bases: the result never varies
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(seed: bytes, label: bytes) -> int:
    """The first prime from a seeded odd start with its top two bits set (so
    the product has the full size) and gcd(E, p - 1) = 1."""
    c = int.from_bytes(_stream(seed, label, PRIME_BITS // 8), "big")
    c |= (3 << (PRIME_BITS - 2)) | 1
    while not ((c - 1) % E != 0 and _probable_prime(c)):
        c += 2
    if c.bit_length() != PRIME_BITS:
        raise RuntimeError("prime search left the size range")
    return c


# ----------------------------------------------------------------- DER

def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _len(len(body)) + body


def _int(v: int) -> bytes:
    return _tlv(0x02, v.to_bytes((v.bit_length() + 8) // 8, "big"))


def _seq(*parts: bytes) -> bytes:
    return _tlv(0x30, b"".join(parts))


def _oid(dotted: str) -> bytes:
    arcs = [int(a) for a in dotted.split(".")]
    out = bytearray([40 * arcs[0] + arcs[1]])
    for a in arcs[2:]:
        chunk = [a & 0x7F]
        a >>= 7
        while a:
            chunk.append(0x80 | (a & 0x7F))
            a >>= 7
        out += bytes(reversed(chunk))
    return _tlv(0x06, bytes(out))


NULL = b"\x05\x00"
RSA_ENCRYPTION = "1.2.840.113549.1.1.1"
SHA256_WITH_RSA = "1.2.840.113549.1.1.11"
SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def derive(seed: str) -> dict:
    """Key and certificate (DER) for a seed - the same every time."""
    s = seed.strip().encode("utf-8")
    if len(s) < MIN_SEED:
        raise ValueError(f"the seed is too short ({len(s)} characters): use a random password of 20 or more characters")
    p = _prime(s, b"p")
    q = _prime(s, b"q")
    if p == q:
        raise RuntimeError("p == q")
    if p < q:
        p, q = q, p
    n = p * q
    d = pow(E, -1, (p - 1) * (q - 1))
    dp, dq, qinv = d % (p - 1), d % (q - 1), pow(q, -1, p)
    rsa_key = _seq(_int(0), _int(n), _int(E), _int(d), _int(p), _int(q), _int(dp), _int(dq), _int(qinv))
    public = _seq(_int(n), _int(E))
    alg = _seq(_oid(SHA256_WITH_RSA), NULL)
    name = _seq(_tlv(0x31, _seq(_oid("2.5.4.3"), _tlv(0x0C, SUBJECT.encode()))))
    serial = int.from_bytes(_stream(s, b"serial", 16), "big") >> 1 | 1
    tbs = _seq(
        _tlv(0xA0, _int(2)),                                          # v3
        _int(serial),
        alg,
        name,
        _seq(_tlv(0x17, NOT_BEFORE.encode()), _tlv(0x18, NOT_AFTER.encode())),
        name,
        _seq(_seq(_oid(RSA_ENCRYPTION), NULL), _tlv(0x03, b"\0" + public)),
        _tlv(0xA3, _seq(_seq(_oid("2.5.29.14"), _tlv(0x04, _tlv(0x04, hashlib.sha1(public).digest()))))),
    )
    # PKCS#1 v1.5 with SHA-256: deterministic, so the certificate is too.
    k = (n.bit_length() + 7) // 8
    info = SHA256_DIGEST_INFO + hashlib.sha256(tbs).digest()
    m = int.from_bytes(b"\0\1" + b"\xff" * (k - 3 - len(info)) + b"\0" + info, "big")
    sig = pow(m, d, n)
    if pow(sig, E, n) != m:
        raise RuntimeError("signature check failed")
    cert = _seq(tbs, alg, _tlv(0x03, b"\0" + sig.to_bytes(k, "big")))
    return {"key": rsa_key, "cert": cert, "n_bits": n.bit_length(), "sha256": hashlib.sha256(cert).hexdigest()}


def _pem(kind: str, der: bytes) -> bytes:
    b64 = base64.b64encode(der).decode()
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return ("-----BEGIN %s-----\n%s\n-----END %s-----\n" % (kind, "\n".join(lines), kind)).encode()


def write_keystore(k: dict, out: Path, alias: str, password_env: str) -> None:
    """PKCS#12 with the key and certificate (openssl reads the password from
    the environment variable, so it never appears in a command line)."""
    with tempfile.TemporaryDirectory() as tmp:
        key_pem = Path(tmp) / "key.pem"
        fd = os.open(key_pem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(_pem("RSA PRIVATE KEY", k["key"]))
        cert_pem = Path(tmp) / "cert.pem"
        cert_pem.write_bytes(_pem("CERTIFICATE", k["cert"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["openssl", "pkcs12", "-export", "-inkey", str(key_pem), "-in", str(cert_pem),
                        "-name", alias, "-out", str(out), "-passout", "env:" + password_env],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    os.chmod(out, 0o600)


def self_test() -> None:
    a, b = derive(TEST_SEED), derive(TEST_SEED + " ")
    assert a["cert"] == b["cert"] and a["key"] == b["key"], "the same seed must give the same key"
    assert a["n_bits"] == 2 * PRIME_BITS, a["n_bits"]
    c = derive(TEST_SEED + "!")
    assert c["sha256"] != a["sha256"], "another seed must give another key"
    try:
        derive("short")
        raise AssertionError("a short seed must be refused")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        cert_pem = Path(tmp) / "cert.pem"
        cert_pem.write_bytes(_pem("CERTIFICATE", a["cert"]))
        text = subprocess.run(["openssl", "x509", "-in", str(cert_pem), "-noout", "-subject", "-fingerprint", "-sha256"],
                              check=True, capture_output=True, text=True).stdout
        assert SUBJECT in text, text
        fp = text.split("=")[-1].strip().replace(":", "").lower()
        assert fp == a["sha256"], (fp, a["sha256"])
        os.environ["UPDATE_KEY_SELF_TEST_PASS"] = "self-test-password"
        ks = Path(tmp) / "test.p12"
        write_keystore(a, ks, "minermania", "UPDATE_KEY_SELF_TEST_PASS")
        info = subprocess.run(["openssl", "pkcs12", "-in", str(ks), "-nokeys", "-passin", "env:UPDATE_KEY_SELF_TEST_PASS"],
                              check=True, capture_output=True, text=True).stdout
        assert "friendlyName: minermania" in info, info
    print(f"update_key self-test passed (test certificate {a['sha256'][:16]}...)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, help="PKCS#12 keystore to write")
    ap.add_argument("--alias", default="minermania")
    ap.add_argument("--seed-env", default="ANDROID_UPDATE_SEED", help="environment variable holding the seed")
    ap.add_argument("--password-env", default="KEYSTORE_PASSWORD", help="environment variable holding the keystore password")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    seed = os.environ.get(args.seed_env, "")
    if not seed.strip():
        print(f"error: {args.seed_env} is not set", file=sys.stderr)
        return 2
    if not args.out or not os.environ.get(args.password_env):
        print(f"error: --out and {args.password_env} are required", file=sys.stderr)
        return 2
    try:
        k = derive(seed)
    except ValueError as e:
        print(f"error: {args.seed_env}: {e}", file=sys.stderr)
        return 1
    write_keystore(k, args.out, args.alias, args.password_env)
    print(k["sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
