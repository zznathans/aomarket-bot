# autotrack

Scrapes [ao-stonks.com](https://ao-stonks.com)'s "top traded items"
ranking so the bot can auto-track popular items without anyone manually
registering them for watch.

## Files

- **`scraper.py`** — `AutoTrackScraper` fetches paginated HTML
  (`{source_url}/items/{page}`) and `extract_aoids()` regex-matches item
  IDs out of the rendered item list. There's no JSON API for this
  ranking, so this is regex-scraped HTML by necessity — deliberately kept
  isolated in its own module so it stays easy to mock in tests and easy
  to swap out if ao-stonks.com's markup changes or a real API ever shows
  up.

## How it's used

`sync_top_traded_items()` on [`MarketService`](../market/README.md) calls
this scraper, resolves the returned AOIDs against
[`aodb`](../aodb/README.md), and adds new ones to the watch list.
Triggered on a timer by [`bot/scheduler.py`](../bot/README.md)'s
`autotrack_loop`, or on demand via the `/bot/autotrack:trigger` API
route.
