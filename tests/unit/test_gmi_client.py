import httpx
import pytest
import respx

from aomarket.gmi.client import GmiClient


@pytest.mark.asyncio
async def test_get_orders_parses_sell_and_buy_orders():
    with respx.mock(base_url="https://gmi.example") as mock:
        mock.get("/v1.0/aoid/12345").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sell_orders": [{"price": 1000, "ql": 200, "count": 3, "seller": "Alice"}],
                    "buy_orders": [{"price": 500, "min_ql": 1, "max_ql": 200, "count": 1, "buyer": "Bob"}],
                },
            )
        )
        client = GmiClient("https://gmi.example")
        orders = await client.get_orders(12345)

    assert orders is not None
    assert orders.sell_orders[0].price == 1000
    assert orders.sell_orders[0].seller == "Alice"
    assert orders.buy_orders[0].buyer == "Bob"


@pytest.mark.asyncio
async def test_get_orders_returns_none_on_http_error():
    with respx.mock(base_url="https://gmi.example") as mock:
        mock.get("/v1.0/aoid/999").mock(return_value=httpx.Response(500))
        client = GmiClient("https://gmi.example")
        orders = await client.get_orders(999)

    assert orders is None


@pytest.mark.asyncio
async def test_get_orders_returns_none_on_malformed_json():
    with respx.mock(base_url="https://gmi.example") as mock:
        mock.get("/v1.0/aoid/999").mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
        client = GmiClient("https://gmi.example")
        orders = await client.get_orders(999)

    assert orders is None


@pytest.mark.asyncio
async def test_get_orders_returns_none_on_non_json_body():
    with respx.mock(base_url="https://gmi.example") as mock:
        mock.get("/v1.0/aoid/999").mock(return_value=httpx.Response(200, text="not json"))
        client = GmiClient("https://gmi.example")
        orders = await client.get_orders(999)

    assert orders is None
