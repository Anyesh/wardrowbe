from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.packing_service import (
    TripWeather,
    choose_items,
    plan_quantities,
    summarize_forecast,
)
from app.services.weather_service import DailyForecast
from app.utils.timezone import get_user_today


def _day(day: date, low: float, high: float, rain: int = 0) -> DailyForecast:
    return DailyForecast(
        date=day.isoformat(),
        temp_min=low,
        temp_max=high,
        precipitation_chance=rain,
        condition="rainy" if rain > 50 else "sunny",
        condition_code=61 if rain > 50 else 0,
    )


def _item(item_type: str, **fields) -> ClothingItem:
    return ClothingItem(
        type=item_type,
        image_path=f"test/{item_type}.jpg",
        status=ItemStatus.ready,
        season=fields.pop("season", []),
        favorite=fields.pop("favorite", False),
        **fields,
    )


class TestSummarizeForecast:
    def test_uses_only_days_inside_the_trip(self):
        start = date(2026, 3, 10)
        forecast = [
            _day(start - timedelta(days=1), -10, -5),
            _day(start, 4, 12, rain=80),
            _day(start + timedelta(days=1), 6, 15),
            _day(start + timedelta(days=5), 20, 30),
        ]
        weather = summarize_forecast(forecast, start, start + timedelta(days=1), "spring")
        assert (weather.temp_min, weather.temp_max) == (4, 15)
        assert weather.rain_days == 1
        assert weather.estimated is False
        assert len(weather.days) == 2

    def test_light_rain_counts_even_at_a_low_chance(self):
        start = date(2026, 3, 10)
        drizzle = DailyForecast(
            date=start.isoformat(),
            temp_min=8,
            temp_max=14,
            precipitation_chance=30,
            condition="light rain",
            condition_code=61,
        )
        assert summarize_forecast([drizzle], start, start, "spring").rain_days == 1

    def test_falls_back_to_the_season_beyond_the_forecast(self):
        weather = summarize_forecast([], date(2026, 7, 1), date(2026, 7, 5), "summer")
        assert weather.estimated is True
        assert weather.temp_max > 25
        assert weather.days == []


class TestPlanQuantities:
    def test_cold_trip_needs_layers_and_accessories(self):
        weather = TripWeather(temp_min=-2, temp_max=5, rain_days=0, estimated=False)
        plan = plan_quantities(5, weather, laundry=False, preferences=None)
        assert plan["base_top"] == 5
        assert plan["bottom"] == 2
        assert plan["outer_layer"] == 1
        assert plan["mid_layer"] == 1
        assert plan["accessory"] == 2

    def test_hot_dry_trip_skips_outerwear(self):
        weather = TripWeather(temp_min=24, temp_max=34, rain_days=0, estimated=False)
        plan = plan_quantities(3, weather, laundry=False, preferences=None)
        assert plan["outer_layer"] == 0
        assert plan["mid_layer"] == 0
        assert plan["accessory"] == 0

    def test_laundry_caps_the_number_of_tops(self):
        weather = TripWeather(temp_min=12, temp_max=20, rain_days=0, estimated=False)
        assert plan_quantities(14, weather, laundry=True, preferences=None)["base_top"] == 4
        assert plan_quantities(14, weather, laundry=False, preferences=None)["base_top"] == 10

    def test_rain_adds_a_layer_and_spare_shoes(self):
        weather = TripWeather(temp_min=15, temp_max=22, rain_days=2, estimated=False)
        plan = plan_quantities(2, weather, laundry=False, preferences=None)
        assert plan["outer_layer"] == 1
        assert plan["footwear"] == 2


class TestChooseItems:
    def test_never_packs_summer_clothes_for_the_snow(self):
        weather = TripWeather(temp_min=-5, temp_max=2, rain_days=0, estimated=False)
        coat = _item("coat", material="wool", season=["winter"])
        shorts = _item("shorts", season=["summer"])
        jeans = _item("jeans", season=["all-season"])
        groups = choose_items(
            [coat, shorts, jeans],
            {"outer_layer": 1, "bottom": 2},
            weather,
            "winter",
            "casual",
            None,
        )
        by_role = {g.role: g for g in groups}
        assert by_role["outer_layer"].items == [coat]
        assert shorts not in by_role["bottom"].items
        assert jeans in by_role["bottom"].items

    def test_optional_roles_without_items_are_not_gaps(self):
        weather = TripWeather(temp_min=15, temp_max=22, rain_days=0, estimated=False)
        groups = choose_items(
            [_item("t-shirt")],
            {"base_top": 1, "full_body": 1, "footwear": 1},
            weather,
            "spring",
            "casual",
            None,
        )
        roles = {g.role: g for g in groups}
        assert "full_body" not in roles
        assert roles["footwear"].items == []

    def test_keeps_role_order_and_skips_roles_not_needed(self):
        weather = TripWeather(temp_min=15, temp_max=22, rain_days=0, estimated=False)
        groups = choose_items(
            [_item("t-shirt"), _item("sneakers")],
            {"base_top": 1, "footwear": 1, "outer_layer": 0},
            weather,
            "spring",
            "casual",
            None,
        )
        assert [g.role for g in groups] == ["base_top", "footwear"]


class TestPackingApi:
    @pytest.mark.asyncio
    async def test_plans_from_the_wardrobe(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        for item_type in ("t-shirt", "t-shirt", "jeans", "sneakers"):
            db_session.add(
                ClothingItem(
                    user_id=test_user.id,
                    type=item_type,
                    image_path=f"test/{item_type}.jpg",
                    status=ItemStatus.ready,
                )
            )
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="coat",
                image_path="test/archived.jpg",
                status=ItemStatus.archived,
                is_archived=True,
            )
        )
        await db_session.commit()

        start = get_user_today(test_user) + timedelta(days=1)
        forecast = [_day(start + timedelta(days=i), 16, 24) for i in range(3)]
        with (
            patch(
                "app.api.packing.WeatherService.geocode_location_name",
                AsyncMock(return_value=(41.9, 12.5, "Roma")),
            ),
            patch(
                "app.api.packing.WeatherService.get_daily_forecast",
                AsyncMock(return_value=forecast),
            ),
        ):
            response = await client.post(
                "/api/v1/packing",
                json={
                    "destination": "Roma",
                    "start_date": start.isoformat(),
                    "end_date": (start + timedelta(days=2)).isoformat(),
                    "occasion": "casual",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["destination"] == "Roma"
        assert data["days"] == 3
        assert data["estimated"] is False
        groups = {g["role"]: g for g in data["groups"]}
        assert len(groups["base_top"]["items"]) == 2
        assert groups["base_top"]["needed"] == 3
        assert "base_top" in data["missing_roles"]
        packed = [i for g in data["groups"] for i in g["items"]]
        assert all(not i["is_archived"] for i in packed)
        assert all(i["image_url"] for i in packed)

    @pytest.mark.asyncio
    async def test_unknown_destination(self, client: AsyncClient, test_user, auth_headers):
        start = get_user_today(test_user) + timedelta(days=1)
        with patch(
            "app.api.packing.WeatherService.geocode_location_name", AsyncMock(return_value=None)
        ):
            response = await client.post(
                "/api/v1/packing",
                json={
                    "destination": "Nowhere",
                    "start_date": start.isoformat(),
                    "end_date": start.isoformat(),
                },
                headers=auth_headers,
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_reversed_dates(self, client: AsyncClient, test_user, auth_headers):
        start = get_user_today(test_user) + timedelta(days=5)
        response = await client.post(
            "/api/v1/packing",
            json={
                "destination": "Roma",
                "start_date": start.isoformat(),
                "end_date": (start - timedelta(days=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_sign_in(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/packing",
            json={"destination": "Roma", "start_date": "2030-01-01", "end_date": "2030-01-02"},
        )
        assert response.status_code == 401
