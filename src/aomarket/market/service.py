"""MarketService: transport-agnostic market business logic. No knowledge of
chat or HTTP -- callers (chat commands, API routes) adapt its typed
results/exceptions to their own presentation. Optional `ChatSink`
callbacks are the only side channel out, used for the
announce()/announce_background() private-channel logging and for delivering
watchlist alert tells; all left as no-ops when unset (e.g. bot not yet
connected, or pure API/test usage).
"""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from aomarket.aodb.client import AodbClient, Item
from aomarket.autotrack.scraper import AutoTrackScraper, extract_aoids
from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import GmiClient, Orders
from aomarket.logging import get_logger
from aomarket.market import parsing
from aomarket.market.errors import (
    AlreadyRegisteredError,
    AlreadyWatchingError,
    InvalidRangeError,
    NotRegisteredError,
    NotWatchingError,
    SubscriptionLimitError,
    UnknownItemError,
)

log = get_logger(__name__)

_MAX_AUTOTRACK_PAGES = 50


@dataclass
class ChatSink:
    send_privgroup: Callable[[str], Awaitable[None]] | None = None
    send_tell: Callable[[str, str], Awaitable[None]] | None = None
    is_online: Callable[[str], Awaitable[bool]] | None = None


@dataclass
class NewOrder:
    side: str  # "sell" | "buy"
    price: int
    min_ql: int
    max_ql: int


@dataclass
class PollSummary:
    due_count: int
    updated_count: int
    expired_count: int


@dataclass
class AutoTrackSummary:
    pages_fetched: int
    ranked_count: int
    resolved_count: int


@dataclass
class MarketService:
    repo: MarketRepo
    settings: SettingsRepo
    aodb: AodbClient
    aodb_backoff: AodbBackoffRepo
    gmi: GmiClient
    scraper: AutoTrackScraper = field(default_factory=AutoTrackScraper)
    chat: ChatSink = field(default_factory=ChatSink)

    # -- announce/log ----------------------------------------------------

    async def announce(self, player: str, action: str, aoid: int | None = None) -> None:
        if not await self.settings.get_bool("LogToPrivateChannel"):
            return
        label = action.replace("_", " ")
        suffix = ""
        if aoid is not None:
            item = await self.aodb.get_item(aoid)
            suffix = f" ({item.name})" if item is not None else f" (AOID {aoid})"
        await self._send_privgroup(f"{player} used market {label}{suffix}")

    async def announce_background(self, message: str) -> None:
        if not await self.settings.get_bool("LogBackgroundToPrivateChannel"):
            return
        await self._send_privgroup(f"Market: {message}")

    async def announce_tracked(self, item_name: str, source: str) -> None:
        if source == "auto":
            await self.announce_background(f"{item_name} added to auto-tracking")
            return
        if not await self.settings.get_bool("LogToPrivateChannel"):
            return
        await self._send_privgroup(f"{item_name} added to tracking (manual)")

    async def _send_privgroup(self, message: str) -> None:
        if self.chat.send_privgroup is not None:
            await self.chat.send_privgroup(message)

    async def log_action(self, player: str, action: str, aoid: int | None = None) -> None:
        await self.repo.log_action(player, action, aoid)
        await self.announce(player, action, aoid)

    # -- registration ----------------------------------------------------

    async def is_registered(self, player: str) -> bool:
        return await self.repo.is_registered(player)

    async def register(self, player: str) -> None:
        if await self.repo.is_registered(player):
            raise AlreadyRegisteredError(player)
        await self.repo.register(player)
        await self.log_action(player, "register")

    async def unregister(self, player: str) -> int:
        if not await self.repo.is_registered(player):
            raise NotRegisteredError(player)
        removed = await self.repo.unregister_cascade(player)
        await self.announce(player, "unregister")
        return removed

    # -- tracking ---------------------------------------------------------

    async def watch_item(self, aoid: int, name: str, ql: int, icon: int | None, auto_tracked: bool = False) -> bool:
        is_new = await self.repo.upsert_watch(aoid, name, ql, icon, auto_tracked=auto_tracked)
        if is_new:
            await self.announce_tracked(name, "auto" if auto_tracked else "manual")
        return is_new

    async def untrack_all(self) -> int:
        return await self.repo.clear_watch()

    # -- subscriptions ----------------------------------------------------

    async def subscribe(self, player: str, aoid: int) -> Item:
        item = await self.aodb.get_item(aoid)
        if item is None:
            raise UnknownItemError(aoid)
        if not await self.repo.is_registered(player):
            await self.log_action(player, "watch_denied", aoid)
            raise NotRegisteredError(player)
        if await self.repo.get_subscription(player, aoid) is not None:
            raise AlreadyWatchingError(aoid)

        limit = await self.settings.get_int("MaxSubscriptionsPerPlayer")
        if await self.repo.count_subscriptions(player) >= limit:
            raise SubscriptionLimitError(limit)

        # market_subscriptions.aoid FKs to market_watch.aoid (a deliberate
        # tightening of the original schema), so the watch row must
        # exist before the subscription can reference it.
        await self.watch_item(aoid, item.name, item.ql, item.icon)
        await self.repo.add_subscription(player, aoid)
        await self.log_action(player, "watch", aoid)
        return item

    async def unsubscribe(self, player: str, aoid: int) -> bool:
        deleted = await self.repo.delete_subscription(player, aoid)
        await self.log_action(player, "unwatch", aoid)
        return deleted

    async def unsubscribe_bulk(self, player: str, aoids: list[int]) -> tuple[set[int], set[int]]:
        unique_aoids = sorted(set(aoids))
        removed: set[int] = set()
        not_watched: set[int] = set()
        for aoid in unique_aoids:
            deleted = await self.repo.delete_subscription(player, aoid)
            await self.log_action(player, "unwatch", aoid)
            (removed if deleted else not_watched).add(aoid)
        return removed, not_watched

    async def unsubscribe_all(self, player: str) -> int:
        count = await self.repo.delete_all_subscriptions(player)
        await self.log_action(player, "unwatch_all")
        return count

    async def list_watchlist(self, player: str):
        return await self.repo.list_subscriptions(player)

    # -- filters ----------------------------------------------------------

    async def _require_subscription(self, player: str, aoid: int):
        sub = await self.repo.get_subscription(player, aoid)
        if sub is None:
            raise NotWatchingError(aoid)
        return sub

    async def set_price_filter(self, player: str, aoid: int, spec: str) -> None:
        await self._require_subscription(player, aoid)
        parsed = parsing.parse_range(spec, parsing.parse_credits)
        if parsed is None:
            raise InvalidRangeError(spec)
        min_price, max_price = parsed
        await self.repo.update_price_filter(player, aoid, min_price, max_price)

    async def set_ql_filter(self, player: str, aoid: int, spec: str) -> None:
        await self._require_subscription(player, aoid)
        parsed = parsing.parse_range(spec, parsing.parse_ql)
        if parsed is None:
            raise InvalidRangeError(spec)
        min_ql, max_ql = parsed
        await self.repo.update_ql_filter(player, aoid, min_ql, max_ql)

    async def clear_filter(self, player: str, aoid: int) -> None:
        await self._require_subscription(player, aoid)
        await self.repo.clear_filter(player, aoid)

    async def get_filter(self, player: str, aoid: int):
        return await self._require_subscription(player, aoid)

    # -- stats/status ------------------------------------------------------

    async def user_stats(self, player: str):
        total, first_seen = await self.repo.user_action_summary(player)
        if not total:
            return None
        breakdown = await self.repo.user_action_breakdown(player)
        subscriptions = await self.repo.count_subscriptions(player)
        return {
            "total_actions": total,
            "first_seen": first_seen,
            "active_subscriptions": subscriptions,
            "by_action": breakdown,
        }

    async def status_summary(self) -> dict:
        total = await self.repo.count_watch()
        auto = await self.repo.count_watch(auto_tracked=True)
        manual = total - auto
        return {
            "total_tracked": total,
            "auto_tracked": auto,
            "manually_tracked": manual,
            "auto_track_enabled": await self.settings.get_bool("AutoTrackEnabled"),
            "auto_track_count": await self.settings.get_int("AutoTrackCount"),
            "auto_track_last_sync": await self.settings.get_int("AutoTrackLastSync"),
        }

    async def status_details(self, limit: int = 500, offset: int = 0):
        return await self.repo.list_watch(limit=limit, offset=offset)

    # -- polling -----------------------------------------------------------

    async def poll_market(self) -> PollSummary:
        now = datetime.now(UTC)
        retention_days = await self.settings.get_int("HistoryRetentionDays")
        expire_days = await self.settings.get_int("WatchExpireDays")
        interval_minutes = await self.settings.get_int("PollIntervalMinutes")
        batch_size = await self.settings.get_int("PollBatchSize")

        expired = await self.repo.expire_stale_watch(now - timedelta(days=expire_days))
        await self.repo.prune_history(now - timedelta(days=retention_days))

        due = await self.repo.due_for_poll(now - timedelta(minutes=interval_minutes), batch_size)
        updated = 0
        for watch in due:
            orders = await self.gmi.get_orders(watch.aoid)
            if orders is not None:
                await self._snapshot(watch.aoid, orders, watch.ql)
                await self._detect_new_orders(watch.aoid, orders, watch.name)
                updated += 1
            await self.repo.update_last_polled(watch.aoid, now)

        if due:
            summary = f"Poll cycle complete: {updated}/{len(due)} item(s) successfully updated"
            if expired:
                summary += f", {len(expired)} item(s) expired and dropped from tracking"
            await self.announce_background(summary)

        return PollSummary(due_count=len(due), updated_count=updated, expired_count=len(expired))

    async def _snapshot(self, aoid: int, orders: Orders, anchor_ql: int) -> None:
        sell_count = len(orders.sell_orders)
        buy_count = len(orders.buy_orders)
        min_sell = min((o.price for o in orders.sell_orders), default=0)
        max_buy = max((o.price for o in orders.buy_orders), default=0)

        anchor_sell_prices = [o.price for o in orders.sell_orders if o.ql == anchor_ql]
        anchor_buy_prices = [o.price for o in orders.buy_orders if o.min_ql <= anchor_ql <= o.max_ql]
        anchor_sell_count = len(anchor_sell_prices)
        anchor_buy_count = len(anchor_buy_prices)
        avg_sell = sum(anchor_sell_prices) / anchor_sell_count if anchor_sell_count else 0
        avg_buy = sum(anchor_buy_prices) / anchor_buy_count if anchor_buy_count else 0

        await self.repo.insert_snapshot(
            aoid=aoid,
            sell_count=sell_count,
            buy_count=buy_count,
            min_sell_price=min_sell,
            max_buy_price=max_buy,
            avg_sell_price=avg_sell,
            avg_buy_price=avg_buy,
            anchor_sell_count=anchor_sell_count,
            anchor_buy_count=anchor_buy_count,
        )

    # -- new-order detection & alerts ------------------------------------

    async def _detect_new_orders(self, aoid: int, orders: Orders, item_name: str) -> None:
        fingerprint_map: dict[str, NewOrder] = {}
        for sell in orders.sell_orders:
            fp = f"sell|{sell.price}|{sell.ql}|{sell.count}|{sell.seller}"
            fingerprint_map[fp] = NewOrder(side="sell", price=sell.price, min_ql=sell.ql, max_ql=sell.ql)
        for buy in orders.buy_orders:
            fp = f"buy|{buy.price}|{buy.min_ql}|{buy.max_ql}|{buy.count}|{buy.buyer}"
            fingerprint_map[fp] = NewOrder(side="buy", price=buy.price, min_ql=buy.min_ql, max_ql=buy.max_ql)

        fingerprints = set(fingerprint_map.keys())
        seen = await self.repo.get_seen_fingerprints(aoid)
        is_first_poll = not seen
        if not is_first_poll:
            new_fingerprints = fingerprints - seen
            if new_fingerprints:
                new_orders = [fingerprint_map[fp] for fp in new_fingerprints]
                await self.notify_subscribers(aoid, item_name, new_orders)

        await self.repo.replace_seen_fingerprints(aoid, fingerprints)

    @staticmethod
    def order_matches_filter(
        order: NewOrder,
        min_price: int | None,
        max_price: int | None,
        min_ql: int | None,
        max_ql: int | None,
    ) -> bool:
        if min_price is not None and order.price < min_price:
            return False
        if max_price is not None and order.price > max_price:
            return False
        if min_ql is not None and order.min_ql < min_ql:
            return False
        if max_ql is not None and order.max_ql > max_ql:
            return False
        return True

    async def notify_subscribers(self, aoid: int, item_name: str, new_orders: list[NewOrder]) -> int:
        subs = await self.repo.subscribers_for_aoid(aoid)
        if not subs:
            return 0

        notified = 0
        for sub in subs:
            matching = [
                o
                for o in new_orders
                if self.order_matches_filter(o, sub.min_price, sub.max_price, sub.min_ql, sub.max_ql)
            ]
            if not matching:
                continue

            message = self._format_alert(item_name, aoid, matching)
            online = await self.chat.is_online(sub.player) if self.chat.is_online is not None else False
            if online:
                await self._send_tell(sub.player, message)
            else:
                await self.repo.queue_pending_alert(sub.player, aoid, message)
            notified += 1

        log.info(
            "notify_subscribers",
            aoid=aoid,
            notified=notified,
            subscriber_count=len(subs),
            new_order_count=len(new_orders),
        )
        return notified

    async def _send_tell(self, player: str, message: str) -> None:
        if self.chat.send_tell is not None:
            await self.chat.send_tell(player, message)

    @staticmethod
    def _format_alert(item_name: str, aoid: int, matching: list[NewOrder]) -> str:
        lines = [f"{len(matching)} new order(s) posted for {item_name}:", ""]
        for order in matching:
            ql_part = (
                f"QL{order.min_ql}" if order.min_ql == order.max_ql else f"QL{order.min_ql}-{order.max_ql}"
            )
            lines.append(f" - {order.side.capitalize()}: {parsing.format_credits(order.price)} {ql_part}")
        lines.append("")
        lines.append(f"[market {aoid}]")
        return "\n".join(lines)

    async def deliver_pending_alerts(self, player: str) -> int:
        """Called once a subscriber logs back on (fired by
        the framework's logon-notify hook)."""
        alerts = await self.repo.pop_pending_alerts(player)
        for alert in alerts:
            await self._send_tell(player, alert.message)
        return len(alerts)

    # -- auto-track resync -------------------------------------------------

    async def sync_top_traded_items(self) -> AutoTrackSummary | None:
        if not await self.settings.get_bool("AutoTrackEnabled"):
            return None
        count = await self.settings.get_int("AutoTrackCount")
        if count < 1:
            return None

        pages = min(_MAX_AUTOTRACK_PAGES, math.ceil(count / 20))
        source_url = (await self.settings.get_str("AutoTrackSourceUrl")).rstrip("/")

        aoids: list[int] = []
        pages_fetched = 0
        for page in range(1, pages + 1):
            html = await self.scraper.fetch_page(source_url, page)
            if html is None:
                break
            found = extract_aoids(html)
            if not found:
                break
            pages_fetched += 1
            for aoid in found:
                if aoid not in aoids:
                    aoids.append(aoid)
            if len(aoids) >= count:
                break

        if pages_fetched == 0:
            log.warning("autotrack_no_pages_fetched", source_url=source_url)
            return None

        aoids = aoids[:count]
        resolved: dict[int, Item] = {}
        if aoids:
            # Skip re-requesting aoids that recently 404'd and are still
            # within their backoff window - the ranked list is scraped
            # fresh every cycle and reliably includes the same
            # already-known-missing aoids alongside real ones, so without
            # this every sync cycle re-attempts every permanently-missing
            # item forever.
            due_aoids = list(await self.aodb_backoff.due_for_retry(set(aoids)))
            skipped_count = len(aoids) - len(due_aoids)
            if skipped_count:
                log.info("aodb_lookup_backoff_skipped", count=skipped_count)

            if due_aoids:
                items = await asyncio.gather(*(self.aodb.get_item(aoid) for aoid in due_aoids))
                for aoid, item in zip(due_aoids, items, strict=True):
                    if item is None:
                        log.warning("aodb_item_lookup_404", aoid=aoid)
                        await self.aodb_backoff.record_failure(aoid)
                    else:
                        await self.aodb_backoff.record_success(aoid)
                        resolved[aoid] = item

        await self.repo.unflag_autotrack_not_in(set(resolved.keys()))
        existing_aoids = await self.repo.existing_aoids(set(resolved.keys()))

        for aoid, item in resolved.items():
            await self.repo.upsert_watch(aoid, item.name, item.ql, item.icon, auto_tracked=True)
            if aoid not in existing_aoids:
                await self.announce_tracked(item.name, "auto")

        await self.settings.set("AutoTrackLastSync", int(now_epoch()))
        summary = (
            f"Resync complete: {pages_fetched} page(s) fetched, {len(aoids)} ranked AOID(s) found, "
            f"{len(resolved)} resolved against aodb-api and now auto-tracked"
        )
        await self.announce_background(summary)
        return AutoTrackSummary(pages_fetched=pages_fetched, ranked_count=len(aoids), resolved_count=len(resolved))


def now_epoch() -> float:
    return datetime.now(UTC).timestamp()
