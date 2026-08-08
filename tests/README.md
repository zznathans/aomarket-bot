# tests

## Layout

- **`unit/`** — Pure logic tests: AO chat packet framing/crypto, the
  `aodb`/`gmi` HTTP clients (via `respx`-mocked `httpx`), market command
  parsing, and `MarketService` behavior. No live Postgres or network
  needed — fast, run on every `pytest` invocation.
- **`api/`** — Full-stack API tests against `create_app()` wired up with
  fakes for `aodb`/`gmi` (`FakeAodbClient`/`FakeGmiClient` in
  `api/conftest.py`) and a real Postgres session (`db_session`
  from `conftest.py`), driven over an in-process ASGI transport
  (`httpx.ASGITransport`, no real socket).
- **`integration/`** — Cross-thread integration tests, e.g.
  `test_bot_thread_bridge.py` exercises the actual
  `BotHandle`/`call_on_bot` bridge between a real bot thread and an
  asyncio caller (see [`src/aomarket/bot/README.md`](../src/aomarket/bot/README.md)).

## Running

```bash
pip install -e ".[dev]"
docker compose up -d postgres   # or any reachable Postgres
pytest
```

`asyncio_mode = "auto"` is set in `pyproject.toml`, so async test
functions don't need `@pytest.mark.asyncio`.

## Postgres-dependent tests

Anything using the `db_session`/`api_client` fixtures needs a real
Postgres reachable at `TEST_DATABASE_URL` (defaults to
`postgresql+asyncpg://aomarket:aomarket@localhost:55432/aomarket_test` —
deliberately a separate database from `docker-compose.yml`'s default
`aomarket` dev database, since these fixtures drop and recreate every
table on each test). `tests/conftest.py`'s `requires_postgres` marker
auto-skips those tests when nothing is reachable at that URL, so a plain
`pytest` run without a database up still passes (skipping rather than
failing) — bring up Postgres first if you want that coverage locally.
