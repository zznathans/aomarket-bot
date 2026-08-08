import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.db.engine import make_engine, make_sessionmaker
from aomarket.db.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    # Deliberately a separate database from the docker-compose dev/default
    # "aomarket" DB (same server) -- this fixture drops/recreates every
    # table each test, which would otherwise wipe out a manually-run dev
    # container's data.
    "postgresql+asyncpg://aomarket:aomarket@localhost:55432/aomarket_test",
)


def _pg_available() -> bool:
    import socket
    from urllib.parse import urlparse

    import asyncpg  # noqa: F401

    parsed = urlparse(TEST_DATABASE_URL.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1):
            return True
    except OSError:
        return False


requires_postgres = pytest.mark.skipif(
    not _pg_available(), reason="local Postgres not reachable at TEST_DATABASE_URL"
)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
