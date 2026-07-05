"""Unit tests for KeyManager: kid derivation, rotation, and JWKS publication."""
from __future__ import annotations

from gabriel.identity.keys import KeyManager


def test_kid_is_stable_for_same_key():
    km = KeyManager()
    first = km.kid
    # kid is a pure function of the public key material; re-reading is stable.
    assert km.kid == first
    # A separately-generated key yields a different kid.
    assert KeyManager().kid != first


def test_jwks_structure():
    km = KeyManager()
    jwks = km.jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"] == km.kid
    assert key["n"] and key["e"]


def test_rotate_keeps_old_key_for_verification():
    km = KeyManager()
    old_kid = km.kid

    new_kid = km.rotate()

    assert new_kid != old_kid
    assert km.kid == new_kid
    # Both the old and new public keys remain resolvable for verification so
    # tokens signed before the rotation still validate (ADR-007 seamless
    # rotation requirement).
    assert km.get_verification_key(old_kid) is not None
    assert km.get_verification_key(new_kid) is not None


def test_rotate_publishes_both_keys_in_jwks():
    km = KeyManager()
    old_kid = km.kid
    new_kid = km.rotate()

    published = {key["kid"] for key in km.jwks()["keys"]}
    assert {old_kid, new_kid} <= published


def test_unknown_kid_returns_none():
    km = KeyManager()
    assert km.get_verification_key("not-a-real-kid") is None
