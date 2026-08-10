"""HTTP-level coverage of the auth layer itself, across a representative
sample of player-scoped and global write routes -- see test_routes.py for
per-route business-logic tests (some of which already cover 401/403 for
their own route inline; this file focuses on the auth mechanism generally:
revocation, and every read route staying open)."""

import pytest

from tests.conftest import requires_postgres


@requires_postgres
@pytest.mark.asyncio
async def test_revoked_key_401s(api_client, player_key_factory, _sessionmaker):
    from aomarket.auth.service import AuthService
    from aomarket.db.api_key_repo import ApiKeyRepo
    from aomarket.db.market_repo import MarketRepo

    raw = await player_key_factory("Alice")

    async with _sessionmaker() as session:
        auth = AuthService(repo=ApiKeyRepo(session), market_repo=MarketRepo(session))
        await auth.revoke_keys("Alice")

    response = await api_client.post("/players/Alice/watchlist/2", headers={"X-Api-Key": raw})

    assert response.status_code == 401


@requires_postgres
@pytest.mark.asyncio
async def test_garbage_key_401s(api_client):
    response = await api_client.post("/players/Alice/watchlist/2", headers={"X-Api-Key": "aomk_not-a-real-key"})

    assert response.status_code == 401


@requires_postgres
@pytest.mark.asyncio
async def test_admin_key_can_write_to_any_player(api_client, admin_key, player_key_factory):
    await player_key_factory("Alice")  # registers Alice

    response = await api_client.post("/players/Alice/watchlist/2", headers={"X-Api-Key": admin_key})

    assert response.status_code == 200


@requires_postgres
@pytest.mark.asyncio
async def test_register_stays_unauthenticated(api_client):
    response = await api_client.post("/players/Someone:register")

    assert response.status_code == 200


@requires_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/healthz"),
        ("get", "/readyz"),
        ("get", "/settings"),
        ("get", "/settings/PollIntervalMinutes"),
        ("get", "/items/2"),
        ("get", "/watch"),
        ("get", "/status"),
        ("get", "/bot/status"),
        ("get", "/players/Alice"),
        ("get", "/players/Alice/watchlist"),
        ("get", "/admin/players/Alice/stats"),
    ],
)
async def test_read_routes_stay_open_with_zero_headers(api_client, method, path):
    response = await getattr(api_client, method)(path)

    assert response.status_code != 401
    assert response.status_code != 403
