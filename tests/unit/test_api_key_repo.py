import pytest

from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo
from tests.conftest import requires_postgres


@requires_postgres
@pytest.mark.asyncio
async def test_create_then_get_by_hash_round_trips(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)

    created = await repo.create("Alice", "somehash", "aomk_abc123")

    found = await repo.get_by_hash("somehash")
    assert found is not None
    assert found.id == created.id
    assert found.player == "Alice"
    assert found.prefix == "aomk_abc123"
    assert found.revoked_at is None


@requires_postgres
@pytest.mark.asyncio
async def test_get_by_hash_unknown_returns_none(db_session):
    repo = ApiKeyRepo(db_session)

    assert await repo.get_by_hash("nope") is None


@requires_postgres
@pytest.mark.asyncio
async def test_revoke_all_for_player_excludes_from_get_by_hash(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)
    await repo.create("Alice", "somehash", "aomk_abc123")

    count = await repo.revoke_all_for_player("Alice")

    assert count == 1
    assert await repo.get_by_hash("somehash") is None


@requires_postgres
@pytest.mark.asyncio
async def test_revoke_all_for_player_no_active_keys_returns_zero(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)

    assert await repo.revoke_all_for_player("Alice") == 0


@requires_postgres
@pytest.mark.asyncio
async def test_list_for_player_includes_revoked_newest_first(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)
    await repo.create("Alice", "hash1", "aomk_1")
    await repo.revoke_all_for_player("Alice")
    await repo.create("Alice", "hash2", "aomk_2")

    keys = await repo.list_for_player("Alice")

    assert [k.prefix for k in keys] == ["aomk_2", "aomk_1"]
    assert keys[1].revoked_at is not None
    assert keys[0].revoked_at is None


@requires_postgres
@pytest.mark.asyncio
async def test_list_for_player_no_keys_returns_empty(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)

    assert await repo.list_for_player("Alice") == []


@requires_postgres
@pytest.mark.asyncio
async def test_touch_last_used_sets_timestamp(db_session):
    await MarketRepo(db_session).register("Alice")
    repo = ApiKeyRepo(db_session)
    key = await repo.create("Alice", "somehash", "aomk_abc123")
    assert key.last_used_at is None

    await repo.touch_last_used(key.id)

    found = await repo.get_by_hash("somehash")
    assert found.last_used_at is not None
