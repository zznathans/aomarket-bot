import pytest

from aomarket.db.settings_repo import SettingsRepo, UnknownSettingError
from tests.conftest import requires_postgres


@requires_postgres
@pytest.mark.asyncio
async def test_seed_defaults_populates_all_market_keys(db_session):
    repo = SettingsRepo(db_session)
    await repo.seed_defaults()

    values = await repo.all()

    assert values["Enabled"] is False
    assert values["ApiUrl"] == "https://gmi.nadybot.org"
    assert values["PollIntervalMinutes"] == 30
    assert values["AutoTrackEnabled"] is True
    assert values["AutoTrackSourceUrl"] == "https://ao-stonks.com"


@requires_postgres
@pytest.mark.asyncio
async def test_set_then_get_round_trips_typed_value(db_session):
    repo = SettingsRepo(db_session)
    await repo.seed_defaults()

    await repo.set("PollIntervalMinutes", 45)

    assert await repo.get_int("PollIntervalMinutes") == 45


@requires_postgres
@pytest.mark.asyncio
async def test_reseeding_does_not_clobber_changed_values(db_session):
    repo = SettingsRepo(db_session)
    await repo.seed_defaults()
    await repo.set("PollIntervalMinutes", 45)

    await repo.seed_defaults()

    assert await repo.get_int("PollIntervalMinutes") == 45


@requires_postgres
@pytest.mark.asyncio
async def test_get_unknown_key_raises(db_session):
    repo = SettingsRepo(db_session)
    await repo.seed_defaults()

    with pytest.raises(UnknownSettingError):
        await repo.get("NotARealSetting")
