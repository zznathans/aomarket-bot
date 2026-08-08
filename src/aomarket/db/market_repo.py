from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.db.models import (
    MarketHistory,
    MarketPendingAlert,
    MarketSeenOrder,
    MarketSubscription,
    MarketUser,
    MarketUserAction,
    MarketWatch,
)


class MarketRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    # -- market_users -----------------------------------------------------

    async def is_registered(self, player: str) -> bool:
        return await self._session.get(MarketUser, player) is not None

    async def register(self, player: str) -> None:
        self._session.add(MarketUser(player=player))
        await self._session.commit()

    async def unregister_cascade(self, player: str) -> int:
        """Deletes subscriptions, pending alerts, the user row, and the
        action ledger. Returns the subscription count that was removed."""
        sub_count = (
            await self._session.execute(
                select(func.count()).select_from(MarketSubscription).where(MarketSubscription.player == player)
            )
        ).scalar_one()
        await self._session.execute(delete(MarketSubscription).where(MarketSubscription.player == player))
        await self._session.execute(delete(MarketPendingAlert).where(MarketPendingAlert.player == player))
        await self._session.execute(delete(MarketUserAction).where(MarketUserAction.player == player))
        await self._session.execute(delete(MarketUser).where(MarketUser.player == player))
        await self._session.commit()
        return sub_count

    # -- market_watch -------------------------------------------------------

    async def get_watch(self, aoid: int) -> MarketWatch | None:
        return await self._session.get(MarketWatch, aoid)

    async def upsert_watch(self, aoid: int, name: str, ql: int, icon: int | None, auto_tracked: bool = False) -> bool:
        """Returns True if this aoid was newly inserted (mirrors watch()'s $isNew)."""
        existing = await self.get_watch(aoid)
        is_new = existing is None
        stmt = pg_insert(MarketWatch).values(
            aoid=aoid, name=name, ql=ql, icon=icon, auto_tracked=auto_tracked
        )
        update_cols = {"name": name, "ql": ql, "icon": icon}
        if auto_tracked:
            update_cols["auto_tracked"] = True
        stmt = stmt.on_conflict_do_update(index_elements=["aoid"], set_=update_cols)
        await self._session.execute(stmt)
        await self._session.commit()
        return is_new

    async def delete_watch(self, aoid: int) -> bool:
        result = await self._session.execute(delete(MarketWatch).where(MarketWatch.aoid == aoid))
        await self._session.commit()
        return result.rowcount > 0

    async def count_watch(self, auto_tracked: bool | None = None) -> int:
        stmt = select(func.count()).select_from(MarketWatch)
        if auto_tracked is not None:
            stmt = stmt.where(MarketWatch.auto_tracked == auto_tracked)
        return (await self._session.execute(stmt)).scalar_one()

    async def clear_watch(self) -> int:
        count = await self.count_watch()
        await self._session.execute(delete(MarketWatch))
        await self._session.commit()
        return count

    async def list_watch(
        self, limit: int = 500, offset: int = 0, auto_tracked: bool | None = None
    ) -> list[MarketWatch]:
        stmt = select(MarketWatch).order_by(MarketWatch.aoid).limit(limit).offset(offset)
        if auto_tracked is not None:
            stmt = stmt.where(MarketWatch.auto_tracked == auto_tracked)
        return list((await self._session.execute(stmt)).scalars())

    async def expire_stale_watch(self, cutoff: datetime) -> list[int]:
        """Deletes non-auto-tracked items whose GREATEST(last_polled, first_seen)
        is older than cutoff (plus their history), returns the removed aoids."""
        stmt = select(MarketWatch.aoid).where(
            MarketWatch.auto_tracked.is_(False),
            func.greatest(MarketWatch.last_polled, MarketWatch.first_seen) < cutoff,
        )
        aoids = list((await self._session.execute(stmt)).scalars())
        if aoids:
            await self._session.execute(delete(MarketWatch).where(MarketWatch.aoid.in_(aoids)))
            await self._session.commit()
        return aoids

    async def due_for_poll(self, cutoff: datetime, batch_size: int) -> list[MarketWatch]:
        stmt = (
            select(MarketWatch)
            .where(MarketWatch.last_polled < cutoff)
            .order_by(MarketWatch.last_polled.asc())
            .limit(batch_size)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def update_last_polled(self, aoid: int, ts: datetime) -> None:
        await self._session.execute(update(MarketWatch).where(MarketWatch.aoid == aoid).values(last_polled=ts))
        await self._session.commit()

    async def unflag_autotrack_not_in(self, keep_aoids: set[int]) -> None:
        stmt = update(MarketWatch).where(MarketWatch.auto_tracked.is_(True)).values(auto_tracked=False)
        if keep_aoids:
            stmt = stmt.where(MarketWatch.aoid.notin_(keep_aoids))
        await self._session.execute(stmt)
        await self._session.commit()

    async def existing_aoids(self, aoids: set[int]) -> set[int]:
        if not aoids:
            return set()
        stmt = select(MarketWatch.aoid).where(MarketWatch.aoid.in_(aoids))
        return set((await self._session.execute(stmt)).scalars())

    # -- market_history -----------------------------------------------------

    async def insert_snapshot(
        self,
        aoid: int,
        sell_count: int,
        buy_count: int,
        min_sell_price: int,
        max_buy_price: int,
        avg_sell_price: float,
        avg_buy_price: float,
        anchor_sell_count: int,
        anchor_buy_count: int,
    ) -> None:
        self._session.add(
            MarketHistory(
                aoid=aoid,
                sell_count=sell_count,
                buy_count=buy_count,
                min_sell_price=min_sell_price,
                max_buy_price=max_buy_price,
                avg_sell_price=avg_sell_price,
                avg_buy_price=avg_buy_price,
                anchor_sell_count=anchor_sell_count,
                anchor_buy_count=anchor_buy_count,
            )
        )
        await self._session.commit()

    async def prune_history(self, cutoff: datetime) -> None:
        await self._session.execute(delete(MarketHistory).where(MarketHistory.ts < cutoff))
        await self._session.commit()

    # -- market_subscriptions ------------------------------------------------

    async def get_subscription(self, player: str, aoid: int) -> MarketSubscription | None:
        stmt = select(MarketSubscription).where(
            MarketSubscription.player == player, MarketSubscription.aoid == aoid
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_subscriptions(self, player: str) -> int:
        stmt = select(func.count()).select_from(MarketSubscription).where(MarketSubscription.player == player)
        return (await self._session.execute(stmt)).scalar_one()

    async def add_subscription(self, player: str, aoid: int) -> None:
        self._session.add(MarketSubscription(player=player, aoid=aoid))
        await self._session.commit()

    async def delete_subscription(self, player: str, aoid: int) -> bool:
        result = await self._session.execute(
            delete(MarketSubscription).where(MarketSubscription.player == player, MarketSubscription.aoid == aoid)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def delete_subscriptions_bulk(self, player: str, aoids: list[int]) -> set[int]:
        removed: set[int] = set()
        for aoid in aoids:
            if await self.delete_subscription(player, aoid):
                removed.add(aoid)
        return removed

    async def delete_all_subscriptions(self, player: str) -> int:
        count = await self.count_subscriptions(player)
        await self._session.execute(delete(MarketSubscription).where(MarketSubscription.player == player))
        await self._session.commit()
        return count

    async def list_subscriptions(self, player: str) -> list[MarketSubscription]:
        stmt = (
            select(MarketSubscription)
            .where(MarketSubscription.player == player)
            .order_by(MarketSubscription.created_at.asc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def update_price_filter(self, player: str, aoid: int, min_price: int | None, max_price: int | None) -> None:
        await self._session.execute(
            update(MarketSubscription)
            .where(MarketSubscription.player == player, MarketSubscription.aoid == aoid)
            .values(min_price=min_price, max_price=max_price)
        )
        await self._session.commit()

    async def update_ql_filter(self, player: str, aoid: int, min_ql: int | None, max_ql: int | None) -> None:
        await self._session.execute(
            update(MarketSubscription)
            .where(MarketSubscription.player == player, MarketSubscription.aoid == aoid)
            .values(min_ql=min_ql, max_ql=max_ql)
        )
        await self._session.commit()

    async def clear_filter(self, player: str, aoid: int) -> None:
        await self._session.execute(
            update(MarketSubscription)
            .where(MarketSubscription.player == player, MarketSubscription.aoid == aoid)
            .values(min_price=None, max_price=None, min_ql=None, max_ql=None)
        )
        await self._session.commit()

    async def subscribers_for_aoid(self, aoid: int) -> list[MarketSubscription]:
        stmt = select(MarketSubscription).where(MarketSubscription.aoid == aoid)
        return list((await self._session.execute(stmt)).scalars())

    # -- market_seen_orders ---------------------------------------------------

    async def get_seen_fingerprints(self, aoid: int) -> set[str]:
        stmt = select(MarketSeenOrder.fingerprint).where(MarketSeenOrder.aoid == aoid)
        return set((await self._session.execute(stmt)).scalars())

    async def replace_seen_fingerprints(self, aoid: int, fingerprints: set[str]) -> None:
        await self._session.execute(delete(MarketSeenOrder).where(MarketSeenOrder.aoid == aoid))
        for fp in fingerprints:
            stmt = pg_insert(MarketSeenOrder).values(aoid=aoid, fingerprint=fp).on_conflict_do_nothing()
            await self._session.execute(stmt)
        await self._session.commit()

    # -- market_pending_alerts ------------------------------------------------

    async def queue_pending_alert(self, player: str, aoid: int, message: str) -> None:
        self._session.add(MarketPendingAlert(player=player, aoid=aoid, message=message))
        await self._session.commit()

    async def pop_pending_alerts(self, player: str) -> list[MarketPendingAlert]:
        stmt = (
            select(MarketPendingAlert)
            .where(MarketPendingAlert.player == player)
            .order_by(MarketPendingAlert.created_at.asc())
        )
        alerts = list((await self._session.execute(stmt)).scalars())
        if alerts:
            await self._session.execute(
                delete(MarketPendingAlert).where(MarketPendingAlert.id.in_([a.id for a in alerts]))
            )
            await self._session.commit()
        return alerts

    # -- market_user_actions --------------------------------------------------

    async def log_action(self, player: str, action: str, aoid: int | None = None) -> None:
        self._session.add(MarketUserAction(player=player, action=action, aoid=aoid))
        await self._session.commit()

    async def user_action_summary(self, player: str) -> tuple[int, datetime | None]:
        stmt = select(func.count(), func.min(MarketUserAction.created_at)).where(MarketUserAction.player == player)
        total, first_seen = (await self._session.execute(stmt)).one()
        return total, first_seen

    async def user_action_breakdown(self, player: str) -> list[tuple[str, int]]:
        stmt = (
            select(MarketUserAction.action, func.count())
            .where(MarketUserAction.player == player)
            .group_by(MarketUserAction.action)
            .order_by(func.count().desc())
        )
        return list((await self._session.execute(stmt)).all())
