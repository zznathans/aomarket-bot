"""Proves the run_coroutine_threadsafe cross-thread bridge genuinely works:
a real BotThread with its own event loop, driven from the test's (FastAPI-
like) event loop via asyncio.run_coroutine_threadsafe + asyncio.wrap_future,
producing an observable DB write made from the bot thread. Uses a fake
AOChatClient (no real network) but a real Postgres and a real thread/loop
boundary -- this is the one piece of the concurrency design that's easy to
get subtly wrong and hard to fully unit-test in isolation.
"""

import asyncio
import threading
from datetime import UTC, datetime, timedelta

import pytest

from aomarket.aochat.types import CharacterInfo
from aomarket.aodb.client import Item
from aomarket.bot.runner import BotHandle, MarketBot, bot_thread_main
from aomarket.config import AppConfig
from aomarket.db.engine import make_engine, make_sessionmaker
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import Orders, SellOrder
from tests.conftest import TEST_DATABASE_URL, requires_postgres


class FakeChatClient:
    def __init__(self):
        self.character = CharacterInfo(id=1, name="Testbot", level=220, online=1)
        self.sent_privgroup: list[str] = []

    async def login(self) -> None:
        pass

    def start_background_tasks(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_privgroup(self, gid: int, message: str) -> None:
        self.sent_privgroup.append(message)

    async def send_tell_by_name(self, name: str, message: str) -> None:
        pass

    async def is_online_by_name(self, name: str) -> bool:
        return False


class FakeAodbClient:
    async def get_item(self, aoid: int) -> Item | None:
        return None

    async def search_items(self, query, ql=None, limit=50, offset=0):
        return [], 0


class FakeGmiClient:
    async def get_orders(self, aoid: int):
        return Orders(sell_orders=[SellOrder(price=1000, ql=200, count=1, seller="Bob")], buy_orders=[])


class FakeScraper:
    async def fetch_page(self, source_url: str, page: int):
        return None


@requires_postgres
@pytest.mark.asyncio
async def test_force_poll_now_crosses_thread_boundary_and_writes_to_db(db_session):
    repo = MarketRepo(db_session)
    settings = SettingsRepo(db_session)
    await settings.seed_defaults()
    await repo.upsert_watch(2, "Notum Splitter", 200, 1234)
    watch = await repo.get_watch(2)
    original_last_polled = datetime.now(UTC) - timedelta(days=1)
    watch.last_polled = original_last_polled
    await db_session.commit()

    engine = make_engine(TEST_DATABASE_URL)
    sessionmaker = make_sessionmaker(engine)
    bot = MarketBot(
        config=AppConfig(),
        sessionmaker=sessionmaker,
        aodb=FakeAodbClient(),
        gmi=FakeGmiClient(),
        scraper=FakeScraper(),
        chat_client=FakeChatClient(),
    )
    handle = BotHandle()
    thread = threading.Thread(target=bot_thread_main, args=(handle, bot), daemon=True)
    thread.start()

    assert handle.ready.wait(timeout=10), "bot thread never became ready"
    assert handle.loop is not None

    future = asyncio.run_coroutine_threadsafe(bot.force_poll_now(), handle.loop)
    await asyncio.wrap_future(future)

    db_session.expire_all()
    updated_watch = await repo.get_watch(2)
    assert updated_watch.last_polled > original_last_polled

    stop_future = asyncio.run_coroutine_threadsafe(bot.stop(), handle.loop)
    await asyncio.wrap_future(stop_future)
    handle.loop.call_soon_threadsafe(handle.loop.stop)
    thread.join(timeout=5)
    await engine.dispose()
