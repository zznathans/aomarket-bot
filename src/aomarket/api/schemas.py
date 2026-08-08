from datetime import datetime

from pydantic import BaseModel


class ErrorOut(BaseModel):
    detail: str


class SettingOut(BaseModel):
    key: str
    value: bool | int | float | str


class SettingUpdate(BaseModel):
    value: bool | int | float | str


class ItemOut(BaseModel):
    aoid: int
    name: str
    ql: int
    icon: int | None
    description: str | None = None


class WatchItemOut(BaseModel):
    aoid: int
    name: str
    ql: int
    icon: int | None
    first_seen: datetime
    last_polled: datetime
    auto_tracked: bool


class SubscriptionOut(BaseModel):
    aoid: int
    player: str
    min_price: int | None
    max_price: int | None
    min_ql: int | None
    max_ql: int | None
    created_at: datetime


class FilterUpdate(BaseModel):
    price_spec: str | None = None
    ql_spec: str | None = None


class RegisterOut(BaseModel):
    player: str
    registered: bool


class UnregisterIn(BaseModel):
    confirm: bool = False


class UnregisterOut(BaseModel):
    player: str
    subscriptions_removed: int


class BulkUnwatchIn(BaseModel):
    aoids: list[int]


class BulkUnwatchOut(BaseModel):
    removed: list[int]
    not_watched: list[int]


class UserStatsOut(BaseModel):
    player: str
    total_actions: int
    first_seen: datetime
    active_subscriptions: int
    by_action: dict[str, int]


class StatusSummaryOut(BaseModel):
    total_tracked: int
    auto_tracked: int
    manually_tracked: int
    auto_track_enabled: bool
    auto_track_count: int
    auto_track_last_sync: int


class UntrackAllIn(BaseModel):
    confirm: bool = False


class UntrackAllOut(BaseModel):
    cleared: int


class BotStatusOut(BaseModel):
    connected: bool
    character_name: str | None
    character_id: int | None
    last_poll_at: datetime | None
    last_autotrack_at: datetime | None


class TellIn(BaseModel):
    player: str
    message: str
