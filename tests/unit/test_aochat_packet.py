import pytest

from aomarket.aochat import packet


def test_header_round_trip():
    data = packet.encode_header(packet.AOCP_MSG_PRIVATE, 1234)
    assert len(data) == 4
    assert packet.decode_header(data) == (packet.AOCP_MSG_PRIVATE, 1234)


def test_encode_decode_msg_private_round_trip():
    payload = packet.encode_args(packet.AOCP_MSG_PRIVATE, [12345, "hello there", "\0"])
    args = packet.decode_args(packet.AOCP_MSG_PRIVATE, payload)

    assert args[0] == 12345
    assert args[1] == b"hello there"
    assert args[2] == b"\0"


def test_encode_login_request():
    payload = packet.encode_args(packet.AOCP_LOGIN_REQUEST, [0, "myuser", "deadbeef-cafebabe"])

    # I(0) + S(len=6 "myuser") + S(len=17 key)
    assert payload[:4] == b"\x00\x00\x00\x00"
    assert payload[4:6] == b"\x00\x06"
    assert payload[6:12] == b"myuser"
    assert payload[12:14] == b"\x00\x11"
    assert payload[14:] == b"deadbeef-cafebabe"


def test_decode_login_charlist():
    # isii: id-array(1)=[111], name-array(1)=[b"Bob"], level-array(1)=[220], online-array(1)=[1]
    payload = (
        b"\x00\x01" + b"\x00\x00\x00\x6f"  # i: count=1, [111]
        + b"\x00\x01" + b"\x00\x03" + b"Bob"  # s: count=1, "Bob"
        + b"\x00\x01" + b"\x00\x00\x00\xdc"  # i: count=1, [220]
        + b"\x00\x01" + b"\x00\x00\x00\x01"  # i: count=1, [1]
    )
    args = packet.decode_args(packet.AOCP_LOGIN_CHARLIST, payload)

    assert args[0] == [111]
    assert args[1] == [b"Bob"]
    assert args[2] == [220]
    assert args[3] == [1]


def test_decode_buddy_logonoff():
    payload = struct_pack_helper(packet.AOCP_BUDDY_LOGONOFF, [999, 1, b"\x01"])
    args = packet.decode_args(packet.AOCP_BUDDY_LOGONOFF, payload)

    assert args[0] == 999
    assert args[1] == 1
    assert args[2] == b"\x01"


def test_encode_packet_and_decode_packet_full_round_trip():
    raw = packet.encode_packet(packet.AOCP_MSG_PRIVATE, [42, "hi", "\0"])
    ptype, plen = packet.decode_header(raw[:4])
    decoded = packet.decode_packet(ptype, raw[4 : 4 + plen])

    assert ptype == packet.AOCP_MSG_PRIVATE
    assert decoded.args[0] == 42
    assert decoded.args[1] == b"hi"


def test_decode_client_name():
    payload = struct_pack_helper_client_name(555, b"Alice")
    args = packet.decode_args(packet.AOCP_CLIENT_NAME, payload)

    assert args[0] == 555
    assert args[1] == b"Alice"


def test_unknown_outbound_packet_type_raises():
    with pytest.raises(KeyError):
        packet.encode_args(9999, [])


def struct_pack_helper(packet_type: int, values: list) -> bytes:
    # IIS payload built by hand, mirroring what decode_args expects for BUDDY_LOGONOFF.
    import struct as _struct

    uid, online, btype = values
    return _struct.pack(">I", uid) + _struct.pack(">I", online) + _struct.pack(">H", len(btype)) + btype


def struct_pack_helper_client_name(char_id: int, name: bytes) -> bytes:
    # IS payload, mirroring what decode_args expects for CLIENT_NAME/CLIENT_LOOKUP.
    import struct as _struct

    return _struct.pack(">I", char_id) + _struct.pack(">H", len(name)) + name
