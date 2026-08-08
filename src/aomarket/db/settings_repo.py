from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.db.models import Setting

ValueType = Literal["bool", "int", "float", "str"]
SettingValue = bool | int | float | str


@dataclass(frozen=True)
class SettingDefault:
    key: str
    value: SettingValue
    value_type: ValueType


# Default settings for the market module.
DEFAULT_SETTINGS: list[SettingDefault] = [
    SettingDefault("Enabled", False, "bool"),
    SettingDefault("ApiUrl", "https://gmi.nadybot.org", "str"),
    SettingDefault("PollIntervalMinutes", 30, "int"),
    SettingDefault("HistoryRetentionDays", 90, "int"),
    SettingDefault("WatchExpireDays", 30, "int"),
    SettingDefault("PollBatchSize", 25, "int"),
    SettingDefault("AutoTrackEnabled", True, "bool"),
    SettingDefault("AutoTrackCount", 100, "int"),
    SettingDefault("AutoTrackIntervalMinutes", 60, "int"),
    SettingDefault("AutoTrackSourceUrl", "https://ao-stonks.com", "str"),
    SettingDefault("AutoTrackLastSync", 0, "int"),
    SettingDefault("MaxSubscriptionsPerPlayer", 25, "int"),
    SettingDefault("LogToPrivateChannel", False, "bool"),
    SettingDefault("LogBackgroundToPrivateChannel", False, "bool"),
]


def _serialize(value: SettingValue, value_type: ValueType) -> str:
    if value_type == "bool":
        return "true" if value else "false"
    return str(value)


def _deserialize(value: str, value_type: ValueType) -> SettingValue:
    if value_type == "bool":
        return value == "true"
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    return value


class UnknownSettingError(KeyError):
    pass


class SettingsRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def seed_defaults(self) -> None:
        for default in DEFAULT_SETTINGS:
            stmt = (
                pg_insert(Setting)
                .values(
                    key=default.key,
                    value=_serialize(default.value, default.value_type),
                    value_type=default.value_type,
                )
                .on_conflict_do_nothing(index_elements=["key"])
            )
            await self._session.execute(stmt)
        await self._session.commit()

    async def _get_row(self, key: str) -> Setting:
        row = await self._session.get(Setting, key)
        if row is None:
            raise UnknownSettingError(key)
        return row

    async def get(self, key: str) -> SettingValue:
        row = await self._get_row(key)
        return _deserialize(row.value, row.value_type)  # type: ignore[arg-type]

    async def get_bool(self, key: str) -> bool:
        value = await self.get(key)
        assert isinstance(value, bool)
        return value

    async def get_int(self, key: str) -> int:
        value = await self.get(key)
        assert isinstance(value, int) and not isinstance(value, bool)
        return value

    async def get_float(self, key: str) -> float:
        value = await self.get(key)
        assert isinstance(value, (int, float))
        return float(value)

    async def get_str(self, key: str) -> str:
        value = await self.get(key)
        assert isinstance(value, str)
        return value

    async def set(self, key: str, value: SettingValue) -> None:
        row = await self._get_row(key)
        row.value = _serialize(value, row.value_type)  # type: ignore[arg-type]
        await self._session.commit()

    async def all(self) -> dict[str, SettingValue]:
        result = await self._session.execute(select(Setting))
        return {row.key: _deserialize(row.value, row.value_type) for row in result.scalars()}  # type: ignore[arg-type]
