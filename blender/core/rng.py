"""Deterministic randomness.

Python's built-in ``hash()`` is salted per process, so it must never feed a
seed. Everything here derives child seeds with SHA-256 so the same definition
seed always produces the same geometry on every machine and every run.
"""

import hashlib
import random


def derive_seed(*parts):
    """Stable 31-bit seed from arbitrary parts (ints/strings)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "little") & 0x7FFFFFFF


class Rng(random.Random):
    """``random.Random`` with helpers for deterministic sub-streams."""

    def __init__(self, seed, label="root"):
        self.base_seed = int(seed)
        self.label = label
        super().__init__(derive_seed(self.base_seed, label))

    def child(self, label):
        return Rng(self.base_seed, f"{self.label}/{label}")

    def jitter(self, value, amount):
        """value * (1 +/- amount)."""
        return value * (1.0 + self.uniform(-amount, amount))

    def vec_offset(self, scale=100.0):
        """Deterministic offset used to decorrelate procedural noise."""
        return (self.uniform(-scale, scale), self.uniform(-scale, scale), self.uniform(-scale, scale))
