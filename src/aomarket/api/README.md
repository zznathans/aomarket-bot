# api

The FastAPI control surface — every operation `MarketService` supports,
exposed over HTTP, plus a small set of endpoints for observing/poking the
bot thread directly.

## Files

- **`app.py`** — `create_app()`: wires the FastAPI app, stashes shared
  dependencies (`sessionmaker`, `aodb`, `gmi`, `scraper`, `config`,
  `bot_handle`) on `app.state`, registers a single exception handler that
  maps every [`MarketError`](../market/README.md) subclass to an HTTP
  status code, and mounts each router in `routes/`.
- **`deps.py`** — FastAPI dependency providers, most importantly
  `get_service()` (builds a per-request `MarketService`, including a
  `ChatSink` that's a no-op unless the bot thread is up) and
  `call_on_bot()` — the bridge that lets a request handler run a
  coroutine on the [bot thread](../bot/README.md)'s event loop via
  `asyncio.run_coroutine_threadsafe`, then awaits the result from
  FastAPI's own loop.
- **`auth_deps.py`** — API key enforcement, kept separate from `deps.py`
  since it's a distinct, security-sensitive concern. `require_player_key`
  (binds a route's own `{player}` path parameter to check the key is
  scoped to that player, or is an admin) and `require_admin_key`, both
  attached to routes via `dependencies=[Depends(...)]`. See
  [`auth/README.md`](../auth/README.md) for the issuance/verification
  logic itself.
- **`schemas.py`** — Pydantic request/response models for every route.
- **`routes/`** — One module per resource:
  - `health.py` — `/healthz` (always 200, status reflected in the body)
    and `/readyz` (reflects whether the bot thread has connected — stays
    false forever in API-only mode, so it's *not* used for the
    container's liveness/readiness probes; see the
    [Helm chart](../../../charts/aomarket-bot/README.md)).
  - `items.py` — item search/lookup, proxied through
    [`aodb`](../aodb/README.md).
  - `watch.py` — start/stop watching an item, current order book.
  - `users.py` — player registration, watchlist subscriptions and
    per-subscription filters, per-player stats.
  - `admin.py` — bulk untrack, admin stats lookups.
  - `status.py` — overall market/watch-list summary.
  - `bot.py` — bot connection status, `poll:trigger`/`autotrack:trigger`
    to force a cycle on demand, and `tell` to send a chat message
    directly.

  Every write route (`POST`/`PUT`/`DELETE`, except player `:register`)
  requires `require_player_key` or `require_admin_key` from
  `auth_deps.py` — see the root README's Authentication section for the
  scoping rules.

## How it's used

`main.py` calls `create_app()` with real implementations of every
dependency and runs it under `uvicorn` on the FastAPI event loop, while
the bot (if configured) runs on its own separate thread — see
[`bot/README.md`](../bot/README.md) for the concurrency model that
`call_on_bot()` bridges.
