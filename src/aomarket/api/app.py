from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aomarket.aodb.client import AodbClient
from aomarket.autotrack.scraper import AutoTrackScraper
from aomarket.bot.runner import BotHandle
from aomarket.gmi.client import GmiClient
from aomarket.market.errors import (
    AlreadyRegisteredError,
    AlreadyWatchingError,
    InvalidRangeError,
    MarketError,
    NoActivityError,
    NotRegisteredError,
    NotWatchingError,
    SubscriptionLimitError,
    UnknownItemError,
)

_ERROR_STATUS_CODES: dict[type[MarketError], int] = {
    UnknownItemError: 404,
    NotWatchingError: 404,
    NoActivityError: 404,
    AlreadyRegisteredError: 409,
    AlreadyWatchingError: 409,
    SubscriptionLimitError: 409,
    NotRegisteredError: 400,
    InvalidRangeError: 422,
}


def _status_code_for(exc: MarketError) -> int:
    for exc_type, code in _ERROR_STATUS_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return 400


def create_app(
    sessionmaker: async_sessionmaker[AsyncSession],
    aodb: AodbClient,
    gmi: GmiClient,
    scraper: AutoTrackScraper,
    bot_handle: BotHandle | None = None,
) -> FastAPI:
    app = FastAPI(title="aomarket-bot", version="0.1.0")
    app.state.sessionmaker = sessionmaker
    app.state.aodb = aodb
    app.state.gmi = gmi
    app.state.scraper = scraper
    app.state.bot_handle = bot_handle

    @app.exception_handler(MarketError)
    async def market_error_handler(request: Request, exc: MarketError) -> JSONResponse:
        return JSONResponse(status_code=_status_code_for(exc), content={"detail": str(exc)})

    from aomarket.api.routes import admin, bot, health, items, settings, status, users, watch

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(items.router)
    app.include_router(watch.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(status.router)
    app.include_router(bot.router)

    return app
