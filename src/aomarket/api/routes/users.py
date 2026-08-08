from fastapi import APIRouter, Depends, HTTPException

from aomarket.api.deps import get_service
from aomarket.api.schemas import (
    BulkUnwatchIn,
    BulkUnwatchOut,
    FilterUpdate,
    ItemOut,
    RegisterOut,
    SubscriptionOut,
    UnregisterIn,
    UnregisterOut,
    UserStatsOut,
)

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/{player}", response_model=RegisterOut)
async def get_player(player: str, service=Depends(get_service)):
    return RegisterOut(player=player, registered=await service.is_registered(player))


@router.post("/{player}:register", response_model=RegisterOut)
async def register(player: str, service=Depends(get_service)):
    await service.register(player)
    return RegisterOut(player=player, registered=True)


@router.post("/{player}:unregister", response_model=UnregisterOut)
async def unregister(player: str, body: UnregisterIn, service=Depends(get_service)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="destructive action requires confirm=true")
    removed = await service.unregister(player)
    return UnregisterOut(player=player, subscriptions_removed=removed)


@router.get("/{player}/watchlist", response_model=list[SubscriptionOut])
async def get_watchlist(player: str, service=Depends(get_service)):
    subs = await service.list_watchlist(player)
    return [SubscriptionOut.model_validate(s, from_attributes=True) for s in subs]


@router.post("/{player}/watchlist/{aoid}", response_model=ItemOut)
async def subscribe(player: str, aoid: int, service=Depends(get_service)):
    item = await service.subscribe(player, aoid)
    return ItemOut(aoid=item.aoid, name=item.name, ql=item.ql, icon=item.icon, description=item.description)


@router.delete("/{player}/watchlist/{aoid}", status_code=204)
async def unsubscribe(player: str, aoid: int, service=Depends(get_service)):
    deleted = await service.unsubscribe(player, aoid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"{player} is not watching aoid {aoid}")


@router.post("/{player}/watchlist:bulk_delete", response_model=BulkUnwatchOut)
async def bulk_unsubscribe(player: str, body: BulkUnwatchIn, service=Depends(get_service)):
    removed, not_watched = await service.unsubscribe_bulk(player, body.aoids)
    return BulkUnwatchOut(removed=sorted(removed), not_watched=sorted(not_watched))


@router.delete("/{player}/watchlist")
async def unsubscribe_all(player: str, body: UnregisterIn, service=Depends(get_service)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="destructive action requires confirm=true")
    count = await service.unsubscribe_all(player)
    return {"player": player, "unwatched": count}


@router.get("/{player}/watchlist/{aoid}/filter", response_model=SubscriptionOut)
async def get_filter(player: str, aoid: int, service=Depends(get_service)):
    sub = await service.get_filter(player, aoid)
    return SubscriptionOut.model_validate(sub, from_attributes=True)


@router.put("/{player}/watchlist/{aoid}/filter", response_model=SubscriptionOut)
async def update_filter(player: str, aoid: int, body: FilterUpdate, service=Depends(get_service)):
    if body.price_spec is not None:
        await service.set_price_filter(player, aoid, body.price_spec)
    if body.ql_spec is not None:
        await service.set_ql_filter(player, aoid, body.ql_spec)
    sub = await service.get_filter(player, aoid)
    return SubscriptionOut.model_validate(sub, from_attributes=True)


@router.delete("/{player}/watchlist/{aoid}/filter", response_model=SubscriptionOut)
async def clear_filter(player: str, aoid: int, service=Depends(get_service)):
    await service.clear_filter(player, aoid)
    sub = await service.get_filter(player, aoid)
    return SubscriptionOut.model_validate(sub, from_attributes=True)


@router.get("/{player}/stats", response_model=UserStatsOut)
async def get_stats(player: str, service=Depends(get_service)):
    stats = await service.user_stats(player)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"{player} has no recorded Market activity")
    return UserStatsOut(
        player=player,
        total_actions=stats["total_actions"],
        first_seen=stats["first_seen"],
        active_subscriptions=stats["active_subscriptions"],
        by_action=dict(stats["by_action"]),
    )
