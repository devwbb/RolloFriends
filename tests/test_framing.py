from __future__ import annotations

import json

import pytest

from aiosmartfriends.exceptions import SmartFriendsProtocolError
from aiosmartfriends.framing import LineFramer, encode_message


def test_split_frames_across_chunks() -> None:
    framer = LineFramer()
    assert framer.feed(b'{"a":') == []
    assert framer.feed(b'1}\n{"b":2}\n') == [b'{"a":1}', b'{"b":2}']


def test_crlf_and_whitespace_are_tolerated() -> None:
    framer = LineFramer()
    assert framer.feed(b'  {"a":1}\r\n\t\n') == [b'{"a":1}']


def test_empty_and_partial_buffer() -> None:
    framer = LineFramer()
    assert framer.feed(b"\n\r\n") == []
    assert framer.buffered == 0
    assert framer.feed(b'{"a":') == []
    assert framer.buffered == 5


def test_oversized_frame_is_rejected() -> None:
    framer = LineFramer(max_frame_size=4)
    with pytest.raises(SmartFriendsProtocolError):
        framer.feed(b"12345\n")


def test_oversized_unterminated_buffer_is_rejected() -> None:
    framer = LineFramer(max_frame_size=4)
    with pytest.raises(SmartFriendsProtocolError):
        framer.feed(b"12345")


def test_encode_message_is_compact_utf8_with_newline() -> None:
    encoded = encode_message({"command": "helo", "name": "Büro"})
    assert encoded.endswith(b"\n")
    assert json.loads(encoded) == {"command": "helo", "name": "Büro"}
    assert b" " not in encoded
