from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.pagination import PaginationParams

app = FastAPI()


@app.get("/things")
async def list_things(pagination: Annotated[PaginationParams, Depends()]) -> dict:
    return {"page": pagination.page, "page_size": pagination.page_size}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_defaults_to_the_first_page_of_twenty(client):
    response = await client.get("/things")
    assert response.status_code == 200
    assert response.json() == {"page": 1, "page_size": 20}


async def test_accepts_the_cap(client):
    response = await client.get("/things", params={"page": 3, "page_size": 100})
    assert response.json() == {"page": 3, "page_size": 100}


@pytest.mark.parametrize(
    "params",
    [{"page_size": 101}, {"page_size": 0}, {"page": 0}],
)
async def test_rejects_out_of_range_values(client, params):
    response = await client.get("/things", params=params)
    assert response.status_code == 422


def test_query_parameter_names_are_page_and_page_size():
    params = app.openapi()["paths"]["/things"]["get"]["parameters"]
    assert [(p["name"], p["in"]) for p in params] == [("page", "query"), ("page_size", "query")]


@pytest.mark.parametrize(
    ("page", "page_size", "total", "expected"),
    [(1, 20, 21, True), (1, 20, 20, False), (2, 20, 41, True), (3, 20, 41, False)],
)
def test_has_more(page, page_size, total, expected):
    assert PaginationParams(page=page, page_size=page_size).has_more(total) is expected
