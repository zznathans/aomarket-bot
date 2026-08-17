# aodb

HTTP client for [aodb-api](https://aodb.ao.yeetbox.net), the item
lookup/search service this bot uses to resolve Anarchy Online item names
and metadata.

## Files

- **`client.py`** — `AodbClient`, a thin `httpx`-based wrapper around the
  aodb-api `/api/items` endpoints. Handles the specifics of that API: bare
  JSON array responses (no envelope), pagination via the `X-Total-Count`
  response header, and a JSON body on a 404 miss rather than an empty
  array. `Item` is the frozen dataclass every lookup returns (`aoid`,
  `name`, `ql`, `icon`, `description`).

## How it's used

Injected into [`MarketService`](../market/README.md) (as `aodb`) for item
lookups and search — it's the only source of item metadata the bot has;
[`gmi`](../gmi/README.md) supplies live order data for a given item once
it's known via this client.
