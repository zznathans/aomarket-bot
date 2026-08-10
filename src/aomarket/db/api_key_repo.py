from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.db.models import ApiKey


class ApiKeyRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, player: str, key_hash: str, prefix: str) -> ApiKey:
        key = ApiKey(player=player, key_hash=key_hash, prefix=prefix)
        self._session.add(key)
        await self._session.commit()
        return key

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def revoke_all_for_player(self, player: str) -> int:
        result = await self._session.execute(
            update(ApiKey).where(ApiKey.player == player, ApiKey.revoked_at.is_(None)).values(revoked_at=func.now())
        )
        await self._session.commit()
        return result.rowcount

    async def list_for_player(self, player: str) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.player == player).order_by(ApiKey.created_at.desc())
        return list((await self._session.execute(stmt)).scalars())

    async def touch_last_used(self, key_id: int) -> None:
        await self._session.execute(update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=func.now()))
        await self._session.commit()
