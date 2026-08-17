import httpx
import pytest
import respx

from aomarket.aodb.client import AodbClient, Item


@pytest.mark.asyncio
async def test_get_item_returns_item_on_200():
    with respx.mock(base_url="https://aodb.example") as mock:
        mock.get("/api/items/2").mock(
            return_value=httpx.Response(
                200, json={"id": 2, "name": "Notum Splitter", "ql": 150, "icon": 54321, "description": None}
            )
        )
        client = AodbClient("https://aodb.example")
        item = await client.get_item(2)

    assert item == Item(aoid=2, name="Notum Splitter", ql=150, icon=54321, description=None)


@pytest.mark.asyncio
async def test_get_item_returns_none_on_404():
    with respx.mock(base_url="https://aodb.example") as mock:
        mock.get("/api/items/999999").mock(
            return_value=httpx.Response(404, json={"detail": "No item with id 999999"})
        )
        client = AodbClient("https://aodb.example")
        item = await client.get_item(999999)

    assert item is None


@pytest.mark.asyncio
async def test_search_items_parses_list_and_total_count_header():
    with respx.mock(base_url="https://aodb.example") as mock:
        mock.get("/api/items", params={"q": "splitter", "limit": 50, "offset": 0}).mock(
            return_value=httpx.Response(
                200,
                json=[{"id": 2, "name": "Notum Splitter", "ql": 150, "icon": 54321, "description": None}],
                headers={"X-Total-Count": "1"},
            )
        )
        client = AodbClient("https://aodb.example")
        items, total = await client.search_items("splitter")

    assert total == 1
    assert items[0].name == "Notum Splitter"


@pytest.mark.asyncio
async def test_search_items_empty_result():
    with respx.mock(base_url="https://aodb.example") as mock:
        mock.get("/api/items", params={"q": "doesnotexist", "limit": 50, "offset": 0}).mock(
            return_value=httpx.Response(200, json=[], headers={"X-Total-Count": "0"})
        )
        client = AodbClient("https://aodb.example")
        items, total = await client.search_items("doesnotexist")

    assert items == []
    assert total == 0
