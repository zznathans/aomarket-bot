import pytest

from aomarket.auth.service import AuthService
from aomarket.bot.admin_commands import handle_admin_command
from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.market.commands import handle_command
from aomarket.market.service import ChatSink, MarketService
from tests.conftest import requires_postgres


class FakeAodbClient:
    async def get_item(self, aoid):
        return None

    async def search_items(self, query, ql=None, limit=50, offset=0):
        return [], 0


class FakeGmiClient:
    async def get_orders(self, aoid):
        return None


async def _make_service(db_session) -> MarketService:
    repo = MarketRepo(db_session)
    settings = SettingsRepo(db_session)
    await settings.seed_defaults()
    return MarketService(
        repo=repo,
        settings=settings,
        aodb=FakeAodbClient(),
        aodb_backoff=AodbBackoffRepo(db_session),
        gmi=FakeGmiClient(),
        chat=ChatSink(),
    )


def _make_admin_auth(db_session, player: str) -> AuthService:
    return AuthService(repo=ApiKeyRepo(db_session), market_repo=MarketRepo(db_session), owner_character=player)


def _make_non_admin_auth(db_session) -> AuthService:
    return AuthService(repo=ApiKeyRepo(db_session), market_repo=MarketRepo(db_session))


@requires_postgres
@pytest.mark.asyncio
async def test_settings_list_shows_all_settings(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "!settings")

    assert reply is not None
    assert "Enabled = False" in reply


@requires_postgres
@pytest.mark.asyncio
async def test_settings_get_known_key(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "!settings PollIntervalMinutes")

    assert reply == "PollIntervalMinutes = 30"


@requires_postgres
@pytest.mark.asyncio
async def test_settings_get_unknown_key(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "!settings Bogus")

    assert "unknown setting" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_settings_set_bool_re_enables_module(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")
    assert await service.settings.get_bool("Enabled") is False

    reply = await handle_admin_command(service, auth, "Admin", "!settings Enabled true")

    assert reply == "Enabled = True"
    assert await service.settings.get_bool("Enabled") is True

    status_reply = await handle_command(service, auth, "Admin", "market status")
    assert "disabled" not in status_reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_settings_set_bool_rejects_truthy_string_bug(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")
    await service.settings.set("Enabled", True)

    reply = await handle_admin_command(service, auth, "Admin", "!settings Enabled false")

    assert reply == "Enabled = False"
    assert await service.settings.get_bool("Enabled") is False


@requires_postgres
@pytest.mark.asyncio
async def test_settings_set_bad_int_value(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "!settings PollIntervalMinutes abc")

    assert "not a valid integer" in reply
    assert await service.settings.get_int("PollIntervalMinutes") == 30


@requires_postgres
@pytest.mark.asyncio
async def test_settings_set_unknown_key(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "!settings Bogus 5")

    assert "unknown setting" in reply.lower()


@requires_postgres
@pytest.mark.asyncio
async def test_non_admin_gets_none(db_session):
    service = await _make_service(db_session)
    auth = _make_non_admin_auth(db_session)

    reply = await handle_admin_command(service, auth, "Alice", "!settings")

    assert reply is None


@requires_postgres
@pytest.mark.asyncio
async def test_non_settings_message_gets_none(db_session):
    service = await _make_service(db_session)
    auth = _make_admin_auth(db_session, "Admin")

    reply = await handle_admin_command(service, auth, "Admin", "hello")

    assert reply is None
