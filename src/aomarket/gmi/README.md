# gmi

HTTP client for the [GMI](https://gmi.nadybot.org) live-order API — the
current buy/sell order book for a given item.

## Files

- **`client.py`** — `GmiClient`, wraps `GET {ApiUrl}/v1.0/aoid/{aoid}`.
  Returns `None` on any request error or malformed response rather than
  raising, since a stale/unavailable order book for one item shouldn't
  fail a whole poll cycle. `Orders` bundles the parsed `SellOrder`/
  `BuyOrder` lists.

## How it's used

Injected into [`MarketService`](../market/README.md) (as `gmi`) and
polled per watched item during the bot's poll cycle
([`bot/scheduler.py`](../bot/README.md)) to detect new orders and drive
watchlist alerts. Item identity (`aoid`) comes from
[`aodb`](../aodb/README.md) — this client only knows about orders, not
item metadata.
