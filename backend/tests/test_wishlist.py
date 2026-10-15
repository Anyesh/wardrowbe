from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.link_preview import LinkPreview, PreviewError, ensure_public_host, parse_preview

SHOP_PAGE = """<html><head>
<title>Fallback title</title>
<meta property="og:title" content="Giacca in lana blu">
<meta property="og:image" content="/img/jacket.jpg">
<meta property="og:site_name" content="Negozio">
<meta property="product:price:amount" content="129,90">
<meta property="product:price:currency" content="eur">
</head><body></body></html>"""

JSON_LD_PAGE = """<html><head><title>Sneakers</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Sneakers",
 "image": ["https://cdn.example.com/s.jpg"],
 "offers": {"@type": "Offer", "price": "1.299,00", "priceCurrency": "EUR"}}
</script></head></html>"""


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (300, 300), (40, 40, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestParsePreview:
    def test_reads_open_graph_and_product_tags(self):
        preview = parse_preview("https://shop.example.com/p/1", SHOP_PAGE)
        assert preview.title == "Giacca in lana blu"
        assert preview.image_url == "https://shop.example.com/img/jacket.jpg"
        assert preview.price == Decimal("129.90")
        assert preview.currency == "EUR"
        assert preview.site == "Negozio"

    def test_falls_back_to_json_ld_offers(self):
        preview = parse_preview("https://shop.example.com/s", JSON_LD_PAGE)
        assert preview.title == "Sneakers"
        assert preview.price == Decimal("1299.00")
        assert preview.image_url == "https://cdn.example.com/s.jpg"

    def test_survives_a_page_without_tags(self):
        preview = parse_preview("https://example.com", "<html><body>hi</body></html>")
        assert preview.title is None and preview.image_url is None and preview.price is None


class TestPublicHostsOnly:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["127.0.0.1", "192.168.1.10", "10.0.0.5", "localhost", "::1"])
    async def test_refuses_the_local_network(self, host):
        with pytest.raises(PreviewError):
            await ensure_public_host(host)


class TestWishlistApi:
    @pytest.mark.asyncio
    async def test_add_edit_buy_and_delete(self, client: AsyncClient, auth_headers):
        created = await client.post(
            "/api/v1/wishlist",
            json={
                "name": "Giacca blu",
                "notes": "Taglia M, in saldo a gennaio",
                "link": "https://shop.example.com/p/1",
                "image_url": "https://shop.example.com/img/jacket.jpg",
                "price": "129.90",
                "item_type": "jacket",
                "priority": 1,
            },
            headers=auth_headers,
        )
        assert created.status_code == 201, created.json()
        entry = created.json()
        assert entry["photo_url"] == "https://shop.example.com/img/jacket.jpg"
        assert entry["bought"] is False

        bought = await client.patch(
            f"/api/v1/wishlist/{entry['id']}", json={"bought": True}, headers=auth_headers
        )
        assert bought.status_code == 200 and bought.json()["bought"] is True
        assert bought.json()["notes"] == "Taglia M, in saldo a gennaio"

        listed = await client.get("/api/v1/wishlist", headers=auth_headers)
        assert [e["id"] for e in listed.json()] == [entry["id"]]

        removed = await client.delete(f"/api/v1/wishlist/{entry['id']}", headers=auth_headers)
        assert removed.status_code == 204
        assert (await client.get("/api/v1/wishlist", headers=auth_headers)).json() == []

    @pytest.mark.asyncio
    async def test_uploaded_photo_takes_precedence(self, client: AsyncClient, auth_headers):
        entry = (
            await client.post(
                "/api/v1/wishlist",
                json={"name": "Scarpe", "image_url": "https://cdn.example.com/x.jpg"},
                headers=auth_headers,
            )
        ).json()
        response = await client.put(
            f"/api/v1/wishlist/{entry['id']}/image",
            files={"image": ("scarpe.jpg", _jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["photo_url"].startswith("/api/v1/images/")

    @pytest.mark.asyncio
    async def test_rejects_non_web_links_and_unknown_types(self, client: AsyncClient, auth_headers):
        bad_link = await client.post(
            "/api/v1/wishlist",
            json={"name": "x", "link": "file:///etc/passwd"},
            headers=auth_headers,
        )
        assert bad_link.status_code == 422
        bad_type = await client.post(
            "/api/v1/wishlist", json={"name": "x", "item_type": "spaceship"}, headers=auth_headers
        )
        assert bad_type.status_code == 422

    @pytest.mark.asyncio
    async def test_cannot_touch_someone_elses_entry(self, client: AsyncClient, auth_headers):
        response = await client.patch(
            f"/api/v1/wishlist/{uuid4()}", json={"bought": True}, headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_uses_the_page(self, client: AsyncClient, auth_headers):
        preview = LinkPreview(
            url="https://shop.example.com/p/1",
            title="Giacca",
            image_url="https://shop.example.com/i.jpg",
            price=Decimal("50"),
            currency="EUR",
            site="Negozio",
        )
        with patch("app.api.wishlist.fetch_preview", AsyncMock(return_value=preview)):
            response = await client.post(
                "/api/v1/wishlist/preview",
                json={"url": "https://shop.example.com/p/1"},
                headers=auth_headers,
            )
        assert response.status_code == 200
        assert response.json()["title"] == "Giacca"

    @pytest.mark.asyncio
    async def test_preview_of_a_local_address_is_refused(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/wishlist/preview",
            json={"url": "http://127.0.0.1:8000/api/v1/health"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_suggestions_point_at_the_thin_roles(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        for item_type in ["t-shirt"] * 7 + ["jeans"]:
            db_session.add(
                ClothingItem(
                    user_id=test_user.id,
                    type=item_type,
                    image_path="x.jpg",
                    status=ItemStatus.ready,
                )
            )
        await db_session.commit()
        response = await client.get("/api/v1/wishlist/suggestions", headers=auth_headers)
        roles = [s["role"] for s in response.json()]
        assert "base_top" not in roles
        assert roles[0] in ("footwear", "outer_layer", "mid_layer")
        assert {"role": "bottom", "have": 1, "target": 3} in response.json()
