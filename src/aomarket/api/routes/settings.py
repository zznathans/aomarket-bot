from fastapi import APIRouter, Depends, HTTPException

from aomarket.api.auth_deps import require_admin_key
from aomarket.api.deps import get_service
from aomarket.api.schemas import SettingOut, SettingUpdate
from aomarket.db.settings_repo import UnknownSettingError

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=dict[str, bool | int | float | str])
async def list_settings(service=Depends(get_service)):
    return await service.settings.all()


@router.get("/{key}", response_model=SettingOut)
async def get_setting(key: str, service=Depends(get_service)):
    try:
        value = await service.settings.get(key)
    except UnknownSettingError:
        raise HTTPException(status_code=404, detail=f"unknown setting {key!r}") from None
    return SettingOut(key=key, value=value)


@router.put("/{key}", response_model=SettingOut, dependencies=[Depends(require_admin_key)])
async def update_setting(key: str, body: SettingUpdate, service=Depends(get_service)):
    try:
        await service.settings.set(key, body.value)
        value = await service.settings.get(key)
    except UnknownSettingError:
        raise HTTPException(status_code=404, detail=f"unknown setting {key!r}") from None
    return SettingOut(key=key, value=value)
