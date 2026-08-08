# aomarket

The `aomarket` Python package — everything that ships in the
`aomarket-bot` container.

## Module map

| Module | Purpose |
| --- | --- |
| [`aochat/`](aochat/README.md) | AO chat protocol client (login, tells, privgroup) |
| [`aodb/`](aodb/README.md) | aodb-api client — item lookup/search |
| [`gmi/`](gmi/README.md) | GMI client — live buy/sell order books |
| [`autotrack/`](autotrack/README.md) | ao-stonks.com scraper for auto-tracking popular items |
| [`db/`](db/README.md) | SQLAlchemy models and repositories |
| [`market/`](market/README.md) | Core business logic: `MarketService`, chat commands, rendering |
| [`bot/`](bot/README.md) | The AO chat session's dedicated thread and background loops |
| [`api/`](api/README.md) | FastAPI control surface |

Plus three top-level files with no submodule of their own:

- **`config.py`** — `AppConfig` (`pydantic-settings`): every environment
  variable the bot reads, with defaults, loaded once in `main.py`.
- **`logging.py`** — `structlog` configuration (`configure_logging`) and
  `get_logger()`, used throughout the codebase for structured log output.
- **`main.py`** — the process entry point: builds the DB engine, seeds
  default settings, starts the bot thread if AO credentials are present,
  and runs the FastAPI app under `uvicorn`.

## Concurrency model

The process has (at most) two independently-running event loops:

1. **FastAPI's loop**, run by `uvicorn` on the main thread.
2. **The bot's loop**, run on a dedicated non-daemon thread
   ([`bot/runner.py`](bot/README.md)) — only started at all if
   `AO_LOGIN`/`AO_PASSWORD`/`AO_CHARACTER` are all set. Without them, the
   process runs in **API-only mode**: no AO chat connection, `bot_handle`
   stays `None`, and every API route that would need the bot
   (`/bot/*`, and any [`MarketService`](market/README.md) `ChatSink`
   callback) either degrades to a no-op or returns 503.

The two loops never share state directly. The bridge is
`api.deps.call_on_bot()`, which schedules a coroutine onto the bot
thread's loop with `asyncio.run_coroutine_threadsafe` and awaits the
result from whichever loop called it. `BotHandle` (in
[`bot/runner.py`](bot/README.md)) is the only object shared between the
two threads — its `loop`/`bot` fields are published once, after login,
and are read-only from the API side after that; `ready` (a
`threading.Event`) is the memory barrier that makes that publication
safe to observe from the other thread.

## Request/command flow

Both the chat command layer ([`market/commands.py`](market/README.md))
and the HTTP API ([`api/routes/`](api/README.md)) are thin presentation
layers over the exact same [`MarketService`](market/README.md) methods —
neither talks to [`db`](db/README.md), [`aodb`](aodb/README.md),
[`gmi`](gmi/README.md), or [`autotrack`](autotrack/README.md) directly.
A chat-originated `market watch <item>` and an API `POST
/watch/{aoid}` end up calling the same code.
