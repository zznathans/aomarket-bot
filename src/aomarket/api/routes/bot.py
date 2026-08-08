from fastapi import APIRouter, Depends

from aomarket.api.deps import call_on_bot, get_bot_handle, require_bot_ready
from aomarket.api.schemas import BotStatusOut, TellIn
from aomarket.bot.runner import BotHandle

router = APIRouter(prefix="/bot", tags=["bot"])


@router.get("/status", response_model=BotStatusOut)
async def bot_status(handle: BotHandle | None = Depends(get_bot_handle)):
    connected = bool(handle and handle.ready.is_set())
    character = handle.bot.chat_client.character if connected else None
    return BotStatusOut(
        connected=connected,
        character_name=character.name if character else None,
        character_id=character.id if character else None,
        last_poll_at=handle.bot.last_poll_at if connected else None,
        last_autotrack_at=handle.bot.last_autotrack_at if connected else None,
    )


@router.post("/poll:trigger")
async def trigger_poll(handle: BotHandle | None = Depends(get_bot_handle)):
    handle = require_bot_ready(handle)
    await call_on_bot(handle, handle.bot.force_poll_now)
    return {"triggered": True}


@router.post("/autotrack:trigger")
async def trigger_autotrack(handle: BotHandle | None = Depends(get_bot_handle)):
    handle = require_bot_ready(handle)
    await call_on_bot(handle, handle.bot.force_autotrack_now)
    return {"triggered": True}


@router.post("/tell")
async def send_tell(body: TellIn, handle: BotHandle | None = Depends(get_bot_handle)):
    handle = require_bot_ready(handle)
    await call_on_bot(handle, lambda: handle.bot.chat_client.send_tell_by_name(body.player, body.message))
    return {"sent": True}
