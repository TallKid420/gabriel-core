"""Unit tests for PBKDF2 password hashing."""
from __future__ import annotations

import pytest

from gabriel.identity.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", encoded)


def test_wrong_password_fails():
    encoded = hash_password("right-password")
    assert not verify_password("wrong-password", encoded)


def test_hashes_are_salted_and_unique():
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b  # unique salt per hash
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_malformed_hash_is_rejected():
    assert not verify_password("anything", "not-a-valid-hash")
    assert not verify_password("anything", "")


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_needs_rehash_detects_weaker_params():
    encoded = hash_password("pw123456", iterations=100_000)
    assert needs_rehash(encoded, iterations=200_000)
    strong = hash_password("pw123456", iterations=200_000)
    assert not needs_rehash(strong, iterations=200_000)
