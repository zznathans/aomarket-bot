import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TZ_TIMESTAMP = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class SubscriptionSide(enum.StrEnum):
    buy = "buy"
    sell = "sell"


class MarketUser(Base):
    __tablename__ = "market_users"

    player: Mapped[str] = mapped_column(Text, primary_key=True)
    registered_at: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)


class MarketWatch(Base):
    __tablename__ = "market_watch"

    aoid: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ql: Mapped[int] = mapped_column(Integer, nullable=False)
    icon: Mapped[int | None] = mapped_column(Integer)
    first_seen: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)
    last_polled: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default="-infinity", nullable=False)
    auto_tracked: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)


class MarketHistory(Base):
    __tablename__ = "market_history"
    __table_args__ = (Index("ix_market_history_aoid_ts", "aoid", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aoid: Mapped[int] = mapped_column(BigInteger, ForeignKey("market_watch.aoid", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)
    sell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_sell_price: Mapped[int | None] = mapped_column(BigInteger)
    max_buy_price: Mapped[int | None] = mapped_column(BigInteger)
    avg_sell_price: Mapped[float | None] = mapped_column(Numeric)
    avg_buy_price: Mapped[float | None] = mapped_column(Numeric)
    anchor_sell_count: Mapped[int | None] = mapped_column(Integer)
    anchor_buy_count: Mapped[int | None] = mapped_column(Integer)


class MarketSubscription(Base):
    __tablename__ = "market_subscriptions"
    __table_args__ = (UniqueConstraint("player", "aoid", name="uq_market_subscriptions_player_aoid"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player: Mapped[str] = mapped_column(Text, ForeignKey("market_users.player", ondelete="CASCADE"), nullable=False)
    aoid: Mapped[int] = mapped_column(BigInteger, ForeignKey("market_watch.aoid", ondelete="CASCADE"), nullable=False)
    side: Mapped[SubscriptionSide | None] = mapped_column(Enum(SubscriptionSide, name="subscription_side"))
    min_price: Mapped[int | None] = mapped_column(BigInteger)
    max_price: Mapped[int | None] = mapped_column(BigInteger)
    min_ql: Mapped[int | None] = mapped_column(Integer)
    max_ql: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)


class MarketSeenOrder(Base):
    __tablename__ = "market_seen_orders"

    aoid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text, primary_key=True)


class MarketPendingAlert(Base):
    __tablename__ = "market_pending_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player: Mapped[str] = mapped_column(Text, nullable=False)
    aoid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)


class MarketUserAction(Base):
    __tablename__ = "market_user_actions"
    __table_args__ = (Index("ix_market_user_actions_player_created", "player", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    aoid: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TZ_TIMESTAMP, server_default=func.now(), nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("value_type IN ('bool','int','float','str')", name="ck_settings_value_type"),)

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZ_TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )
