from fastapi import APIRouter, Depends

from aomarket.api.deps import get_service
from aomarket.api.schemas import StatusSummaryOut, WatchItemOut

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=StatusSummaryOut)
async def status_summary(service=Depends(get_service)):
    return StatusSummaryOut(**await service.status_summary())


@router.get("/details", response_model=list[WatchItemOut])
async def status_details(limit: int = 500, offset: int = 0, service=Depends(get_service)):
    rows = await service.status_details(limit=limit, offset=offset)
    return [WatchItemOut.model_validate(r, from_attributes=True) for r in rows]
