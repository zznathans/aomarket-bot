import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aomarket.aochat.client import AOChatClient
from aomarket.aodb.client import AodbClient
from aomarket.auth.service import AuthService
from aomarket.autotrack.scraper import AutoTrackScraper
from aomarket.bot.scheduler import autotrack_loop, poll_loop
from aomarket.config import AppConfig
from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import GmiClient
from aomarket.logging import get_logger
from aomarket.market.service import ChatSink, MarketService

log = get_logger(__name__)


@dataclass
class BotHandle:
    """The only object shared between the FastAPI thread and the bot thread.
    `loop`/`bot` are published once (before run_forever()/after login), then
    read-only from the API side; `ready` is the memory-barrier for that
    publication."""

    loop: asyncio.AbstractEventLoop | None = None
    bot: "MarketBot | None" = None
    ready: threading.Event = field(default_factory=threading.Event)


class MarketBot:
    def __init__(
        self,
        config: AppConfig,
        sessionmaker: async_sessionmaker[AsyncSession],
        aodb: AodbClient,
        gmi: GmiClient,
        scraper: AutoTrackScraper,
        chat_client: AOChatClient,
    ):
        self.config = config
        self.sessionmaker = sessionmaker
        self.aodb = aodb
        self.gmi = gmi
        self.scraper = scraper
        self.chat_client = chat_client
        self._stopping = False
        self._tasks: list[asyncio.Task] = []
        self.last_poll_at: datetime | None = None
        self.last_autotrack_at: datetime | None = None

    @property
    def connected(self) -> bool:
        return self.chat_client.character is not None

    @asynccontextmanager
    async def make_service(self) -> AsyncIterator[MarketService]:
        session = self.sessionmaker()
        try:
            repo = MarketRepo(session)
            settings = SettingsRepo(session)
            aodb_backoff = AodbBackoffRepo(session)
            chat = ChatSink(
                send_privgroup=self._send_privgroup,
                send_tell=self.chat_client.send_tell_by_name,
                is_online=self.chat_client.is_online_by_name,
            )
            yield MarketService(
                repo=repo,
                settings=settings,
                aodb=self.aodb,
                aodb_backoff=aodb_backoff,
                gmi=self.gmi,
                scraper=self.scraper,
                chat=chat,
            )
        finally:
            await session.close()

    @asynccontextmanager
    async def make_auth_service(self) -> AsyncIterator[AuthService]:
        session = self.sessionmaker()
        try:
            yield AuthService(
                repo=ApiKeyRepo(session),
                market_repo=MarketRepo(session),
                owner_character=self.config.ao_owner_character,
                pepper=self.config.api_key_pepper,
            )
        finally:
            await session.close()

    async def _send_privgroup(self, message: str) -> None:
        gid = self.chat_client.character.id if self.chat_client.character else None
        if gid is not None:
            await self.chat_client.send_privgroup(gid, message)

    async def start(self) -> None:
        await self.chat_client.login()
        self.chat_client.on_tell = self._handle_tell
        self.chat_client.start_background_tasks()
        self._stopping = False
        self._tasks = [
            asyncio.create_task(poll_loop(self)),
            asyncio.create_task(autotrack_loop(self)),
        ]
        log.info("market_bot_started", character=self.chat_client.character)

    async def _handle_tell(self, tell) -> None:
        from aomarket.bot.admin_commands import handle_admin_command
        from aomarket.market.commands import handle_command

        # AOCP_MSG_PRIVATE only carries the sender's numeric character id, not
        # their name -- the AO chat server separately (and asynchronously)
        # pushes an AOCP_CLIENT_NAME packet resolving it, typically around
        # the same time as the tell. name_for_id() returns that once it's
        # arrived; fall back to the numeric id if it hasn't yet (e.g. the
        # very first tell in a session), so a `player` identity is always
        # available even if it doesn't match their display name this once.
        char_id = tell.sender_id
        player = self.chat_client.name_for_id(char_id) or str(char_id)
        log.info("tell_received", player=player, char_id=char_id, message=tell.message)

        async with self.make_service() as service, self.make_auth_service() as auth:
            reply = await handle_admin_command(service, auth, player, tell.message)
            if reply is None:
                reply = await handle_command(service, auth, player, tell.message)
        # Logging reply length rather than content -- some replies (e.g.
        # `market apikey generate`) carry a freshly minted secret token
        # that must never land in logs.
        log.info("tell_reply_sent", player=player, char_id=char_id, reply_length=len(reply))
        await self.chat_client.send_tell(char_id, reply)

    async def stop(self) -> None:
        self._stopping = True
        for task in self._tasks:
            task.cancel()
        await self.chat_client.stop()

    async def force_poll_now(self) -> None:
        async with self.make_service() as service:
            await service.poll_market()
            self.last_poll_at = datetime.now(UTC)

    async def force_autotrack_now(self) -> None:
        async with self.make_service() as service:
            await service.sync_top_traded_items()
            self.last_autotrack_at = datetime.now(UTC)


def bot_thread_main(handle: BotHandle, bot: MarketBot) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    handle.loop = loop
    handle.bot = bot
    try:
        loop.run_until_complete(bot.start())
    except Exception:
        log.exception("market_bot_start_failed")
        loop.close()
        return
    handle.ready.set()
    try:
        loop.run_forever()
    finally:
        loop.close()
