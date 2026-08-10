from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest_asyncio

from aomarket.aodb.client import Item
from aomarket.api.app import create_app
from aomarket.auth.service import AuthService
from aomarket.autotrack.scraper import AutoTrackScraper
from aomarket.config import AppConfig
from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.engine import make_engine, make_sessionmaker
from aomarket.db.market_repo import MarketRepo
from aomarket.db.models import Base
from aomarket.gmi.client import Orders, SellOrder
from tests.conftest import TEST_DATABASE_URL

# Bootstrap admin for tests -- matches the `config` passed into create_app
# in the `api_client` fixture below.
OWNER_CHARACTER = "Owner"


class FakeAodbClient:
    def __init__(self):
        self.items: dict[int, Item] = {
            2: Item(aoid=2, name="Notum Splitter", ql=150, icon=54321, description=None),
        }

    async def get_item(self, aoid: int) -> Item | None:
        return self.items.get(aoid)

    async def search_items(self, query: str, ql=None, limit=50, offset=0):
        matches = [i for i in self.items.values() if query.lower() in i.name.lower()]
        return matches, len(matches)


class FakeGmiClient:
    async def get_orders(self, aoid: int):
        return Orders(sell_orders=[SellOrder(price=1000, ql=150, count=1, seller="Bob")], buy_orders=[])


@pytest_asyncio.fixture
async def _sessionmaker():
    """Shared by api_client and the key-minting fixtures below, so they all
    operate against the same freshly-created schema."""
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as seed_session:
        from aomarket.db.settings_repo import SettingsRepo

        await SettingsRepo(seed_session).seed_defaults()

    yield sessionmaker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        sessionmaker=_sessionmaker,
        aodb=FakeAodbClient(),
        gmi=FakeGmiClient(),
        scraper=AutoTrackScraper(),
        config=AppConfig(ao_owner_character=OWNER_CHARACTER),
        bot_handle=None,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def player_key_factory(_sessionmaker) -> Callable[[str], Awaitable[str]]:
    """player_key_factory("Alice") -> raw API key for Alice, auto-registering
    her if needed -- mints through the real AuthService, not a test-only
    bypass, so tests exercise the actual code path."""

    async def _make(player: str) -> str:
        async with _sessionmaker() as session:
            auth = AuthService(repo=ApiKeyRepo(session), market_repo=MarketRepo(session))
            return await auth.generate_key(player)

    return _make


@pytest_asyncio.fixture
async def admin_key(player_key_factory) -> str:
    """A key for OWNER_CHARACTER, matching api_client's ao_owner_character."""
    return await player_key_factory(OWNER_CHARACTER)
