import pytest

from backend.app.core.security import digest_token, hash_password, verify_password


def test_password_hash_is_not_reversible() -> None:
    password = "correct horse battery staple"
    password_hash = hash_password(password)
    assert password_hash != password
    assert verify_password(password_hash, password)
    assert not verify_password(password_hash, "wrong password")


def test_password_minimum_is_enforced() -> None:
    with pytest.raises(ValueError):
        hash_password("too-short")


def test_token_digest_is_stable_and_not_plaintext() -> None:
    digest = digest_token("session-value")
    assert digest != "session-value"
    assert len(digest) == 64
