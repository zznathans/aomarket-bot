"""ao-stonks.com "top traded items" HTML scraper.

Ported from Market.php::sync_top_traded_items() (Market.php:1705-1799). No
JSON API exists for this ranking, so it's regex-scraped from the rendered
item list -- fragile by nature (see the module-level warning in the PHP
original). Kept isolated so it's easily swappable/mockable.
"""

import re

import httpx

from aomarket.logging import get_logger

log = get_logger(__name__)

_ITEM_LINK_RE = re.compile(r'class="item-name"\s+href="/item/([0-9]+)"', re.IGNORECASE)


def extract_aoids(html: str) -> list[int]:
    return [int(m) for m in _ITEM_LINK_RE.findall(html)]


class AutoTrackScraper:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_page(self, source_url: str, page: int) -> str | None:
        url = f"{source_url.rstrip('/')}/items/{page}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            log.warning("autotrack_fetch_failed", url=url, error=str(exc))
            return None
