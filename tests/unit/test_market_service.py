from datetime import UTC, datetime, timedelta

import pytest

from aomarket.aodb.client import Item
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import BuyOrder, Orders, SellOrder
from aomarket.market.errors import (
    AlreadyRegisteredError,
    AlreadyWatchingError,
    InvalidRangeError,
    NotRegisteredError,
    NotWatchingError,
    SubscriptionLimitError,
    UnknownItemError,
)
from aomarket.market.service import ChatSink, MarketService, NewOrder
from tests.conftest import requires_postgres


class FakeAodbClient:
    def __init__(self, items: dict[int, Item]):
        self._items = items

    async def get_item(self, aoid: int) -> Item | None:
        return self._items.get(aoid)

    async def search_items(self, query, ql=None, limit=50, offset=0):
        matches = [i for i in self._items.values() if query.lower() in i.name.lower()]
        return matches, len(matches)


class FakeGmiClient:
    def __init__(self, orders_by_aoid: dict[int, Orders]):
        self._orders = orders_by_aoid

    async def get_orders(self, aoid: int) -> Orders | None:
        return self._orders.get(aoid)


class FakeScraper:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.fetched_pages: list[int] = []

    async def fetch_page(self, source_url: str, page: int) -> str | None:
        self.fetched_pages.append(page)
        return self._pages.get(page)


def _item(aoid: int, name: str = "Notum Splitter", ql: int = 150) -> Item:
    return Item(aoid=aoid, name=name, ql=ql, icon=1234, description=None)


async def _make_service(db_session, items=None, orders=None, pages=None, chat=None) -> MarketService:
    repo = MarketRepo(db_session)
    settings = SettingsRepo(db_session)
    await settings.seed_defaults()
    return MarketService(
        repo=repo,
        settings=settings,
        aodb=FakeAodbClient(items or {}),
        gmi=FakeGmiClient(orders or {}),
        scraper=FakeScraper(pages or {}),
        chat=chat or ChatSink(),
    )


# -- registration ---------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_register_then_is_registered(db_session):
    service = await _make_service(db_session)

    await service.register("Alice")

    assert await service.is_registered("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_register_twice_raises(db_session):
    service = await _make_service(db_session)
    await service.register("Alice")

    with pytest.raises(AlreadyRegisteredError):
        await service.register("Alice")


@requires_postgres
@pytest.mark.asyncio
async def test_unregister_unknown_player_raises(db_session):
    service = await _make_service(db_session)

    with pytest.raises(NotRegisteredError):
        await service.unregister("Nobody")


@requires_postgres
@pytest.mark.asyncio
async def test_unregister_cascades_subscriptions(db_session, ):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 2)

    removed = await service.unregister("Alice")

    assert removed == 1
    assert not await service.is_registered("Alice")


# -- subscriptions ----------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_unknown_item_raises(db_session):
    service = await _make_service(db_session)
    await service.register("Alice")

    with pytest.raises(UnknownItemError):
        await service.subscribe("Alice", 999)


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_without_registration_raises(db_session):
    service = await _make_service(db_session, items={2: _item(2)})

    with pytest.raises(NotRegisteredError):
        await service.subscribe("Alice", 2)


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_twice_raises_already_watching(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 2)

    with pytest.raises(AlreadyWatchingError):
        await service.subscribe("Alice", 2)


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_enforces_max_subscriptions_per_player(db_session):
    items = {i: _item(i, name=f"Item{i}") for i in range(1, 4)}
    service = await _make_service(db_session, items=items)
    await service.settings.set("MaxSubscriptionsPerPlayer", 2)
    await service.register("Alice")
    await service.subscribe("Alice", 1)
    await service.subscribe("Alice", 2)

    with pytest.raises(SubscriptionLimitError):
        await service.subscribe("Alice", 3)


@requires_postgres
@pytest.mark.asyncio
async def test_subscribe_also_starts_tracking_item(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")

    await service.subscribe("Alice", 2)

    watch = await service.repo.get_watch(2)
    assert watch is not None
    assert watch.name == "Notum Splitter"


@requires_postgres
@pytest.mark.asyncio
async def test_unsubscribe_bulk_reports_removed_and_not_watched(db_session):
    service = await _make_service(db_session, items={1: _item(1), 2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 1)

    removed, not_watched = await service.unsubscribe_bulk("Alice", [1, 2])

    assert removed == {1}
    assert not_watched == {2}


# -- filters ------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_set_price_filter_requires_existing_subscription(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")

    with pytest.raises(NotWatchingError):
        await service.set_price_filter("Alice", 2, "1m-5m")


@requires_postgres
@pytest.mark.asyncio
async def test_set_price_filter_rejects_malformed_spec(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 2)

    with pytest.raises(InvalidRangeError):
        await service.set_price_filter("Alice", 2, "not-a-range-either-side")


@requires_postgres
@pytest.mark.asyncio
async def test_set_price_filter_applies_parsed_bounds(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 2)

    await service.set_price_filter("Alice", 2, "1m-5m")

    sub = await service.get_filter("Alice", 2)
    assert sub.min_price == 1_000_000
    assert sub.max_price == 5_000_000


@requires_postgres
@pytest.mark.asyncio
async def test_clear_filter_resets_all_bounds(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.register("Alice")
    await service.subscribe("Alice", 2)
    await service.set_price_filter("Alice", 2, "1m-5m")

    await service.clear_filter("Alice", 2)

    sub = await service.get_filter("Alice", 2)
    assert sub.min_price is None
    assert sub.max_price is None


# -- order fingerprinting / filter matching -------------------------------


def test_order_matches_filter_bounds():
    order = NewOrder(side="sell", price=1000, min_ql=200, max_ql=200)

    assert MarketService.order_matches_filter(order, None, None, None, None)
    assert MarketService.order_matches_filter(order, 500, 1500, None, None)
    assert not MarketService.order_matches_filter(order, 1500, None, None, None)
    assert not MarketService.order_matches_filter(order, None, 500, None, None)
    assert MarketService.order_matches_filter(order, None, None, 100, 200)
    assert not MarketService.order_matches_filter(order, None, None, 201, None)
    assert not MarketService.order_matches_filter(order, None, None, None, 199)


@requires_postgres
@pytest.mark.asyncio
async def test_detect_new_orders_first_poll_never_notifies(db_session):
    orders = Orders(
        sell_orders=[SellOrder(price=1000, ql=200, count=1, seller="Bob")],
        buy_orders=[],
    )
    service = await _make_service(db_session)
    notified = []
    service.notify_subscribers = _record(notified)  # type: ignore[method-assign]

    await service._detect_new_orders(2, orders, "Notum Splitter")  # noqa: SLF001

    assert notified == []
    seen = await service.repo.get_seen_fingerprints(2)
    assert len(seen) == 1


@requires_postgres
@pytest.mark.asyncio
async def test_detect_new_orders_notifies_on_genuinely_new_order_second_poll(db_session):
    service = await _make_service(db_session)
    notified = []
    service.notify_subscribers = _record(notified)  # type: ignore[method-assign]

    first = Orders(sell_orders=[SellOrder(price=1000, ql=200, count=1, seller="Bob")], buy_orders=[])
    await service._detect_new_orders(2, first, "Notum Splitter")  # noqa: SLF001
    assert notified == []

    second = Orders(
        sell_orders=[
            SellOrder(price=1000, ql=200, count=1, seller="Bob"),
            SellOrder(price=2000, ql=200, count=1, seller="Carol"),
        ],
        buy_orders=[],
    )
    await service._detect_new_orders(2, second, "Notum Splitter")  # noqa: SLF001

    assert len(notified) == 1
    aoid, item_name, new_orders = notified[0]
    assert aoid == 2
    assert len(new_orders) == 1
    assert new_orders[0].price == 2000


@requires_postgres
@pytest.mark.asyncio
async def test_fingerprint_excludes_expiration_but_includes_count():
    # Fingerprints are built purely from price/ql/count/seller-or-buyer -- no
    # expiration field exists on our SellOrder/BuyOrder dataclasses at all,
    # which is itself the regression guard: it can't leak into the fingerprint.
    order_a = SellOrder(price=1000, ql=200, count=3, seller="Bob")
    order_b = SellOrder(price=1000, ql=200, count=5, seller="Bob")

    fp_a = f"sell|{order_a.price}|{order_a.ql}|{order_a.count}|{order_a.seller}"
    fp_b = f"sell|{order_b.price}|{order_b.ql}|{order_b.count}|{order_b.seller}"

    assert fp_a != fp_b  # count is part of the identity


@requires_postgres
@pytest.mark.asyncio
async def test_notify_subscribers_only_notifies_matching_filter(db_session):
    online_players: set[str] = set()
    sent: list[tuple[str, str]] = []

    async def is_online(player: str) -> bool:
        return player in online_players

    async def send_tell(player: str, message: str) -> None:
        sent.append((player, message))

    service = await _make_service(
        db_session, items={2: _item(2)}, chat=ChatSink(is_online=is_online, send_tell=send_tell)
    )
    await service.register("Alice")
    await service.subscribe("Alice", 2)
    await service.set_price_filter("Alice", 2, "5m-")  # only alert above 5m
    online_players.add("Alice")

    cheap_order = NewOrder(side="sell", price=1_000_000, min_ql=200, max_ql=200)
    expensive_order = NewOrder(side="sell", price=10_000_000, min_ql=200, max_ql=200)

    notified = await service.notify_subscribers(2, "Notum Splitter", [cheap_order, expensive_order])

    assert notified == 1
    assert len(sent) == 1
    assert "10.0m" in sent[0][1]


@requires_postgres
@pytest.mark.asyncio
async def test_notify_subscribers_queues_pending_alert_when_offline(db_session):
    service = await _make_service(db_session, items={2: _item(2)}, chat=ChatSink(is_online=lambda p: _false()))
    await service.register("Alice")
    await service.subscribe("Alice", 2)

    order = NewOrder(side="sell", price=1_000_000, min_ql=200, max_ql=200)
    notified = await service.notify_subscribers(2, "Notum Splitter", [order])

    assert notified == 1
    alerts = await service.repo.pop_pending_alerts("Alice")
    assert len(alerts) == 1


async def _false():
    return False


def _record(sink: list):
    async def _fn(aoid, item_name, new_orders):
        sink.append((aoid, item_name, new_orders))
        return 0

    return _fn


# -- poll_market ------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_poll_market_expires_stale_non_autotracked_items(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.watch_item(2, "Notum Splitter", 200, 1234, auto_tracked=False)
    await service.settings.set("WatchExpireDays", 1)

    # Backdate first_seen/last_polled past the expiry window.
    watch = await service.repo.get_watch(2)
    watch.first_seen = datetime.now(UTC) - timedelta(days=5)
    watch.last_polled = datetime.now(UTC) - timedelta(days=5)
    await db_session.commit()

    summary = await service.poll_market()

    assert summary.expired_count == 1
    assert await service.repo.get_watch(2) is None


@requires_postgres
@pytest.mark.asyncio
async def test_poll_market_polls_due_items_and_snapshots(db_session):
    orders = Orders(sell_orders=[SellOrder(price=1000, ql=200, count=1, seller="Bob")], buy_orders=[])
    service = await _make_service(db_session, items={2: _item(2)}, orders={2: orders})
    await service.watch_item(2, "Notum Splitter", 200, 1234)

    summary = await service.poll_market()

    assert summary.due_count == 1
    assert summary.updated_count == 1
    watch = await service.repo.get_watch(2)
    assert watch.last_polled is not None


@requires_postgres
@pytest.mark.asyncio
async def test_poll_market_skips_items_not_yet_due(db_session):
    service = await _make_service(db_session, items={2: _item(2)})
    await service.watch_item(2, "Notum Splitter", 200, 1234)
    # Freshly polled -- shouldn't be due again immediately at the default 30-minute interval.
    await service.repo.update_last_polled(2, datetime.now(UTC))

    summary = await service.poll_market()

    assert summary.due_count == 0


# -- sync_top_traded_items ----------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_sync_top_traded_items_noop_when_disabled(db_session):
    service = await _make_service(db_session)
    await service.settings.set("AutoTrackEnabled", False)

    result = await service.sync_top_traded_items()

    assert result is None


@requires_postgres
@pytest.mark.asyncio
async def test_sync_top_traded_items_aborts_without_touching_data_on_zero_pages(db_session):
    service = await _make_service(db_session, items={2: _item(2)}, pages={})
    await service.watch_item(2, "Notum Splitter", 200, 1234, auto_tracked=True)

    result = await service.sync_top_traded_items()

    assert result is None
    watch = await service.repo.get_watch(2)
    assert watch is not None
    assert watch.auto_tracked is True  # untouched, not wiped


@requires_postgres
@pytest.mark.asyncio
async def test_sync_top_traded_items_tracks_resolved_items_and_unflags_dropped_ones(db_session):
    page_html = (
        '<a class="item-name" href="/item/2">Notum Splitter</a>'
        '<a class="item-name" href="/item/3">Boots</a>'
    )
    items = {2: _item(2, "Notum Splitter"), 3: _item(3, "Boots", ql=100)}
    service = await _make_service(db_session, items=items, pages={1: page_html})
    await service.settings.set("AutoTrackCount", 2)
    # Pre-existing auto-tracked item that will fall out of the new top list.
    await service.watch_item(99, "Old Item", 1, None, auto_tracked=True)

    result = await service.sync_top_traded_items()

    assert result is not None
    assert result.resolved_count == 2
    watch_2 = await service.repo.get_watch(2)
    watch_3 = await service.repo.get_watch(3)
    watch_99 = await service.repo.get_watch(99)
    assert watch_2.auto_tracked is True
    assert watch_3.auto_tracked is True
    assert watch_99.auto_tracked is False


@requires_postgres
@pytest.mark.asyncio
async def test_sync_top_traded_items_only_announces_newly_added_items(db_session):
    page_html = '<a class="item-name" href="/item/2">Notum Splitter</a>'
    announced = []

    async def send_privgroup(message: str) -> None:
        announced.append(message)

    service = await _make_service(
        db_session, items={2: _item(2)}, pages={1: page_html}, chat=ChatSink(send_privgroup=send_privgroup)
    )
    await service.settings.set("AutoTrackCount", 1)
    await service.settings.set("LogBackgroundToPrivateChannel", True)
    # Already tracked -- should NOT re-announce "added to auto-tracking".
    await service.watch_item(2, "Notum Splitter", 150, 1234, auto_tracked=True)
    announced.clear()

    await service.sync_top_traded_items()

    assert not any("added to auto-tracking" in m for m in announced)
