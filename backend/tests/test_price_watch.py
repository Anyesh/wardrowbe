from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.item import ClothingItem, ItemStatus
from app.models.wishlist import WishlistItem
from app.services.link_preview import LinkPreview
from app.services.price_watch import apply_price, drop_texts, due_query


def _item(item_type: str, seasons: list[str] | None = None, **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        type=item_type,
        image_path=f"{item_type}.jpg",
        status=ItemStatus.ready,
        season=seasons or [],
        **fields,
    )


class TestPriceWatch:
    def _entry(self, price: str | None, current: str | None = None) -> WishlistItem:
        return WishlistItem(
            name="Giacca",
            price=Decimal(price) if price else None,
            current_price=Decimal(current) if current else None,
            link="https://shop.example.com/p/1",
        )

    def test_reports_a_drop_once_per_new_low(self):
        now = datetime.now(UTC)
        entry = self._entry("129.90")
        drop = apply_price(entry, Decimal("99.00"), now)
        assert drop and drop.old == Decimal("129.90") and drop.new == Decimal("99.00")
        assert entry.price_dropped_at == now
        assert apply_price(entry, Decimal("99.00"), now) is None
        assert apply_price(entry, Decimal("89.00"), now) is not None

    def test_back_to_full_price_clears_the_drop(self):
        now = datetime.now(UTC)
        entry = self._entry("50", current="40")
        entry.price_dropped_at = now
        assert apply_price(entry, Decimal("50"), now) is None
        assert entry.price_dropped_at is None

    def test_never_checked_links_come_first(self):
        sql = str(due_query().compile(compile_kwargs={"literal_binds": False}))
        assert "NULLS FIRST" in sql.upper()

    @pytest.mark.parametrize(
        ("locale", "title"),
        [
            ("it", "Prezzo sceso"),
            ("de-DE", "Preis gesunken"),
            ("fr", "Baisse de prix"),
            ("ja", "値下がり"),
            ("ko", "가격 인하"),
            ("zh-CN", "降价"),
            ("zh-TW", "降價"),
            ("pt-BR", "Price drop"),
            (None, "Price drop"),
        ],
    )
    def test_alerts_speak_the_user_language(self, locale, title):
        assert drop_texts(locale)[0] == title

    def test_first_reading_sets_the_reference_price(self):
        entry = self._entry(None)
        assert apply_price(entry, Decimal("30"), datetime.now(UTC)) is None
        assert entry.price == Decimal("30")

    @pytest.mark.asyncio
    async def test_check_now_endpoint(self, client: AsyncClient, auth_headers):
        created = await client.post(
            "/api/v1/wishlist",
            json={"name": "Giacca", "link": "https://shop.example.com/p/1", "price": "100"},
            headers=auth_headers,
        )
        preview = LinkPreview(url="https://shop.example.com/p/1", price=Decimal("80"))
        with patch("app.services.price_watch.fetch_preview", AsyncMock(return_value=preview)):
            response = await client.post("/api/v1/wishlist/check-prices", headers=auth_headers)
        assert response.status_code == 200, response.json()
        entry = response.json()[0]
        assert entry["id"] == created.json()["id"]
        assert Decimal(entry["current_price"]) == Decimal("80")
        assert entry["price_dropped_at"] is not None

    @pytest.mark.asyncio
    async def test_a_new_link_or_price_starts_the_watch_over(
        self, client: AsyncClient, auth_headers
    ):
        created = await client.post(
            "/api/v1/wishlist",
            json={"name": "Giacca", "link": "https://shop.example.com/p/1", "price": "100"},
            headers=auth_headers,
        )
        preview = LinkPreview(url="https://shop.example.com/p/1", price=Decimal("80"))
        with patch("app.services.price_watch.fetch_preview", AsyncMock(return_value=preview)):
            await client.post("/api/v1/wishlist/check-prices", headers=auth_headers)

        edited = await client.patch(
            f"/api/v1/wishlist/{created.json()['id']}",
            json={"link": "https://other.example.com/p/9"},
            headers=auth_headers,
        )
        assert edited.status_code == 200, edited.json()
        data = edited.json()
        assert data["current_price"] is None
        assert data["price_dropped_at"] is None

    @pytest.mark.asyncio
    async def test_an_undelivered_alert_is_tried_again(self, db_session, test_user):
        from app.models.notification import NotificationStatus
        from app.services.notification_providers import NotificationResult
        from app.workers.price_watch import _check_wishlist_prices

        entry = WishlistItem(
            user_id=test_user.id,
            name="Giacca",
            price=Decimal("100"),
            link="https://shop.example.com/p/1",
        )
        db_session.add(entry)
        await db_session.commit()

        failed = NotificationResult(channel="ntfy", status=NotificationStatus.failed, error="down")
        preview = LinkPreview(url=entry.link, price=Decimal("80"))
        with (
            patch("app.workers.price_watch.get_db_session", return_value=db_session),
            patch.object(db_session, "close", AsyncMock()),
            patch("app.services.price_watch.fetch_preview", AsyncMock(return_value=preview)),
            patch(
                "app.workers.price_watch.NotificationDispatcher.deliver",
                AsyncMock(return_value=[failed]),
            ),
        ):
            result = await _check_wishlist_prices({})

        assert result["drops"] == 1
        await db_session.refresh(entry)
        # The drop still shows, and the next check finds it new again and retries the alert.
        assert entry.price_dropped_at is not None
        assert entry.current_price is None
        assert apply_price(entry, Decimal("80"), datetime.now(UTC)) is not None
