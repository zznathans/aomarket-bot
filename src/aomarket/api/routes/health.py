from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    state = request.app.state
    db_ok = True
    try:
        async with state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    handle = getattr(state, "bot_handle", None)
    bot_connected = bool(handle and handle.ready.is_set())
    character_name = None
    if bot_connected and handle.bot.chat_client.character is not None:
        character_name = handle.bot.chat_client.character.name

    return {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "bot_connected": bot_connected,
        "character_name": character_name,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/readyz")
async def readyz(request: Request) -> dict:
    handle = getattr(request.app.state, "bot_handle", None)
    ready = bool(handle and handle.ready.is_set())
    return {"ready": ready}
