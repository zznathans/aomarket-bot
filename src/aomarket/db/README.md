# db

The data layer: SQLAlchemy (async) models and the two repositories
everything else in the app talks to instead of touching the database
directly.

## Files

- **`models.py`** — Declarative models for every table: `MarketUser`
  (registered players), `MarketWatch` (tracked items), `MarketHistory`
  (per-item poll snapshots), `MarketSubscription` (a player's watch
  filters), `MarketSeenOrder` (dedupe fingerprints for alerting),
  `MarketPendingAlert`, `MarketUserAction` (audit log), and `Setting`
  (typed key/value runtime config — poll interval, auto-track toggles,
  etc.).
- **`engine.py`** — `make_engine()`/`make_sessionmaker()`, the async
  engine/session factory used both by the running app and by tests
  (against a separate `aomarket_test` database — see
  [`tests/README.md`](../../../tests/README.md)).
- **`market_repo.py`** — `MarketRepo`: queries and mutations over watch
  items, history, and subscriptions.
- **`settings_repo.py`** — `SettingsRepo`: typed reads/writes over the
  `settings` table (`get_int`/`get_bool`/…), plus `seed_defaults()` run
  once at process startup ([`main.py`](../../main.py)) so the poll/
  auto-track loops always have values to read.

## Migrations

Schema changes go through Alembic — migration scripts live in
[`/migrations`](../../../migrations) at the repo root, driven by
`alembic.ini`. There's no separate migration `Job`; `main.py` (via the
bot process itself) is expected to be run against an already-migrated
database — run `alembic upgrade head` as part of your deploy step.

## How it's used

`MarketRepo` and `SettingsRepo` are constructed per-request/per-cycle by
[`MarketService`](../market/README.md), which is the only thing that
reaches into `db` directly. Neither the API routes nor the chat command
layer talk to this module directly.
