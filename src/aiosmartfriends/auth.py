"""Challenge-response authentication used by the SmartFriends Box.

The procedure is taken from the verified protocol documentation:

    hashedPassword = Base64(SHA256(UTF8(password) || Base64Decode(salt)))
    digest         = Base64(SHA1(ASCII(hashedPassword) || Base64Decode(sessionSalt)))

The intermediate Base64 text, not its decoded bytes, is fed into SHA-1.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from .exceptions import SmartFriendsProtocolError


def _decode_salt(value: str, name: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as err:
        raise SmartFriendsProtocolError(f"Invalid {name} from the box") from err
    if not decoded:
        raise SmartFriendsProtocolError(f"Empty {name} from the box")
    return decoded


def password_hash(password: str, salt: str) -> str:
    """Return the first authentication stage as Base64 text."""

    salt_bytes = _decode_salt(salt, "salt")
    digest = hashlib.sha256(password.encode("utf-8") + salt_bytes).digest()
    return base64.b64encode(digest).decode("ascii")


def digest(password: str, salt: str, session_salt: str) -> str:
    """Return the login digest expected by the box."""

    session_salt_bytes = _decode_salt(session_salt, "session salt")
    hashed = password_hash(password, salt)
    # usedforsecurity=False keeps this deterministic, protocol-required SHA-1
    # usable on FIPS-restricted Python builds. This is not a security hash.
    # Required by the box protocol; not a security hash.
    second = hashlib.sha1(
        hashed.encode("ascii") + session_salt_bytes,
        usedforsecurity=False,
    ).digest()
    return base64.b64encode(second).decode("ascii")
