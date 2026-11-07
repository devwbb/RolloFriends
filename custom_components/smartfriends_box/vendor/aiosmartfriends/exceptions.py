"""Typed exceptions for the SmartFriends Box client."""

from __future__ import annotations


class SmartFriendsError(Exception):
    """Base class for all library errors."""

    is_transient = False


class SmartFriendsConnectionError(SmartFriendsError):
    """The TCP/TLS connection could not be established or was lost."""

    is_transient = True


class SmartFriendsTimeout(SmartFriendsError):
    """The box did not answer within the expected time."""

    is_transient = True


class SmartFriendsNotConnected(SmartFriendsError):
    """The client is not connected to a box."""

    is_transient = True


class SmartFriendsCertificateError(SmartFriendsConnectionError):
    """TLS certificate validation against the pinned Enexoma root failed."""


class SmartFriendsAuthenticationError(SmartFriendsError):
    """Credentials were rejected, or a password change is required."""


class SmartFriendsProtocolError(SmartFriendsError):
    """The box sent malformed or unexpected data."""


class SmartFriendsSessionExpired(SmartFriendsError):
    """The box invalidated the session."""

    is_transient = True


class SmartFriendsServerError(SmartFriendsError):
    """The box returned ``responseCode == -1`` or an error in a code-1 message."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SmartFriendsCommandRejected(SmartFriendsServerError):
    """A device command was explicitly rejected by the box."""


class SmartFriendsIdentityError(SmartFriendsError):
    """A discovered endpoint did not prove a consistent SmartFriends identity."""


class SmartFriendsCancelled(SmartFriendsError):
    """The operation was cancelled."""
