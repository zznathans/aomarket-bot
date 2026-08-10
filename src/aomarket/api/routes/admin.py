from fastapi import APIRouter, Depends, HTTPException

from aomarket.api.auth_deps import require_admin_key
from aomarket.api.deps import get_service
from aomarket.api.schemas import UntrackAllIn, UntrackAllOut, UserStatsOut
from aomarket.market.errors import NoActivityError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/watch:untrack_all", response_model=UntrackAllOut, dependencies=[Depends(require_admin_key)])
async def untrack_all(body: UntrackAllIn, service=Depends(get_service)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="destructive action requires confirm=true")
    cleared = await service.untrack_all()
    return UntrackAllOut(cleared=cleared)


@router.get("/players/{player}/stats", response_model=UserStatsOut)
async def admin_get_stats(player: str, service=Depends(get_service)):
    stats = await service.user_stats(player)
    if stats is None:
        raise NoActivityError(player)
    return UserStatsOut(
        player=player,
        total_actions=stats["total_actions"],
        first_seen=stats["first_seen"],
        active_subscriptions=stats["active_subscriptions"],
        by_action=dict(stats["by_action"]),
    )
