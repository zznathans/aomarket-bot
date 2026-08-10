import asyncio

import pytest

from aomarket.aochat import packet
from aomarket.aochat.client import AOChatClient, AOChatLoginError
from aomarket.aochat.types import InboundTell


class FakeConnection:
    """Stands in for AOChatConnection: pre-loaded inbound packet queue,
    records outbound send_packet calls, no real socket I/O."""

    def __init__(self, inbound: list[packet.InboundPacket]):
        self._inbound = list(inbound)
        self.sent: list[tuple[int, list]] = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def read_packet(self) -> packet.InboundPacket:
        if not self._inbound:
            raise asyncio.IncompleteReadError(partial=b"", expected=4)
        return self._inbound.pop(0)

    async def send_packet(self, packet_type: int, args: list) -> None:
        self.sent.append((packet_type, args))


def _charlist_packet() -> packet.InboundPacket:
    return packet.InboundPacket(
        type=packet.AOCP_LOGIN_CHARLIST,
        args=[[111], [b"Testchar"], [220], [1]],
    )


def _make_client(inbound: list[packet.InboundPacket], character_name: str = "Testchar") -> AOChatClient:
    client = AOChatClient(
        host="unused",
        port=0,
        username="user",
        password="pass",
        character_name=character_name,
    )
    client._conn = FakeConnection(inbound)  # noqa: SLF001
    return client


@pytest.mark.asyncio
async def test_login_happy_path_selects_configured_character():
    inbound = [
        packet.InboundPacket(type=packet.AOCP_LOGIN_SEED, args=[b"serverseed"]),
        _charlist_packet(),
        packet.InboundPacket(type=packet.AOCP_LOGIN_OK, args=[]),
    ]
    client = _make_client(inbound)

    await client.login()

    assert client.character is not None
    assert client.character.name == "Testchar"
    assert client.character.id == 111

    sent_types = [t for t, _ in client._conn.sent]  # noqa: SLF001
    assert sent_types == [packet.AOCP_LOGIN_REQUEST, packet.AOCP_LOGIN_SELECT]


@pytest.mark.asyncio
async def test_login_raises_on_login_error_packet():
    inbound = [
        packet.InboundPacket(type=packet.AOCP_LOGIN_SEED, args=[b"serverseed"]),
        packet.InboundPacket(type=packet.AOCP_LOGIN_ERROR, args=[b"Account system denies login"]),
    ]
    client = _make_client(inbound)

    with pytest.raises(AOChatLoginError, match="login rejected"):
        await client.login()


@pytest.mark.asyncio
async def test_login_raises_when_configured_character_not_in_charlist():
    inbound = [
        packet.InboundPacket(type=packet.AOCP_LOGIN_SEED, args=[b"serverseed"]),
        _charlist_packet(),
    ]
    client = _make_client(inbound, character_name="Someoneelse")

    with pytest.raises(AOChatLoginError, match="not found"):
        await client.login()


@pytest.mark.asyncio
async def test_dispatch_msg_private_invokes_on_tell_handler():
    received: list[InboundTell] = []

    async def handler(tell: InboundTell) -> None:
        received.append(tell)

    client = _make_client([])
    client.on_tell = handler

    pkt = packet.InboundPacket(type=packet.AOCP_MSG_PRIVATE, args=[555, b"market status", b"\0"])
    await client._dispatch(pkt)  # noqa: SLF001

    assert len(received) == 1
    assert received[0].sender_id == 555
    assert received[0].message == "market status"


@pytest.mark.asyncio
async def test_dispatch_client_lookup_resolves_pending_future():
    client = _make_client([])
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    client._lookup_waiters["testchar"] = future  # noqa: SLF001

    pkt = packet.InboundPacket(type=packet.AOCP_CLIENT_LOOKUP, args=[123, b"Testchar"])
    await client._dispatch(pkt)  # noqa: SLF001

    assert future.result() == 123


@pytest.mark.asyncio
async def test_dispatch_client_lookup_no_such_character_resolves_none():
    client = _make_client([])
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    client._lookup_waiters["nobody"] = future  # noqa: SLF001

    pkt = packet.InboundPacket(type=packet.AOCP_CLIENT_LOOKUP, args=[0xFFFFFFFF, b"Nobody"])
    await client._dispatch(pkt)  # noqa: SLF001

    assert future.result() is None


@pytest.mark.asyncio
async def test_dispatch_client_name_populates_id_to_name_cache():
    client = _make_client([])

    pkt = packet.InboundPacket(type=packet.AOCP_CLIENT_NAME, args=[555, b"Alice"])
    await client._dispatch(pkt)  # noqa: SLF001

    assert client.name_for_id(555) == "Alice"


@pytest.mark.asyncio
async def test_dispatch_client_name_no_such_character_not_cached():
    client = _make_client([])

    pkt = packet.InboundPacket(type=packet.AOCP_CLIENT_NAME, args=[0xFFFFFFFF, b"Nobody"])
    await client._dispatch(pkt)  # noqa: SLF001

    assert client.name_for_id(0xFFFFFFFF) is None


def test_name_for_id_unresolved_returns_none():
    client = _make_client([])

    assert client.name_for_id(999) is None


@pytest.mark.asyncio
async def test_buddy_add_skips_self():
    client = _make_client([
        packet.InboundPacket(type=packet.AOCP_LOGIN_SEED, args=[b"serverseed"]),
        _charlist_packet(),
        packet.InboundPacket(type=packet.AOCP_LOGIN_OK, args=[]),
    ])
    await client.login()
    client._conn.sent.clear()  # noqa: SLF001

    await client.buddy_add(111)  # 111 is our own selected character's id

    assert client._conn.sent == []  # noqa: SLF001
