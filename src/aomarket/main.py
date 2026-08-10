import asyncio
import threading

import uvicorn

from aomarket.aochat.client import AOChatClient
from aomarket.aodb.client import AodbClient
from aomarket.api.app import create_app
from aomarket.autotrack.scraper import AutoTrackScraper
from aomarket.bot.runner import BotHandle, MarketBot, bot_thread_main
from aomarket.config import load_config
from aomarket.db.engine import make_engine, make_sessionmaker
from aomarket.db.settings_repo import SettingsRepo
from aomarket.gmi.client import GmiClient
from aomarket.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _seed_settings(engine, sessionmaker) -> None:
    async with sessionmaker() as session:
        await SettingsRepo(session).seed_defaults()
    # asyncpg connections are bound to the event loop that opened them.
    # asyncio.run() below spins up and tears down its own loop just for
    # this seed step; without disposing here, the pool holds onto
    # connections from that now-closed loop and the first request under
    # uvicorn's (different) loop fails with "Event loop is closed" before
    # the pool recovers. Disposing forces a clean, lazy reconnect under
    # whichever loop asks for a connection next.
    await engine.dispose()


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)

    engine = make_engine(config.database_url)
    sessionmaker = make_sessionmaker(engine)
    asyncio.run(_seed_settings(engine, sessionmaker))

    aodb = AodbClient(config.aodb_api_url)
    gmi = GmiClient(config.gmi_api_url)
    scraper = AutoTrackScraper()

    bot_handle: BotHandle | None = None
    if config.ao_login and config.ao_password and config.ao_character:
        chat_client = AOChatClient(
            host=config.ao_chat_server,
            port=config.ao_chat_port,
            username=config.ao_login,
            password=config.ao_password,
            character_name=config.ao_character,
        )
        # A separate engine/pool, not the one above -- the bot thread runs
        # its own event loop (bot_thread_main), and asyncpg connections are
        # bound to whichever loop opened them. Sharing one pool between
        # uvicorn's loop and the bot's loop means a connection opened under
        # one gets checked out and used under the other, which asyncpg
        # rejects at the protocol level ("attached to a different loop"),
        # surfacing as 500s from /bot/poll:trigger and friends. Created
        # here (not inside bot_thread_main) so it exists before the thread
        # starts; create_async_engine itself is lazy, so this doesn't touch
        # the bot's loop before it's set as current there.
        bot_engine = make_engine(config.database_url)
        bot_sessionmaker = make_sessionmaker(bot_engine)
        bot = MarketBot(config, bot_sessionmaker, aodb, gmi, scraper, chat_client)
        bot_handle = BotHandle()
        thread = threading.Thread(target=bot_thread_main, args=(bot_handle, bot), daemon=False)
        thread.start()
    else:
        log.warning("ao_credentials_not_set", detail="starting in API-only mode, no AO chat connection")

    app = create_app(sessionmaker, aodb, gmi, scraper, config, bot_handle)
    uvicorn.run(app, host=config.api_host, port=config.api_port)


if __name__ == "__main__":
    main()
