import pytest

from aomarket.aodb.client import Item
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import Orders, SellOrder
from aomarket.market.commands import handle_command
from aomarket.market.service import ChatSink, MarketService
from tests.conftest import requires_postgres


class FakeAodbClient:
    def __init__(self, items):
        self._items = items

    async def get_item(self, aoid):
        return self._items.get(aoid)

    async def search_items(self, query, ql=None, limit=50, offset=0):
        matches = [i for i in self._items.values() if query.lower() in i.name.lower()]
        return matches, len(matches)


class FakeGmiClient:
    async def get_orders(self, aoid):
        return Orders(sell_orders=[SellOrder(price=1000, ql=150, count=1, seller="Bob")], buy_orders=[])


def _splitter_item() -> Item:
    return Item(aoid=2, name="Notum Splitter", ql=150, icon=1, description=None)


async def _make_service(db_session, items=None):
    repo = MarketRepo(db_session)
    settings = SettingsRepo(db_session)
    await settings.seed_defaults()
    await settings.set("Enabled", True)
    return MarketService(
        repo=repo,
        settings=settings,
        aodb=FakeAodbClient(items or {}),
        gmi=FakeGmiClient(),
        chat=ChatSink(),
    )


@requires_postgres
@pytest.mark.asyncio
async def test_disabled_module_short_circuits(db_session):
    service = await _make_service(db_session)
    await service.settings.set("Enabled", False)

    reply = await handle_command(service, "Alice", "market status")

    assert "disabled" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_register_command(db_session):
    service = await _make_service(db_session)

    reply = await handle_command(service, "Alice", "market register")

    assert "registered" in reply.lower()
    assert await service.is_registered("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_register_twice_returns_friendly_error_not_traceback(db_session):
    service = await _make_service(db_session)
    await handle_command(service, "Alice", "market register")

    reply = await handle_command(service, "Alice", "market register")

    assert "already registered" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_watch_aoid_without_registration_gives_friendly_error(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})

    reply = await handle_command(service, "Alice", "market watch 2")

    assert "register" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_watch_aoid_full_flow(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})
    await handle_command(service, "Alice", "market register")

    reply = await handle_command(service, "Alice", "market watch 2")

    assert "Notum Splitter" in reply
    watchlist_reply = await handle_command(service, "Alice", "market watchlist")
    assert "2" in watchlist_reply


@requires_postgres
@pytest.mark.asyncio
async def test_unknown_aoid_overview_gives_friendly_message(db_session):
    service = await _make_service(db_session)

    reply = await handle_command(service, "Alice", "market 999999")

    assert "unknown item" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_search_by_name(db_session):
    service = await _make_service(
        db_session, items={2: _splitter_item()}
    )

    reply = await handle_command(service, "Alice", "market splitter")

    assert "Notum Splitter" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_status_command(db_session):
    service = await _make_service(db_session)

    reply = await handle_command(service, "Alice", "market status")

    assert "Total tracked" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_unwatch_all_requires_confirm(db_session):
    service = await _make_service(db_session)

    reply = await handle_command(service, "Alice", "market unwatch all")

    assert "confirm" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_filter_price_full_flow(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})
    await handle_command(service, "Alice", "market register")
    await handle_command(service, "Alice", "market watch 2")

    reply = await handle_command(service, "Alice", "market filter price 2 1m-5m")

    assert "updated" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_unrecognized_command_shows_usage(db_session):
    service = await _make_service(db_session)

    reply = await handle_command(service, "Alice", "market")

    assert "Usage" in reply
