from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Item:
    aoid: int
    name: str
    ql: int
    icon: int | None
    description: str | None


class AodbClient:
    """Thin wrapper around the aodb-api /api/items JSON endpoints: bare
    JSON array responses, X-Total-Count header for pagination, 404 JSON
    body on miss, unauthenticated.

    Was /v2/items until aodb-api's own restructure moved its JSON API
    under /api (see aodb's "redesign browse UI and move JSON API under
    /api") - /v2 hasn't existed for a while, which meant every lookup
    through this client 404'd regardless of whether the aoid was
    actually valid. Confirmed live: aoid 245990 ("Lava capsule") 404s at
    /v2/items/245990 and 200s with real data at /api/items/245990.
    """

    def __init__(self, base_url: str, http_client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_item(self, aoid: int) -> Item | None:
        response = await self._client.get(f"{self._base_url}/api/items/{aoid}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _item_from_json(response.json())

    async def search_items(
        self, query: str, ql: int | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[Item], int]:
        params: dict[str, str | int] = {"q": query, "limit": limit, "offset": offset}
        if ql is not None:
            params["ql"] = ql
        response = await self._client.get(f"{self._base_url}/api/items", params=params)
        response.raise_for_status()
        items = [_item_from_json(row) for row in response.json()]
        total_count = int(response.headers.get("X-Total-Count", len(items)))
        return items, total_count


def _item_from_json(data: dict) -> Item:
    return Item(
        aoid=data["id"],
        name=data["name"],
        ql=data["ql"],
        icon=data.get("icon"),
        description=data.get("description"),
    )
