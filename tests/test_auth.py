from __future__ import annotations

import pytest

from aiosmartfriends.auth import digest, password_hash
from aiosmartfriends.exceptions import SmartFriendsProtocolError

SALT = "MDEyMzQ1Njc4OWFiY2RlZg=="
SESSION_SALT = "ZmVkY2JhOTg3NjU0MzIxMA=="


def test_reference_digest_vector() -> None:
    assert digest("testpass", SALT, SESSION_SALT) == "FKunZxIxe0GLkz0uNytvPv5LJdo="


def test_unicode_password_vector() -> None:
    assert digest("pässwörd", SALT, SESSION_SALT) == "OvixGJjJI9I4WfrfK2J0LLZCRG4="


def test_password_hash_is_base64_sha256() -> None:
    assert password_hash("testpass", SALT) == "orKtpBcr+5QiyZrvwG7+Gjl3LA+jme5nejvlijdOJ9Y="


@pytest.mark.parametrize("salt", ["!!!", ""])
def test_invalid_salt_rejected(salt: str) -> None:
    with pytest.raises(SmartFriendsProtocolError):
        password_hash("x", salt)


def test_invalid_session_salt_rejected() -> None:
    with pytest.raises(SmartFriendsProtocolError):
        digest("x", SALT, "!!!")
