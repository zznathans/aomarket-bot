# market

The core business logic: everything about registering players, watching
items, polling order books, auto-tracking, and subscriptions/alerts —
transport-agnostic, with no knowledge of chat or HTTP.

## Files

- **`service.py`** — `MarketService`, the single entry point both the
  chat command layer and the API routes call into. Takes a `MarketRepo`
  ([`db`](../db/README.md)), `SettingsRepo`, `AodbClient`
  ([`aodb`](../aodb/README.md)), `GmiClient` ([`gmi`](../gmi/README.md)),
  `AutoTrackScraper` ([`autotrack`](../autotrack/README.md)), and an
  optional `ChatSink` — a set of callback hooks (`send_privgroup`,
  `send_tell`, `is_online`) used only for private-channel logging and
  delivering watchlist alerts, left as no-ops when the bot isn't
  chat-connected. Raises typed errors (`errors.py`) rather than doing any
  presentation itself.
- **`errors.py`** — `MarketError` and its subclasses
  (`UnknownItemError`, `AlreadyWatchingError`, `SubscriptionLimitError`,
  …), each carrying just enough structured data (e.g. the `aoid`) for
  callers to render their own message. Both the FastAPI exception handler
  ([`api/app.py`](../api/README.md)) and `commands.py` below catch these
  and adapt them to their own response format.
- **`commands.py`** — In-game `market`/`mkt` chat command dispatch: a
  regex sub-dispatch table (most specific pattern first) that calls
  straight into `MarketService` — the same methods the API routes call —
  and renders results via `rendering.py`. Also dispatches `apikey
  generate`/`revoke`/`list` into an `AuthService`
  ([`auth/`](../auth/README.md)) — the only way a player gets an API key
  for the HTTP API.
- **`parsing.py`** — Shared shorthand parsing/formatting used by both
  `commands.py` and `rendering.py`: credit shorthand (`1.5m` ↔
  1,500,000), QL, and range parsing.
- **`rendering.py`** — Plain-text chat reply formatting. Deliberately
  plain text, no AO-client-only markup (`chatcmd()`/`make_blob()`/
  `itemref://`) — that presentation layer has no meaning outside a live
  AO chat window.

## How it's used

[`bot/runner.py`](../bot/README.md) constructs a fresh `MarketService`
per chat command / poll cycle via `MarketBot.make_service()`; the API
layer does the same per-request via FastAPI's dependency injection (see
[`api/deps.py`](../api/README.md)). Both paths converge on the exact same
service methods — chat and HTTP are just two presentations of the same
logic.
