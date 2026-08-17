from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.db.models import AodbLookupBackoff

# 1h, 2h, 4h, 8h, ... capped at 7 days - an aoid that keeps 404ing is
# almost certainly permanently absent from the dump (it's static between
# aodb releases), but the dump does get new content occasionally, so this
# backs off hard rather than giving up on it forever.
_BASE_DELAY = timedelta(hours=1)
_MAX_DELAY = timedelta(days=7)


def _next_retry_at(failure_count: int, now: datetime) -> datetime:
    delay = min(_BASE_DELAY * (2 ** (failure_count - 1)), _MAX_DELAY)
    return now + delay


class AodbBackoffRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def due_for_retry(self, aoids: set[int]) -> set[int]:
        """Returns the subset of `aoids` that are either never-before-failed
        or whose backoff cooldown has already elapsed."""
        if not aoids:
            return set()
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(AodbLookupBackoff.aoid).where(
                AodbLookupBackoff.aoid.in_(aoids),
                AodbLookupBackoff.next_retry_at > now,
            )
        )
        still_backed_off = set(result.scalars())
        return aoids - still_backed_off

    async def record_failure(self, aoid: int) -> None:
        # Read-then-write (matches MarketRepo.upsert_watch's pattern) rather
        # than a single SQL-side upsert - the exponential delay needs the
        # *current* failure_count computed in Python before it can be
        # written, not something Postgres can derive inline.
        now = datetime.now(UTC)
        existing = await self._session.get(AodbLookupBackoff, aoid)
        failure_count = (existing.failure_count if existing else 0) + 1
        stmt = pg_insert(AodbLookupBackoff).values(
            aoid=aoid,
            failure_count=failure_count,
            last_attempted_at=now,
            next_retry_at=_next_retry_at(failure_count, now),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["aoid"],
            set_={
                "failure_count": failure_count,
                "last_attempted_at": now,
                "next_retry_at": _next_retry_at(failure_count, now),
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def record_success(self, aoid: int) -> None:
        """Clears any backoff state - a successful lookup means the aoid
        isn't actually missing (recovered, or was never really gone)."""
        await self._session.execute(delete(AodbLookupBackoff).where(AodbLookupBackoff.aoid == aoid))
        await self._session.commit()
