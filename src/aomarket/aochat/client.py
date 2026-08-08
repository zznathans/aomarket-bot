"""High-level AO chat session: login sequence, keepalive, inbound dispatch.

Login sequence ported from AoChat.php::connect()/authenticate()/login()
(AoChat.php:221-555): wait for LOGIN_SEED -> send LOGIN_REQUEST with the
DH+TEA-derived key -> receive LOGIN_CHARLIST -> send LOGIN_SELECT for the
configured character -> receive LOGIN_OK.

Only the packet types Market needs are dispatched (see aochat/packet.py's
IN_SCHEMAS) -- guild/duel/group chat and friends are out of scope.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aomarket.aochat import crypto, packet
from aomarket.aochat.protocol import AOChatConnection
from aomarket.aochat.types import BuddyStatus, CharacterInfo, InboundPrivgroupMessage, InboundTell
from aomarket.logging import get_logger

log = get_logger(__name__)

PING_INTERVAL_SECONDS = 60
_TEXT_ENCODING = "latin-1"  # permissive, never raises; AO chat text isn't UTF-8


class AOChatLoginError(Exception):
    pass


TellHandler = Callable[[InboundTell], Awaitable[None]]
PrivgroupHandler = Callable[[InboundPrivgroupMessage], Awaitable[None]]
BuddyHandler = Callable[[BuddyStatus], Awaitable[None]]


@dataclass
class AOChatClient:
    host: str
    port: int
    username: str
    password: str
    character_name: str

    on_tell: TellHandler | None = None
    on_privgroup_message: PrivgroupHandler | None = None
    on_buddy_status: BuddyHandler | None = None

    _conn: AOChatConnection = field(init=False, repr=False)
    _characters: list[CharacterInfo] = field(default_factory=list, init=False, repr=False)
    _selected_character: CharacterInfo | None = field(default=None, init=False, repr=False)
    _reader_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _keepalive_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _lookup_waiters: dict[str, asyncio.Future] = field(default_factory=dict, init=False, repr=False)
    _stopping: bool = field(default=False, init=False, repr=False)
    buddy_online: dict[int, bool] = field(default_factory=dict, init=False, repr=False)
    _name_to_id: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._conn = AOChatConnection(self.host, self.port)

    @property
    def character(self) -> CharacterInfo | None:
        return self._selected_character

    async def login(self) -> None:
        await self._conn.connect()

        seed_packet = await self._conn.read_packet()
        if seed_packet.type != packet.AOCP_LOGIN_SEED:
            raise AOChatLoginError(f"expected LOGIN_SEED, got type {seed_packet.type}")
        server_seed: bytes = seed_packet.args[0]

        key = crypto.generate_login_key(server_seed, self.username, self.password)
        await self._conn.send_packet(packet.AOCP_LOGIN_REQUEST, [0, self.username, key])

        charlist_packet = await self._conn.read_packet()
        if charlist_packet.type == packet.AOCP_LOGIN_ERROR:
            reason = charlist_packet.args[0].decode(_TEXT_ENCODING, errors="replace")
            raise AOChatLoginError(f"login rejected: {reason}")
        if charlist_packet.type != packet.AOCP_LOGIN_CHARLIST:
            raise AOChatLoginError(f"expected LOGIN_CHARLIST, got type {charlist_packet.type}")

        ids, names, levels, online_flags = charlist_packet.args
        self._characters = [
            CharacterInfo(id=i, name=n.decode(_TEXT_ENCODING).capitalize(), level=lvl, online=on)
            for i, n, lvl, on in zip(ids, names, levels, online_flags, strict=True)
        ]

        target_name = self.character_name.capitalize()
        selected = next((c for c in self._characters if c.name == target_name), None)
        if selected is None:
            raise AOChatLoginError(f"character {self.character_name!r} not found in account character list")

        await self._conn.send_packet(packet.AOCP_LOGIN_SELECT, [selected.id])
        ok_packet = await self._conn.read_packet()
        if ok_packet.type != packet.AOCP_LOGIN_OK:
            raise AOChatLoginError(f"expected LOGIN_OK, got type {ok_packet.type}")

        self._selected_character = selected
        log.info("ao_login_ok", character=selected.name, char_id=selected.id)

    def start_background_tasks(self) -> None:
        self._reader_task = asyncio.get_running_loop().create_task(self._read_loop())
        self._keepalive_task = asyncio.get_running_loop().create_task(self._keepalive_loop())

    async def stop(self) -> None:
        self._stopping = True
        for task in (self._reader_task, self._keepalive_task):
            if task is not None:
                task.cancel()
        await self._conn.close()

    async def send_tell(self, char_id: int, message: str) -> None:
        await self._conn.send_packet(packet.AOCP_MSG_PRIVATE, [char_id, message, "\0"])

    async def send_privgroup(self, gid: int, message: str) -> None:
        await self._conn.send_packet(packet.AOCP_PRIVGRP_MESSAGE, [gid, message, "\0"])

    async def buddy_add(self, char_id: int, buddy_type: str = "\x01") -> None:
        if self._selected_character is not None and char_id == self._selected_character.id:
            return
        await self._conn.send_packet(packet.AOCP_BUDDY_ADD, [char_id, buddy_type])

    async def lookup_user(self, name: str, timeout: float = 10.0) -> int | None:
        """Resolve a character name to its numeric id via AOCP_CLIENT_LOOKUP."""
        cached = self._name_to_id.get(name.lower())
        if cached is not None:
            return cached
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        key = name.lower()
        self._lookup_waiters[key] = future
        try:
            await self._conn.send_packet(packet.AOCP_CLIENT_LOOKUP, [name])
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return None
        finally:
            self._lookup_waiters.pop(key, None)

    async def send_tell_by_name(self, name: str, message: str) -> None:
        char_id = await self.lookup_user(name)
        if char_id is not None:
            await self.send_tell(char_id, message)

    async def is_online_by_name(self, name: str) -> bool:
        char_id = await self.lookup_user(name)
        if char_id is None:
            return False
        await self.buddy_add(char_id)
        return self.buddy_online.get(char_id, False)

    async def _read_loop(self) -> None:
        while not self._stopping:
            try:
                pkt = await self._conn.read_packet()
            except (asyncio.IncompleteReadError, ConnectionError):
                log.warning("ao_connection_lost")
                return
            await self._dispatch(pkt)

    async def _dispatch(self, pkt: packet.InboundPacket) -> None:
        if pkt.type == packet.AOCP_MSG_PRIVATE:
            sender_id, message, _blob = pkt.args
            if self.on_tell is not None:
                await self.on_tell(InboundTell(sender_id=sender_id, message=message.decode(_TEXT_ENCODING)))
        elif pkt.type == packet.AOCP_PRIVGRP_MESSAGE:
            _gid, sender_id, message, _blob = pkt.args
            if self.on_privgroup_message is not None:
                await self.on_privgroup_message(
                    InboundPrivgroupMessage(sender_id=sender_id, message=message.decode(_TEXT_ENCODING))
                )
        elif pkt.type == packet.AOCP_BUDDY_LOGONOFF:
            char_id, online, _btype = pkt.args
            self.buddy_online[char_id] = bool(online)
            if self.on_buddy_status is not None:
                await self.on_buddy_status(BuddyStatus(char_id=char_id, online=bool(online)))
        elif pkt.type == packet.AOCP_CLIENT_LOOKUP:
            char_id, name = pkt.args
            decoded_name = name.decode(_TEXT_ENCODING)
            resolved = None if char_id == 0xFFFFFFFF else char_id
            if resolved is not None:
                self._name_to_id[decoded_name.lower()] = resolved
            future = self._lookup_waiters.get(decoded_name.lower())
            if future is not None and not future.done():
                future.set_result(resolved)
        # AOCP_PING / AOCP_LOGIN_* / privgroup join-part: no-op, nothing Market needs.

    async def _keepalive_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            try:
                await self._conn.send_packet(packet.AOCP_PING, ["aomarket-bot"])
            except ConnectionError:
                log.warning("ao_keepalive_send_failed")
                return
