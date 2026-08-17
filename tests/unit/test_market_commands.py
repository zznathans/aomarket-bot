import pytest

from aomarket.aodb.client import Item
from aomarket.auth.service import AuthService
from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.api_key_repo import ApiKeyRepo
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
        aodb_backoff=AodbBackoffRepo(db_session),
        gmi=FakeGmiClient(),
        chat=ChatSink(),
    )


def _make_auth(db_session) -> AuthService:
    return AuthService(repo=ApiKeyRepo(db_session), market_repo=MarketRepo(db_session))


@requires_postgres
@pytest.mark.asyncio
async def test_disabled_module_short_circuits(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)
    await service.settings.set("Enabled", False)

    reply = await handle_command(service, auth, "Alice", "market status")

    assert "disabled" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_register_command(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market register")

    assert "registered" in reply.lower()
    assert await service.is_registered("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_register_twice_returns_friendly_error_not_traceback(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)
    await handle_command(service, auth, "Alice", "market register")

    reply = await handle_command(service, auth, "Alice", "market register")

    assert "already registered" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_watch_aoid_without_registration_gives_friendly_error(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market watch 2")

    assert "register" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_watch_aoid_full_flow(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})
    auth = _make_auth(db_session)
    await handle_command(service, auth, "Alice", "market register")

    reply = await handle_command(service, auth, "Alice", "market watch 2")

    assert "Notum Splitter" in reply
    watchlist_reply = await handle_command(service, auth, "Alice", "market watchlist")
    assert "2" in watchlist_reply


@requires_postgres
@pytest.mark.asyncio
async def test_unknown_aoid_overview_gives_friendly_message(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market 999999")

    assert "unknown item" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_search_by_name(db_session):
    service = await _make_service(
        db_session, items={2: _splitter_item()}
    )
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market splitter")

    assert "Notum Splitter" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_status_command(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market status")

    assert "Total tracked" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_unwatch_all_requires_confirm(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market unwatch all")

    assert "confirm" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_filter_price_full_flow(db_session):
    service = await _make_service(db_session, items={2: _splitter_item()})
    auth = _make_auth(db_session)
    await handle_command(service, auth, "Alice", "market register")
    await handle_command(service, auth, "Alice", "market watch 2")

    reply = await handle_command(service, auth, "Alice", "market filter price 2 1m-5m")

    assert "updated" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_unrecognized_command_shows_usage(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market")

    assert "Usage" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_apikey_generate_returns_key_and_registers_player(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market apikey generate")

    assert "aomk_" in reply
    assert await service.is_registered("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_apikey_revoke_requires_confirm(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)
    await handle_command(service, auth, "Alice", "market apikey generate")

    reply = await handle_command(service, auth, "Alice", "market apikey revoke")

    assert "confirm" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_apikey_revoke_confirmed_revokes(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)
    await handle_command(service, auth, "Alice", "market apikey generate")

    reply = await handle_command(service, auth, "Alice", "market apikey revoke confirm")

    assert "revoked 1" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_apikey_list_shows_no_keys_message(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)

    reply = await handle_command(service, auth, "Alice", "market apikey list")

    assert "no api keys" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_apikey_list_shows_generated_key_prefix(db_session):
    service = await _make_service(db_session)
    auth = _make_auth(db_session)
    generate_reply = await handle_command(service, auth, "Alice", "market apikey generate")
    raw_key = generate_reply.split("Your new API key: ")[1].split("\n")[0]

    reply = await handle_command(service, auth, "Alice", "market apikey list")

    assert raw_key[:12] in reply
    assert "active" in reply.lower()
