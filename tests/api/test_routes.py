import pytest

from tests.conftest import requires_postgres


@requires_postgres
@pytest.mark.asyncio
async def test_healthz_reports_db_ok_and_bot_not_connected(api_client):
    response = await api_client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["db_ok"] is True
    assert body["bot_connected"] is False


@requires_postgres
@pytest.mark.asyncio
async def test_readyz_false_when_no_bot_handle(api_client):
    response = await api_client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"ready": False}


@requires_postgres
@pytest.mark.asyncio
async def test_list_settings_returns_seeded_defaults(api_client):
    response = await api_client.get("/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["Enabled"] is False
    assert body["PollIntervalMinutes"] == 30


@requires_postgres
@pytest.mark.asyncio
async def test_get_unknown_setting_404s(api_client):
    response = await api_client.get("/settings/NotReal")

    assert response.status_code == 404


@requires_postgres
@pytest.mark.asyncio
async def test_update_setting_round_trips(api_client):
    response = await api_client.put("/settings/PollIntervalMinutes", json={"value": 45})

    assert response.status_code == 200
    assert response.json() == {"key": "PollIntervalMinutes", "value": 45}

    follow_up = await api_client.get("/settings/PollIntervalMinutes")
    assert follow_up.json()["value"] == 45


@requires_postgres
@pytest.mark.asyncio
async def test_get_item_proxies_aodb(api_client):
    response = await api_client.get("/items/2")

    assert response.status_code == 200
    assert response.json()["name"] == "Notum Splitter"


@requires_postgres
@pytest.mark.asyncio
async def test_get_unknown_item_404s(api_client):
    response = await api_client.get("/items/999999")

    assert response.status_code == 404


@requires_postgres
@pytest.mark.asyncio
async def test_start_watching_then_appears_in_watch_list(api_client):
    response = await api_client.post("/watch/2")
    assert response.status_code == 200

    listing = await api_client.get("/watch")
    assert listing.status_code == 200
    aoids = [row["aoid"] for row in listing.json()]
    assert 2 in aoids


@requires_postgres
@pytest.mark.asyncio
async def test_watch_unknown_item_returns_404(api_client):
    response = await api_client.post("/watch/999999")

    assert response.status_code == 404


@requires_postgres
@pytest.mark.asyncio
async def test_full_registration_and_subscription_flow(api_client):
    register = await api_client.post("/players/Alice:register")
    assert register.status_code == 200
    assert register.json() == {"player": "Alice", "registered": True}

    duplicate = await api_client.post("/players/Alice:register")
    assert duplicate.status_code == 409

    subscribe = await api_client.post("/players/Alice/watchlist/2")
    assert subscribe.status_code == 200

    watchlist = await api_client.get("/players/Alice/watchlist")
    assert watchlist.status_code == 200
    assert len(watchlist.json()) == 1
    assert watchlist.json()[0]["aoid"] == 2

    filter_update = await api_client.put(
        "/players/Alice/watchlist/2/filter", json={"price_spec": "1m-5m"}
    )
    assert filter_update.status_code == 200
    assert filter_update.json()["min_price"] == 1_000_000
    assert filter_update.json()["max_price"] == 5_000_000

    unsubscribe = await api_client.delete("/players/Alice/watchlist/2")
    assert unsubscribe.status_code == 204

    unregister_needs_confirm = await api_client.post("/players/Alice:unregister", json={"confirm": False})
    assert unregister_needs_confirm.status_code == 400

    unregister = await api_client.post("/players/Alice:unregister", json={"confirm": True})
    assert unregister.status_code == 200
    assert unregister.json()["subscriptions_removed"] == 0


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_without_registration_returns_400(api_client):
    response = await api_client.post("/players/Bob/watchlist/2")

    assert response.status_code == 400


@requires_postgres
@pytest.mark.asyncio
async def test_admin_untrack_all_requires_confirm(api_client):
    await api_client.post("/watch/2")

    without_confirm = await api_client.post("/admin/watch:untrack_all", json={"confirm": False})
    assert without_confirm.status_code == 400

    with_confirm = await api_client.post("/admin/watch:untrack_all", json={"confirm": True})
    assert with_confirm.status_code == 200
    assert with_confirm.json()["cleared"] == 1


@requires_postgres
@pytest.mark.asyncio
async def test_status_summary_reflects_tracked_items(api_client):
    await api_client.post("/watch/2")

    response = await api_client.get("/status")

    assert response.status_code == 200
    body = response.json()
    assert body["total_tracked"] == 1
    assert body["manually_tracked"] == 1


@requires_postgres
@pytest.mark.asyncio
async def test_bot_status_reports_not_connected_without_handle(api_client):
    response = await api_client.get("/bot/status")

    assert response.status_code == 200
    assert response.json()["connected"] is False


@requires_postgres
@pytest.mark.asyncio
async def test_bot_trigger_poll_503s_without_bot_handle(api_client):
    response = await api_client.post("/bot/poll:trigger")

    assert response.status_code == 503
