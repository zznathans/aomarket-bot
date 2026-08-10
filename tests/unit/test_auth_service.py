import pytest

from aomarket.auth.service import AuthService
from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo
from tests.conftest import requires_postgres


def _make_service(db_session, owner_character: str = "") -> AuthService:
    return AuthService(
        repo=ApiKeyRepo(db_session),
        market_repo=MarketRepo(db_session),
        owner_character=owner_character,
    )


@requires_postgres
@pytest.mark.asyncio
async def test_generate_key_auto_registers_player(db_session):
    auth = _make_service(db_session)

    await auth.generate_key("Alice")

    assert await MarketRepo(db_session).is_registered("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_generate_key_returns_usable_raw_token(db_session):
    auth = _make_service(db_session)

    raw = await auth.generate_key("Alice")

    principal = await auth.authenticate(raw)
    assert principal is not None
    assert principal.player == "Alice"


@requires_postgres
@pytest.mark.asyncio
async def test_generate_key_twice_revokes_first_key(db_session):
    auth = _make_service(db_session)
    first = await auth.generate_key("Alice")

    second = await auth.generate_key("Alice")

    assert await auth.authenticate(first) is None
    assert (await auth.authenticate(second)).player == "Alice"


@requires_postgres
@pytest.mark.asyncio
async def test_revoke_keys_invalidates_and_returns_count(db_session):
    auth = _make_service(db_session)
    raw = await auth.generate_key("Alice")

    count = await auth.revoke_keys("Alice")

    assert count == 1
    assert await auth.authenticate(raw) is None


@requires_postgres
@pytest.mark.asyncio
async def test_authenticate_unknown_token_returns_none(db_session):
    auth = _make_service(db_session)

    assert await auth.authenticate("aomk_not-a-real-token") is None


@requires_postgres
@pytest.mark.asyncio
async def test_authenticate_non_admin_player_is_not_admin(db_session):
    auth = _make_service(db_session, owner_character="Owner")
    raw = await auth.generate_key("Alice")

    principal = await auth.authenticate(raw)

    assert principal.is_admin is False


@requires_postgres
@pytest.mark.asyncio
async def test_authenticate_owner_character_is_admin(db_session):
    auth = _make_service(db_session, owner_character="Owner")
    raw = await auth.generate_key("Owner")

    principal = await auth.authenticate(raw)

    assert principal.is_admin is True


@requires_postgres
@pytest.mark.asyncio
async def test_authenticate_market_user_is_admin_flag_grants_admin(db_session):
    auth = _make_service(db_session)
    market_repo = MarketRepo(db_session)
    await market_repo.register("Alice")
    user = await market_repo.get_user("Alice")
    user.is_admin = True
    await db_session.commit()

    raw = await auth.generate_key("Alice")

    principal = await auth.authenticate(raw)
    assert principal.is_admin is True


@requires_postgres
@pytest.mark.asyncio
async def test_authenticate_updates_last_used_at(db_session):
    auth = _make_service(db_session)
    raw = await auth.generate_key("Alice")

    await auth.authenticate(raw)

    keys = await auth.list_keys("Alice")
    assert keys[0].last_used_at is not None


@requires_postgres
@pytest.mark.asyncio
async def test_list_keys_returns_players_keys(db_session):
    auth = _make_service(db_session)
    await auth.generate_key("Alice")

    keys = await auth.list_keys("Alice")

    assert len(keys) == 1
    assert keys[0].player == "Alice"
