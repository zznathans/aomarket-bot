# aomarket-bot

Helm chart to deploy [aomarket-bot](../../README.md) — the chart lives in
this repo rather than a separate one, alongside the code it deploys.

## Install

```bash
helm repo add aomarket-bot https://zznathans.github.io/aomarket-bot/
helm repo update
helm install aomarket-bot aomarket-bot/aomarket-bot \
  --set aomarketBot.secret.databaseUrl="postgresql+asyncpg://user:pass@host:5432/dbname"
```

The chart is published on every release, from the same `gh-pages` branch
this repo's GitHub Pages site is served from — see
[`.github/workflows/release.yml`](../../.github/workflows/release.yml)'s
`publish-chart` job.

## Requirements

- An **external PostgreSQL database** — this chart does not bundle or
  manage a database. Provide a working `DATABASE_URL` via
  `aomarketBot.secret.databaseUrl` (or an `ExternalSecret`, see below).
- AO account credentials are optional. Leave `aomarketBot.ao.character`
  and the `secret.aoLogin`/`secret.aoPassword` values blank to run in
  **API-only mode** (no live AO chat connection) — see
  [`src/aomarket/README.md`](../../src/aomarket/README.md) for what that
  mode does and doesn't do.

## Key values

| Value | Default | Notes |
| --- | --- | --- |
| `aomarketBot.replicaCount` | `1` | Keep at 1 — see the warning inline in `values.yaml`: the bot thread holds a single AO chat session, and there's no separate migration Job. |
| `aomarketBot.image.repository` / `.tag` | `ghcr.io/zznathans/aomarket-bot` / `1.0.0` | Always a real released semver; the pipeline never publishes a floating/`latest` tag. |
| `aomarketBot.image.variant` | `"regular"` | `"regular"` or `"slim"`. Every release publishes both. **The `slim` variant is built by dynamically analyzing the regular image and stripping anything not observed** — smaller, but can be less stable if a rarely-exercised code path needs something that got stripped. Only switch if you've validated it for your workload. |
| `aomarketBot.createSecret` | `true` | `true` renders a plain `Secret` from `aomarketBot.secret.*`. Set `false` to instead render an `ExternalSecret` from `aomarketBot.externalSecret.*` against a `ClusterSecretStore`. |
| `aomarketBot.aodbApiUrl` / `.gmiApiUrl` | live defaults | Only change if you're pointing at different instances of these services. |

See `values.yaml` for the complete, commented list.

## What it renders

- `Deployment` — single container, both liveness and readiness probes on
  `/healthz` (not `/readyz` — that reflects AO chat connection state,
  which stays false forever in API-only mode).
- `Service`, `ServiceAccount`.
- `Secret` or `ExternalSecret` (mutually exclusive, gated by
  `createSecret`) for `DATABASE_URL`/`AO_LOGIN`/`AO_PASSWORD`.
- `extraObjects` passthrough for anything else you want rendered
  alongside the chart's own resources.

There's no ArgoCD `Application` wiring in this chart — just the chart
itself, for now.
