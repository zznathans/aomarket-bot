# aomarket-bot

| Category | Badges |
|---|---|
| CI | [![Lint](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/lint-3.14.json)](#python-version-support) [![Tests](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/tests-3.14.json)](#python-version-support) [![Docker](https://github.com/zznathans/aomarket-bot/actions/workflows/docker.yml/badge.svg)](https://github.com/zznathans/aomarket-bot/actions/workflows/docker.yml) [![Chart CI](https://github.com/zznathans/aomarket-bot/actions/workflows/chart-ci.yml/badge.svg)](https://github.com/zznathans/aomarket-bot/actions/workflows/chart-ci.yml) |
| Release | [![Release](https://github.com/zznathans/aomarket-bot/actions/workflows/release.yml/badge.svg)](https://github.com/zznathans/aomarket-bot/actions/workflows/release.yml) |
| Security | [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/zznathans/aomarket-bot/badge)](https://scorecard.dev/viewer/?uri=github.com/zznathans/aomarket-bot) [![Dependency review](https://github.com/zznathans/aomarket-bot/actions/workflows/dependency-review.yml/badge.svg)](https://github.com/zznathans/aomarket-bot/actions/workflows/dependency-review.yml) [![CII Best Practices](https://www.bestpractices.dev/projects/13996/badge)](https://www.bestpractices.dev/projects/13996) |
| License | [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE) |

A standalone Anarchy Online market-tracking bot: an asyncio AO chat
client for in-game `market`/`mkt` commands, a FastAPI control API for the
same functionality over HTTP, and a PostgreSQL-backed watch list that
polls item order books and auto-tracks popular items.

## Architecture

Two things run in one process:

- **FastAPI**, on `uvicorn`'s event loop — the HTTP control surface.
- **The AO chat bot**, on its own dedicated thread with its own event
  loop — only started if AO account credentials are configured. Without
  them, the process runs in **API-only mode**: no live AO chat
  connection, but every HTTP endpoint still works.

The two sides never share state directly; a small bridge
(`asyncio.run_coroutine_threadsafe`) lets the API thread schedule work
onto the bot thread's loop and await the result. Both the chat command
layer and the API routes are thin presentation layers over the exact
same business logic (`MarketService`) — a chat-originated `market watch`
and an API `POST /watch/{aoid}` end up calling the same code.

See [`src/aomarket/README.md`](src/aomarket/README.md) for the full
module map and concurrency model, and the README in each submodule for
what it does:

- [`aochat/`](src/aomarket/aochat/README.md) — AO chat protocol client
- [`aodb/`](src/aomarket/aodb/README.md) — item lookup/search client
- [`gmi/`](src/aomarket/gmi/README.md) — live order book client
- [`autotrack/`](src/aomarket/autotrack/README.md) — popular-item scraper
- [`db/`](src/aomarket/db/README.md) — models and repositories
- [`market/`](src/aomarket/market/README.md) — core business logic
- [`bot/`](src/aomarket/bot/README.md) — the bot thread and background loops
- [`api/`](src/aomarket/api/README.md) — the FastAPI control surface
- [`auth/`](src/aomarket/auth/README.md) — API key issuance and verification

## Quickstart

```bash
cp .env.example .env   # fill in AO_LOGIN/AO_PASSWORD/AO_CHARACTER to enable chat, or leave blank for API-only mode
docker compose up
```

This brings up Postgres and the bot together; the API is then available
at `http://localhost:8000` (interactive docs at `/docs`).

## Configuration

Every setting is an environment variable, loaded by `AppConfig`
(`src/aomarket/config.py`):

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://aomarket:aomarket@localhost:55432/aomarket` | SQLAlchemy/asyncpg connection string. |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | *(blank)* | Alternate way to configure the database, for setups (e.g. an operator-managed Postgres cluster) that hand out a per-role username/password Secret rather than a single connection string. Setting `DB_HOST` composes `DATABASE_URL` from these instead of using it directly. |
| `AO_LOGIN`, `AO_PASSWORD`, `AO_CHARACTER` | *(blank)* | Leave all blank to run in API-only mode. |
| `AO_OWNER_CHARACTER` | *(blank)* | Player always treated as admin for API key purposes (see Authentication below), regardless of `MarketUser.is_admin`. Bootstraps the first admin; leave blank to require setting `is_admin` directly instead. |
| `API_KEY_PEPPER` | *(blank)* | Server-side secret mixed into API key hashing. Leave blank to hash without one (keys are still PBKDF2-hardened either way). Changing this invalidates every previously-issued key. |
| `AO_CHAT_SERVER` | `chat.d1.funcom.com` | |
| `AO_CHAT_PORT` | `7105` | |
| `AODB_API_URL` | `https://aodb.ao.yeetbox.net` | Item lookup/search service. |
| `GMI_API_URL` | `https://gmi.nadybot.org` | Live order book service. |
| `API_HOST` | `0.0.0.0` | |
| `API_PORT` | `8000` | |
| `LOG_LEVEL` | `INFO` | |

Runtime behavior tuning (poll interval, auto-track on/off, subscription
limits, …) lives in the `settings` table instead, seeded with defaults
on startup — see [`db/README.md`](src/aomarket/db/README.md).

## Authentication

Every GET endpoint is open; every write endpoint requires an API key sent
as the `X-Api-Key` header. There's no HTTP signup — a key is only ever
issued to a player who's proven their identity by actually talking to the
bot in-game, via `market apikey generate`. That reply shows the raw key
once; save it, it can't be retrieved again (`market apikey generate` a
second time revokes the old one and issues a new one). `market apikey
revoke confirm` and `market apikey list` are also available.

A key generated this way is scoped to your own player-level writes only
(`/players/<you>/...`) — it can't touch another player's data or any of
the bot-wide endpoints (`/admin/*`, `/bot/*`, `/settings/*`,
`POST`/`DELETE /watch/{aoid}`). Those require an **admin** key: either the
player named in `AO_OWNER_CHARACTER` above, or any player with
`MarketUser.is_admin` set directly in the database.

See [`auth/README.md`](src/aomarket/auth/README.md) for how key
generation/verification works internally.

## Deploying

A Helm chart lives at [`charts/aomarket-bot`](charts/aomarket-bot/README.md)
and is published to this repo's own Helm repository on every release:

```bash
helm repo add aomarket-bot https://marketbot.ao.yeetbox.net/
helm repo update
helm install aomarket-bot aomarket-bot/aomarket-bot \
  --set aomarketBot.secret.databaseUrl="postgresql+asyncpg://user:pass@host:5432/dbname"
```

It expects an external PostgreSQL database — the chart doesn't bundle
one. See the chart's own README for the full values reference.

## Development

```bash
pip install -e ".[dev]"
docker compose up -d postgres
pytest
ruff check .
```

See [`tests/README.md`](tests/README.md) for how the test suite is laid
out and what needs a live Postgres.

### Python version support

`pyproject.toml` requires Python >=3.12, but CI runs lint and the test
suite against a wider range on every push to `main` so regressions on
other versions surface early. Only **3.14** is a required check for
merging — the rest are informational (`fail-fast: false`, so one
version failing doesn't block the others from reporting).

| Version | Lint | Tests |
| --- | --- | --- |
| 3.12 | ![lint 3.12](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/lint-3.12.json) | ![tests 3.12](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/tests-3.12.json) |
| 3.13 | ![lint 3.13](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/lint-3.13.json) | ![tests 3.13](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/tests-3.13.json) |
| 3.14 (supported) | ![lint 3.14](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/lint-3.14.json) | ![tests 3.14](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/tests-3.14.json) |
| 3.15.0-rc.1 | ![lint 3.15](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/lint-3.15.0-rc.1.json) | ![tests 3.15](https://img.shields.io/endpoint?url=https://marketbot.ao.yeetbox.net/badges/tests-3.15.0-rc.1.json) |

These reflect the most recent push to `main` (each matrix leg in
[`ci.yml`](.github/workflows/ci.yml) publishes its own status to
`gh-pages` as a small JSON file, since GitHub's own workflow badges only
report the workflow as a whole, not individual matrix legs).

Commits must follow [Conventional Commits](https://www.conventionalcommits.org/)
(`fix(component): …`, `feat(component): …`, …) — enforced by CI and
required for [semantic-release](https://github.com/semantic-release/semantic-release)
to cut releases correctly.

## License

[GPL-3.0](LICENSE)
