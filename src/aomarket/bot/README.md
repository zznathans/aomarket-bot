# bot

Runs the AO chat session on its own thread and drives the two background
loops (poll and auto-track) that keep watched items up to date.

## Files

- **`runner.py`** — `MarketBot` (owns the chat client, builds a fresh
  `MarketService` per operation via `make_service()`), `BotHandle` (the
  *only* object shared between the FastAPI thread and the bot thread —
  `loop`/`bot` are published once after login, then read-only from the
  API side; `ready` is the memory barrier for that publication), and
  `bot_thread_main()`, the actual thread entry point: creates a fresh
  event loop, logs in, then calls `run_forever()`.
- **`scheduler.py`** — `poll_loop()` and `autotrack_loop()`: plain
  `asyncio.sleep` loops (no persisted-timer table) that re-read their
  interval [`Setting`](../db/README.md) every cycle, so a setting change
  applies without a restart, and never let one bad cycle kill the loop
  (`except Exception: log + retry`, `except CancelledError: raise`).
  `autotrack_loop` also does a startup catch-up run if the last sync is
  staler than the configured interval.

## Concurrency model

The bot runs on a dedicated, non-daemon thread with its own asyncio event
loop — entirely separate from the FastAPI/uvicorn event loop `main.py`
runs on. The API reaches into the bot thread by scheduling coroutines
onto `BotHandle.loop` via `asyncio.run_coroutine_threadsafe` (see
[`api/README.md`](../api/README.md)'s `call_on_bot` bridge) rather than
sharing any state directly. If `AO_LOGIN`/`AO_PASSWORD`/`AO_CHARACTER`
aren't set, this thread is never started at all — the process runs in
API-only mode, and `BotHandle` stays `None`.
