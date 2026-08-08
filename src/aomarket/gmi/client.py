from dataclasses import dataclass

import httpx

from aomarket.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class SellOrder:
    price: int
    ql: int
    count: int
    seller: str


@dataclass(frozen=True)
class BuyOrder:
    price: int
    min_ql: int
    max_ql: int
    count: int
    buyer: str


@dataclass(frozen=True)
class Orders:
    sell_orders: list[SellOrder]
    buy_orders: list[BuyOrder]


class GmiClient:
    """Wrapper around the GMI live-order API (default https://gmi.nadybot.org),
    matching Market.php::fetch_orders()'s GET {ApiUrl}/v1.0/aoid/{aoid} contract.
    Returns None on any error or malformed response, mirroring the PHP
    original's "return false" behavior rather than raising.
    """

    def __init__(self, base_url: str, http_client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_orders(self, aoid: int) -> Orders | None:
        try:
            response = await self._client.get(f"{self._base_url}/v1.0/aoid/{aoid}")
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("gmi_fetch_failed", aoid=aoid, error=str(exc))
            return None

        try:
            return _orders_from_json(data)
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("gmi_malformed_response", aoid=aoid, error=str(exc))
            return None


def _orders_from_json(data: dict) -> Orders:
    sell_orders = [
        SellOrder(price=row["price"], ql=row["ql"], count=row["count"], seller=row["seller"])
        for row in data["sell_orders"]
    ]
    buy_orders = [
        BuyOrder(
            price=row["price"],
            min_ql=row["min_ql"],
            max_ql=row["max_ql"],
            count=row["count"],
            buyer=row["buyer"],
        )
        for row in data["buy_orders"]
    ]
    return Orders(sell_orders=sell_orders, buy_orders=buy_orders)
