import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.bot.runner import BotHandle
from aomarket.db.aodb_backoff_repo import AodbBackoffRepo
from aomarket.db.market_repo import MarketRepo
from aomarket.db.settings_repo import SettingsRepo
from aomarket.market.service import ChatSink, MarketService


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = request.app.state.sessionmaker
    session = sessionmaker()
    try:
        yield session
    finally:
        await session.close()


def get_bot_handle(request: Request) -> BotHandle | None:
    return getattr(request.app.state, "bot_handle", None)


async def get_service(request: Request, session: AsyncSession = Depends(get_db_session)) -> MarketService:
    state = request.app.state
    handle: BotHandle | None = getattr(state, "bot_handle", None)

    async def send_privgroup(message: str) -> None:
        if handle is not None and handle.ready.is_set():
            await call_on_bot(handle, lambda: handle.bot._send_privgroup(message))  # noqa: SLF001

    async def send_tell(player: str, message: str) -> None:
        if handle is not None and handle.ready.is_set():
            await call_on_bot(handle, lambda: handle.bot.chat_client.send_tell_by_name(player, message))

    async def is_online(player: str) -> bool:
        if handle is not None and handle.ready.is_set():
            return await call_on_bot(handle, lambda: handle.bot.chat_client.is_online_by_name(player))
        return False

    chat = ChatSink(send_privgroup=send_privgroup, send_tell=send_tell, is_online=is_online)
    return MarketService(
        repo=MarketRepo(session),
        settings=SettingsRepo(session),
        aodb=state.aodb,
        aodb_backoff=AodbBackoffRepo(session),
        gmi=state.gmi,
        scraper=state.scraper,
        chat=chat,
    )


class BotNotReadyError(Exception):
    pass


async def call_on_bot[T](handle: BotHandle, coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Bridges a coroutine onto the bot thread's event loop from any other
    thread/loop (here, FastAPI's), per the concurrency design: schedule via
    run_coroutine_threadsafe, then await the resulting concurrent.futures.Future
    wrapped as an asyncio awaitable."""
    if handle.loop is None or not handle.ready.is_set():
        raise BotNotReadyError("bot is not connected yet")
    future = asyncio.run_coroutine_threadsafe(coro_factory(), handle.loop)
    return await asyncio.wrap_future(future)


def require_bot_ready(handle: BotHandle | None) -> BotHandle:
    if handle is None or not handle.ready.is_set():
        raise HTTPException(status_code=503, detail="bot is not connected yet")
    return handle
