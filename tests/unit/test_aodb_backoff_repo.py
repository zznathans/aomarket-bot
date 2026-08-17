from datetime import UTC, datetime, timedelta

import pytest

from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.models import AodbLookupBackoff
from tests.conftest import requires_postgres


@requires_postgres
@pytest.mark.asyncio
async def test_due_for_retry_includes_never_attempted_aoids(db_session):
    repo = AodbBackoffRepo(db_session)

    due = await repo.due_for_retry({1, 2, 3})

    assert due == {1, 2, 3}


@requires_postgres
@pytest.mark.asyncio
async def test_record_failure_excludes_aoid_from_due_for_retry(db_session):
    repo = AodbBackoffRepo(db_session)

    await repo.record_failure(42)

    assert await repo.due_for_retry({42}) == set()


@requires_postgres
@pytest.mark.asyncio
async def test_record_failure_backoff_grows_exponentially(db_session):
    repo = AodbBackoffRepo(db_session)

    await repo.record_failure(42)
    first = await db_session.get(AodbLookupBackoff, 42)
    first_delay = first.next_retry_at - first.last_attempted_at

    await repo.record_failure(42)
    await db_session.refresh(first)
    second = await db_session.get(AodbLookupBackoff, 42)
    second_delay = second.next_retry_at - second.last_attempted_at

    assert second.failure_count == 2
    assert second_delay > first_delay
    assert second_delay == first_delay * 2


@requires_postgres
@pytest.mark.asyncio
async def test_record_failure_caps_backoff_delay(db_session):
    repo = AodbBackoffRepo(db_session)

    for _ in range(20):
        await repo.record_failure(42)

    row = await db_session.get(AodbLookupBackoff, 42)
    delay = row.next_retry_at - row.last_attempted_at

    assert delay == timedelta(days=7)


@requires_postgres
@pytest.mark.asyncio
async def test_record_success_clears_backoff_state(db_session):
    repo = AodbBackoffRepo(db_session)
    await repo.record_failure(42)
    assert await repo.due_for_retry({42}) == set()

    await repo.record_success(42)

    assert await repo.due_for_retry({42}) == {42}
    assert await db_session.get(AodbLookupBackoff, 42) is None


@requires_postgres
@pytest.mark.asyncio
async def test_due_for_retry_includes_aoid_once_cooldown_elapses(db_session):
    repo = AodbBackoffRepo(db_session)
    await repo.record_failure(42)
    row = await db_session.get(AodbLookupBackoff, 42)
    row.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    assert await repo.due_for_retry({42}) == {42}


@requires_postgres
@pytest.mark.asyncio
async def test_due_for_retry_only_returns_requested_aoids(db_session):
    repo = AodbBackoffRepo(db_session)
    await repo.record_failure(1)

    assert await repo.due_for_retry({1, 2}) == {2}
