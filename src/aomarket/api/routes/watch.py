from fastapi import APIRouter, Depends, HTTPException

from aomarket.api.auth_deps import require_admin_key
from aomarket.api.deps import get_service
from aomarket.api.schemas import ItemOut, WatchItemOut
from aomarket.market.errors import UnknownItemError

router = APIRouter(prefix="/watch", tags=["watch"])


@router.get("", response_model=list[WatchItemOut])
async def list_watch(limit: int = 500, offset: int = 0, auto_tracked: bool | None = None, service=Depends(get_service)):
    rows = await service.repo.list_watch(limit=limit, offset=offset, auto_tracked=auto_tracked)
    return [WatchItemOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{aoid}", response_model=WatchItemOut)
async def get_watch(aoid: int, service=Depends(get_service)):
    row = await service.repo.get_watch(aoid)
    if row is None:
        raise HTTPException(status_code=404, detail=f"aoid {aoid} is not currently tracked")
    return WatchItemOut.model_validate(row, from_attributes=True)


@router.post("/{aoid}", response_model=ItemOut, dependencies=[Depends(require_admin_key)])
async def start_watching(aoid: int, service=Depends(get_service)):
    item = await service.aodb.get_item(aoid)
    if item is None:
        raise UnknownItemError(aoid)
    await service.watch_item(aoid, item.name, item.ql, item.icon)
    return ItemOut(aoid=item.aoid, name=item.name, ql=item.ql, icon=item.icon, description=item.description)


@router.delete("/{aoid}", status_code=204, dependencies=[Depends(require_admin_key)])
async def stop_tracking(aoid: int, service=Depends(get_service)):
    deleted = await service.repo.delete_watch(aoid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"aoid {aoid} is not currently tracked")


@router.get("/{aoid}/orders")
async def get_orders(aoid: int, service=Depends(get_service)):
    orders = await service.gmi.get_orders(aoid)
    if orders is None:
        raise HTTPException(status_code=502, detail="market data currently unavailable")
    return {
        "sell_orders": [o.__dict__ for o in orders.sell_orders],
        "buy_orders": [o.__dict__ for o in orders.buy_orders],
    }
