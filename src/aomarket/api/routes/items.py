from fastapi import APIRouter, HTTPException, Query, Request, Response

from aomarket.api.schemas import ItemOut

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemOut])
async def search_items(
    request: Request,
    response: Response,
    q: str = Query(...),
    ql: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    items, total = await request.app.state.aodb.search_items(q, ql=ql, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return [ItemOut(aoid=i.aoid, name=i.name, ql=i.ql, icon=i.icon, description=i.description) for i in items]


@router.get("/{aoid}", response_model=ItemOut)
async def get_item(aoid: int, request: Request):
    item = await request.app.state.aodb.get_item(aoid)
    if item is None:
        raise HTTPException(status_code=404, detail=f"unknown item aoid {aoid}")
    return ItemOut(aoid=item.aoid, name=item.name, ql=item.ql, icon=item.icon, description=item.description)
