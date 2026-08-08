from collections.abc import AsyncIterator

import httpx
import pytest_asyncio

from aomarket.aodb.client import Item
from aomarket.api.app import create_app
from aomarket.autotrack.scraper import AutoTrackScraper
from aomarket.db.engine import make_engine, make_sessionmaker
from aomarket.db.models import Base
from aomarket.gmi.client import Orders, SellOrder
from tests.conftest import TEST_DATABASE_URL


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
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as seed_session:
        from aomarket.db.settings_repo import SettingsRepo

        await SettingsRepo(seed_session).seed_defaults()

    app = create_app(
        sessionmaker=sessionmaker,
        aodb=FakeAodbClient(),
        gmi=FakeGmiClient(),
        scraper=AutoTrackScraper(),
        bot_handle=None,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
