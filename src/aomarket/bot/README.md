# bot

Runs the AO chat session on its own thread and drives the two background
loops (poll and auto-track) that keep watched items up to date.

## Files

- **`runner.py`** — `MarketBot` (owns the chat client, builds a fresh
  `MarketService` per operation via `make_service()`, and a fresh
  `AuthService` via `make_auth_service()` — used by the `apikey` chat
  commands, see [`auth/README.md`](../auth/README.md)), `BotHandle` (the
  *only* object shared between the FastAPI thread and the bot thread —
  `loop`/`bot` are published once after login, then read-only from the
  API side; `ready` is the memory barrier for that publication), and
  `bot_thread_main()`, the actual thread entry point: creates a fresh
  event loop, logs in, then calls `run_forever()`. A tell's sender
  identity (`_handle_tell`) is resolved to their character name via
  `AOChatClient.name_for_id()` where possible, falling back to their
  numeric character id if the server hasn't pushed that mapping yet.
- **`admin_commands.py`** — `handle_admin_command()`: the top-level
  `!settings` command (list/get/set entries in the
  [`Setting`](../db/README.md) table), admin-only via
  `AuthService.is_admin_player()`. Deliberately separate from the
  `market`/`mkt` namespace in [`market/commands.py`](../market/README.md)
  and checked first in `_handle_tell`, so it never passes through that
  module's `Enabled` gate — an admin locked out by a disabled Market
  module can still recover it from in-game. Returns `None` (not a string)
  for non-admins and unrecognized messages, so `_handle_tell` falls
  through to the normal market dispatch with no indication the command
  exists.
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
