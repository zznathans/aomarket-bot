"""AO chat packet framing and argument codecs.

Ported from BeBot's Sources/AoChatPacket.php. Only the subset of packet
types Market needs is implemented (see AOCP_* below) -- guild, duel,
group/vicinity chat, clientmode, forward/CC/admin-mux packets are
intentionally excluded.
"""

import struct
from dataclasses import dataclass
from typing import Any

HEADER = struct.Struct(">HH")  # (type, length), matches PHP unpack("n2", $head)

# Packet type IDs (Sources/AoChat.php:85-123). LOGIN_SEED (in) and
# LOGIN_CHARID (out) share id 0; distinguished by direction, not value.
AOCP_LOGIN_SEED = 0
AOCP_LOGIN_REQUEST = 2
AOCP_LOGIN_SELECT = 3
AOCP_LOGIN_OK = 5
AOCP_LOGIN_ERROR = 6
AOCP_LOGIN_CHARLIST = 7
AOCP_CLIENT_NAME = 20
AOCP_CLIENT_LOOKUP = 21
AOCP_MSG_PRIVATE = 30
AOCP_BUDDY_LOGONOFF = 40  # incoming
AOCP_BUDDY_ADD = 40  # outgoing
AOCP_BUDDY_REMOVE = 41
AOCP_PRIVGRP_CLIJOIN = 55
AOCP_PRIVGRP_CLIPART = 56
AOCP_PRIVGRP_MESSAGE = 57
AOCP_PING = 100

# Argument schemas, "in" (server->client) and "out" (client->server), copied
# from AoChatPacket.php's $GLOBALS["aochat-packetmap"] for AOCHAT_GAME=='ao'
# (aocpdifs = ["IS", "IIS", "IS", "s"]). Only entries Market needs are kept.
IN_SCHEMAS: dict[int, str] = {
    AOCP_LOGIN_SEED: "S",
    AOCP_LOGIN_OK: "",
    AOCP_LOGIN_ERROR: "S",
    AOCP_LOGIN_CHARLIST: "isii",
    AOCP_CLIENT_LOOKUP: "IS",
    AOCP_MSG_PRIVATE: "ISS",
    AOCP_BUDDY_LOGONOFF: "IIS",  # aocpdifs[1] for AO
    AOCP_PRIVGRP_CLIJOIN: "II",
    AOCP_PRIVGRP_CLIPART: "II",
    AOCP_PRIVGRP_MESSAGE: "IISS",
    AOCP_PING: "S",
}

OUT_SCHEMAS: dict[int, str] = {
    AOCP_LOGIN_REQUEST: "ISS",
    AOCP_LOGIN_SELECT: "I",
    AOCP_CLIENT_LOOKUP: "S",
    AOCP_MSG_PRIVATE: "ISS",
    AOCP_BUDDY_ADD: "IS",  # aocpdifs[2] for AO
    AOCP_PRIVGRP_MESSAGE: "ISS",
    AOCP_PING: "S",
}


@dataclass
class InboundPacket:
    type: int
    args: list[Any]


def encode_header(packet_type: int, payload_len: int) -> bytes:
    return HEADER.pack(packet_type, payload_len)


def decode_header(data: bytes) -> tuple[int, int]:
    return HEADER.unpack(data)


def encode_args(packet_type: int, args: list[Any]) -> bytes:
    """Encode outbound packet arguments per OUT_SCHEMAS (AoChatPacket.php:307-346)."""
    schema = OUT_SCHEMAS[packet_type]
    remaining = list(args)
    out = bytearray()
    for code in schema:
        value = remaining.pop(0)
        if code == "I":
            out += struct.pack(">I", value)
        elif code == "S":
            data = value.encode() if isinstance(value, str) else bytes(value)
            out += struct.pack(">H", len(data)) + data
        else:
            raise ValueError(f"Unsupported outbound arg type {code!r} for packet {packet_type}")
    return bytes(out)


def decode_args(packet_type: int, data: bytes) -> list[Any]:
    """Decode inbound packet arguments per IN_SCHEMAS (AoChatPacket.php:251-306)."""
    schema = IN_SCHEMAS[packet_type]
    args: list[Any] = []
    offset = 0
    for code in schema:
        if code == "I":
            (value,) = struct.unpack_from(">I", data, offset)
            args.append(value)
            offset += 4
        elif code == "S":
            (length,) = struct.unpack_from(">H", data, offset)
            offset += 2
            args.append(data[offset : offset + length])
            offset += length
        elif code == "i":
            (count,) = struct.unpack_from(">H", data, offset)
            offset += 2
            values = list(struct.unpack_from(f">{count}I", data, offset))
            args.append(values)
            offset += 4 * count
        elif code == "s":
            (count,) = struct.unpack_from(">H", data, offset)
            offset += 2
            values = []
            for _ in range(count):
                (slen,) = struct.unpack_from(">H", data, offset)
                offset += 2
                values.append(data[offset : offset + slen])
                offset += slen
            args.append(values)
        else:
            raise ValueError(f"Unsupported inbound arg type {code!r} for packet {packet_type}")
    return args


def encode_packet(packet_type: int, args: list[Any]) -> bytes:
    payload = encode_args(packet_type, args)
    return encode_header(packet_type, len(payload)) + payload


def decode_packet(packet_type: int, payload: bytes) -> InboundPacket:
    return InboundPacket(type=packet_type, args=decode_args(packet_type, payload))
