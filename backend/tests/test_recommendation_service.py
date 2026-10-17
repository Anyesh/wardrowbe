import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus, TimeOfDay
from app.models.preference import UserPreference
from app.models.user import User
from app.services.item_scorer import ScoredItem
from app.services.recommendation_service import (
    RECOMMENDATION_PROMPT,
    AIRecommendationError,
    RecommendationService,
    cached_suggestion_fits,
    fill_best_partial,
    format_temp_range_text,
    get_time_of_day,
    resolve_outfit_items,
    suggestion_context,
)
from app.services.weather_service import WeatherData


def _make_user(timezone: str = "UTC") -> User:
    uid = uuid4()
    return User(
        id=uid,
        external_id=f"test-{uid}",
        email=f"test-{uid}@example.com",
        display_name="Test",
        timezone=timezone,
        is_active=True,
    )


class TestGetTimeOfDay:
    @pytest.mark.parametrize(
        "hour,expected",
        [
            (6, "morning"),
            (9, "morning"),
            (11, "morning"),
            (12, "afternoon"),
            (14, "afternoon"),
            (16, "afternoon"),
            (17, "evening"),
            (19, "evening"),
            (20, "evening"),
            (21, "night"),
            (23, "night"),
            (0, "night"),
            (3, "night"),
            (5, "night"),
        ],
    )
    def test_time_buckets(self, hour, expected):
        user = _make_user("UTC")
        mock_dt = datetime(2026, 3, 8, hour, 30, 0, tzinfo=UTC)
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_time_of_day(user)
        assert result == expected

    def test_respects_user_timezone(self):
        user = _make_user("Asia/Kolkata")
        mock_dt = datetime(2026, 3, 8, 13, 30, 0, tzinfo=UTC)
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_time_of_day(user)
        assert result == "evening"

    def test_invalid_timezone_falls_back_to_utc(self):
        user = _make_user("Invalid/Timezone")
        mock_dt = datetime(2026, 3, 8, 9, 0, 0, tzinfo=UTC)
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_time_of_day(user)
        assert result == "morning"

    def test_none_timezone_falls_back_to_utc(self):
        user = _make_user()
        user.timezone = None
        mock_dt = datetime(2026, 3, 8, 22, 0, 0, tzinfo=UTC)
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_time_of_day(user)
        assert result == "night"


class TestPromptTemplate:
    def test_prompt_contains_fashion_principles(self):
        from app.services.recommendation_service import RECOMMENDATION_PROMPT

        prompt = RECOMMENDATION_PROMPT
        assert "Color coordination" in prompt
        assert "Monochrome" in prompt
        assert "Neutral base" in prompt
        assert "Analogous" in prompt
        assert "Texture and fabric" in prompt
        assert "Proportion and silhouette" in prompt
        assert "Time of day" in prompt
        assert "Full day" in prompt
        assert "{time_of_day}" in prompt

    def test_prompt_format_accepts_time_of_day(self):
        from app.services.recommendation_service import RECOMMENDATION_PROMPT

        formatted = RECOMMENDATION_PROMPT.format(
            occasion="casual",
            time_of_day="evening",
            temperature=22,
            feels_like=20,
            condition="clear",
            precipitation_chance=10,
            temp_range_text="",
            preferences_text="",
            items_text="[1] shirt | blue | cotton",
            mandatory_items_section="",
        )
        assert "evening" in formatted
        assert "casual" in formatted
        assert "22" in formatted

    def test_prompt_format_all_time_of_day_values(self):
        from app.services.recommendation_service import RECOMMENDATION_PROMPT

        for tod in ["morning", "afternoon", "evening", "night", "full day"]:
            formatted = RECOMMENDATION_PROMPT.format(
                occasion="work",
                time_of_day=tod,
                temperature=15,
                feels_like=13,
                condition="cloudy",
                precipitation_chance=30,
                temp_range_text="",
                preferences_text="",
                items_text="[1] shirt",
                mandatory_items_section="",
            )
            assert tod in formatted


def _weather(
    temp=20,
    temp_min=None,
    temp_max=None,
    is_day=True,
    window_min=None,
    window_max=None,
    condition="clear",
    feels_like=None,
    precipitation=0,
) -> WeatherData:
    return WeatherData(
        temperature=temp,
        feels_like=temp if feels_like is None else feels_like,
        humidity=50,
        precipitation_chance=precipitation,
        precipitation_mm=0,
        wind_speed=10,
        condition=condition,
        condition_code=0,
        is_day=is_day,
        uv_index=5,
        timestamp=datetime(2026, 3, 8, 12, 0),
        temp_min=temp_min,
        temp_max=temp_max,
        window_min=window_min,
        window_max=window_max,
    )


class TestPromptTemplateTempRange:
    def test_placeholder_in_template(self):
        assert "{temp_range_text}" in RECOMMENDATION_PROMPT

    def test_empty_formats_cleanly(self):
        formatted = RECOMMENDATION_PROMPT.format(
            occasion="casual",
            time_of_day="evening",
            temperature=22,
            feels_like=20,
            condition="clear",
            precipitation_chance=10,
            temp_range_text="",
            preferences_text="",
            items_text="[1] shirt",
            mandatory_items_section="",
        )
        assert "Temperature ahead" not in formatted

    def test_non_empty_appears_in_output(self):
        formatted = RECOMMENDATION_PROMPT.format(
            occasion="casual",
            time_of_day="evening",
            temperature=22,
            feels_like=20,
            condition="clear",
            precipitation_chance=10,
            temp_range_text="- Temperature ahead ranges from 5.0°C to 30.0°C, a large swing.",
            preferences_text="",
            items_text="[1] shirt",
            mandatory_items_section="",
        )
        assert "ranges from 5.0°C to 30.0°C" in formatted


class TestTempRangeText:
    def test_empty_when_min_missing(self):
        weather = _weather(temp=12, window_min=None, window_max=30)
        assert format_temp_range_text(weather) == ""

    def test_empty_when_max_missing(self):
        weather = _weather(temp=12, window_min=5, window_max=None)
        assert format_temp_range_text(weather) == ""

    def test_empty_below_swing_threshold(self):
        weather = _weather(temp=18, window_min=15, window_max=20)
        assert format_temp_range_text(weather) == ""

    def test_daily_range_without_window_is_empty(self):
        weather = _weather(temp=12, temp_min=5, temp_max=30)
        assert format_temp_range_text(weather) == ""

    def test_renders_regardless_of_is_day(self):
        weather = _weather(temp=12, window_min=5, window_max=30, is_day=False)
        text = format_temp_range_text(weather)
        assert "5.0°C" in text
        assert "30.0°C" in text
        assert "currently" not in text

    def test_degenerate_equal_bounds(self):
        weather = _weather(temp=20, window_min=20, window_max=20)
        assert format_temp_range_text(weather) == ""

    def test_float_rounding(self):
        weather = _weather(temp=12.34, window_min=5.06, window_max=30.049)
        text = format_temp_range_text(weather)
        assert "5.1°C" in text
        assert "30.0°C" in text


def _fit_prefs(updated_at=datetime(2026, 3, 8, 9, 0), **kwargs) -> UserPreference:
    return UserPreference(
        user_id=uuid4(),
        cold_threshold=10,
        hot_threshold=25,
        temperature_sensitivity="normal",
        updated_at=updated_at,
        **kwargs,
    )


_FIT_PREFS = _fit_prefs()


def _ctx(weather=None, time="morning", prefs=_FIT_PREFS, measurements=None) -> dict:
    return suggestion_context(weather or _weather(), TimeOfDay(time), prefs, measurements)


@pytest.mark.parametrize(
    ("cached", "now", "expected"),
    [
        (_ctx(), _ctx(), True),
        (_ctx(_weather(temp=20)), _ctx(_weather(temp=22.5)), True),
        (_ctx(_weather(temp=20)), _ctx(_weather(temp=23.5)), False),
        (_ctx(_weather(temp=2)), _ctx(_weather(temp=28)), False),
        (_ctx(_weather(temp=11)), _ctx(_weather(temp=9)), False),
        (_ctx(_weather(temp=24)), _ctx(_weather(temp=26)), False),
        (_ctx(_weather(temp=20)), _ctx(_weather(temp=20, feels_like=14)), False),
        (_ctx(), _ctx(_weather(condition="rainy")), False),
        (_ctx(_weather(precipitation=10)), _ctx(_weather(precipitation=40)), True),
        (_ctx(_weather(precipitation=10)), _ctx(_weather(precipitation=80)), False),
        (_ctx(), _ctx(time="evening"), False),
        (_ctx(), _ctx(_weather(temp=20, window_min=8, window_max=22)), False),
        (
            _ctx(_weather(temp=14, window_min=10.5, window_max=24)),
            _ctx(_weather(temp=14, window_min=10.5, window_max=26)),
            False,
        ),
        (
            _ctx(_weather(temp=12, window_min=8, window_max=22)),
            _ctx(_weather(temp=13, window_min=9, window_max=23)),
            True,
        ),
        (_ctx(prefs=None), _ctx(), False),
        (_ctx(prefs=_fit_prefs(updated_at=datetime(2026, 3, 8, 8, 0))), _ctx(), False),
        (_ctx(measurements={"height": 170}), _ctx(measurements={"height": 170}), True),
        (_ctx(measurements={"height": 170}), _ctx(measurements={"height": 180}), False),
    ],
    ids=[
        "same",
        "small-drift",
        "drift-past-tolerance",
        "cold-to-hot",
        "crosses-cold-threshold",
        "crosses-hot-threshold",
        "feels-colder",
        "condition-changed",
        "rain-chance-stays-low",
        "rain-became-likely",
        "time-of-day-changed",
        "swing-appeared",
        "window-top-crossed-hot",
        "window-small-drift",
        "preferences-created",
        "preferences-edited",
        "same-measurements",
        "measurements-edited",
    ],
)
def test_cached_suggestion_fits_only_the_context_it_was_made_for(cached, now, expected):
    stored = json.loads(json.dumps(cached))
    assert cached_suggestion_fits(stored, now, _FIT_PREFS) is expected


def test_a_cached_suggestion_without_context_does_not_fit():
    assert cached_suggestion_fits(None, _ctx(), _FIT_PREFS) is False
    assert cached_suggestion_fits({}, _ctx(), _FIT_PREFS) is False
    older = {k: v for k, v in _ctx().items() if k != "body_measurements"}
    assert cached_suggestion_fits(older, _ctx(), _FIT_PREFS) is False


def test_fill_best_partial_prefers_an_option_the_fill_can_complete():
    coat, jeans, boots, hoodie = uuid4(), uuid4(), uuid4(), uuid4()
    types = {coat: "coat", jeans: "jeans", boots: "boots", hoodie: "hoodie"}
    unfillable = ({"headline": "coat"}, [coat, jeans, boots])
    fillable = ({"headline": "jeans"}, [jeans])
    outfit_data, item_ids = fill_best_partial(
        [unfillable, fillable], [hoodie, boots, coat, jeans], types
    )
    assert outfit_data["headline"] == "jeans"
    assert set(item_ids) == {jeans, hoodie, boots}
    assert outfit_data["_filled_item_ids"] == [str(hoodie), str(boots)]
    assert "_filled_item_ids" not in unfillable[0]


def test_fill_best_partial_gives_up_when_no_option_can_be_completed():
    coat, jeans, boots, hoodie = uuid4(), uuid4(), uuid4(), uuid4()
    types = {coat: "coat", jeans: "jeans", boots: "boots", hoodie: "hoodie"}
    outfit_data = {"headline": "coat"}
    assert fill_best_partial([(outfit_data, [coat, jeans, boots])], [hoodie], types) is None
    assert "_filled_item_ids" not in outfit_data


class TestSuggestRequestTimeOfDay:
    @pytest.mark.asyncio
    async def test_suggest_accepts_time_of_day(self, client, test_user, auth_headers, db_session):
        from app.models.item import ClothingItem, ItemStatus

        for item_type in ["shirt", "pants", "sneakers"]:
            item = ClothingItem(
                user_id=test_user.id,
                type=item_type,
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
                primary_color="blue",
            )
            db_session.add(item)
        await db_session.commit()

        response = await client.post(
            "/api/v1/outfits/suggest",
            json={
                "occasion": "casual",
                "time_of_day": "evening",
                "weather_override": {
                    "temperature": 20,
                    "condition": "clear",
                },
            },
            headers=auth_headers,
        )
        assert response.status_code != 422

    @pytest.mark.asyncio
    async def test_suggest_rejects_invalid_time_of_day(self, client, test_user, auth_headers):
        response = await client.post(
            "/api/v1/outfits/suggest",
            json={
                "occasion": "casual",
                "time_of_day": "brunch",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_suggest_accepts_full_day(self, client, test_user, auth_headers):
        response = await client.post(
            "/api/v1/outfits/suggest",
            json={
                "occasion": "casual",
                "time_of_day": "full day",
                "weather_override": {"temperature": 20, "condition": "clear"},
            },
            headers=auth_headers,
        )
        assert response.status_code != 422

    @pytest.mark.asyncio
    async def test_suggest_allows_null_time_of_day(self, client, test_user, auth_headers):
        response = await client.post(
            "/api/v1/outfits/suggest",
            json={
                "occasion": "casual",
                "time_of_day": None,
                "weather_override": {
                    "temperature": 20,
                    "condition": "clear",
                },
            },
            headers=auth_headers,
        )
        assert response.status_code != 422


class TestSuggestEndpointRuntime:
    @pytest.mark.asyncio
    async def test_suggest_reaches_ready_item_count(
        self, client, test_user, auth_headers, db_session
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
            primary_color="blue",
        )
        outfit = Outfit(
            user_id=test_user.id,
            occasion="casual",
            status=OutfitStatus.pending,
            source=OutfitSource.on_demand,
        )
        outfit.feedback = None
        outfit.family_ratings = []
        outfit.items = [OutfitItem(item=item, position=0, layer_type=None)]

        db_session.add_all([item, outfit])
        await db_session.commit()

        with patch(
            "app.api.outfits.RecommendationService.generate_recommendation",
            new_callable=AsyncMock,
            return_value=outfit,
        ):
            response = await client.post(
                "/api/v1/outfits/suggest",
                json={
                    "occasion": "casual",
                    "weather_override": {
                        "temperature": 20,
                        "condition": "clear",
                    },
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["is_starter_suggestion"] is True

    @pytest.mark.asyncio
    async def test_suggest_without_occasion_falls_back_from_an_unlisted_default(
        self, client, test_user, auth_headers, db_session
    ):
        db_session.add(UserPreference(user_id=test_user.id, default_occasion="banana"))
        outfit = Outfit(
            user_id=test_user.id,
            occasion="casual",
            status=OutfitStatus.pending,
            source=OutfitSource.on_demand,
        )
        outfit.feedback = None
        outfit.family_ratings = []
        outfit.items = []
        db_session.add(outfit)
        await db_session.commit()
        generate = AsyncMock(return_value=outfit)

        with patch("app.api.outfits.RecommendationService.generate_recommendation", generate):
            response = await client.post(
                "/api/v1/outfits/suggest",
                json={"weather_override": {"temperature": 20, "condition": "clear"}},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert generate.await_args.kwargs["occasion"] == "casual"


def _make_item(**kwargs) -> ClothingItem:
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "type": "shirt",
        "image_path": "test.jpg",
        "primary_color": "blue",
        "colors": ["blue"],
        "formality": "casual",
        "season": [],
        "style": [],
        "last_worn_at": None,
    }
    defaults.update(kwargs)
    return ClothingItem(**defaults)


class TestMultiOutfitParse:
    def test_three_outfits(self):
        service = RecommendationService.__new__(RecommendationService)
        content = '{"outfits": [{"items": [1, 2]}, {"items": [3, 4]}, {"items": [5, 6]}]}'
        result = service._parse_multi_outfit_response(content)
        assert len(result) == 3
        assert result[0]["items"] == [1, 2]

    def test_single_fallback(self):
        service = RecommendationService.__new__(RecommendationService)
        content = '{"items": [1, 2], "headline": "Test"}'
        result = service._parse_multi_outfit_response(content)
        assert len(result) == 1
        assert result[0]["items"] == [1, 2]

    def test_array_format(self):
        service = RecommendationService.__new__(RecommendationService)
        content = '[{"items": [1, 2]}, {"items": [3, 4]}]'
        result = service._parse_multi_outfit_response(content)
        assert len(result) >= 1
        assert "items" in result[0]


class TestFormatItemsEnriched:
    def test_recency_annotation(self):
        service = RecommendationService.__new__(RecommendationService)
        item1 = _make_item(last_worn_at=date(2026, 3, 5))
        item2 = _make_item(last_worn_at=None)
        scored = [ScoredItem(item=item1), ScoredItem(item=item2)]
        today = date(2026, 3, 8)

        text, _ = service._format_items_for_prompt(scored, {}, today)
        assert "worn 3 days ago" in text
        assert "never worn" in text

    def test_pair_annotation(self):
        service = RecommendationService.__new__(RecommendationService)
        item1 = _make_item()
        item2 = _make_item()
        scored = [ScoredItem(item=item1), ScoredItem(item=item2)]
        pairs = {item1.id: [item2.id]}
        today = date(2026, 3, 8)

        text, _ = service._format_items_for_prompt(scored, pairs, today)
        assert "pairs well with:" in text


class TestFormatPrefsOccasion:
    def test_occasion_insights(self):
        service = RecommendationService.__new__(RecommendationService)
        learned = {
            "occasion_insights": {
                "work": {"preferred_colors": ["blue", "gray"], "success_rate": 0.3}
            }
        }
        text = service._format_preferences_for_prompt(None, learned, None, None, occasion="work")
        assert "For work, user prefers: blue, gray" in text
        assert "Low success rate" in text


class TestFormatPrefsBody:
    def test_dress_size_included(self):
        service = RecommendationService.__new__(RecommendationService)
        text = service._format_preferences_for_prompt(
            None, body_measurements={"dress_size": "8", "shoe_size": "10"}
        )
        assert "- Body: dress size 8, shoe size 10" in text


class TestPromptPreRanking:
    def test_pre_ranking_hint_present(self):
        from app.services.recommendation_service import RECOMMENDATION_PROMPT

        assert "pre-ranked" in RECOMMENDATION_PROMPT


class TestIncludeItems:
    def test_format_mandatory_items_section(self):
        service = RecommendationService.__new__(RecommendationService)
        id1, id2, id3 = uuid4(), uuid4(), uuid4()
        id_to_number = {1: id1, 2: id2, 3: id3}

        section = service._format_mandatory_items_section([id2], id_to_number)
        assert "[2]" in section
        assert "MANDATORY ITEMS" in section
        assert "MUST appear in all outfit suggestions" in section

    def test_resolve_outfit_items_enforces_mandatory_item_even_if_omitted_by_ai(self):
        shirt, pants = uuid4(), uuid4()
        resolved = resolve_outfit_items(
            {"items": [2], "headline": "Casual day"},
            {1: shirt, 2: pants},
            {shirt: "shirt", pants: "pants"},
            {shirt},
            drop_legwear=False,
        )
        assert set(resolved) == {shirt, pants}

    @pytest.mark.asyncio
    async def test_suggest_accepts_include_items(self, client, test_user, auth_headers, db_session):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
            primary_color="blue",
        )
        outfit = Outfit(
            user_id=test_user.id,
            occasion="casual",
            status=OutfitStatus.pending,
            source=OutfitSource.on_demand,
        )
        outfit.feedback = None
        outfit.family_ratings = []
        outfit.items = [OutfitItem(item=item, position=0, layer_type=None)]

        db_session.add_all([item, outfit])
        await db_session.commit()

        with patch(
            "app.api.outfits.RecommendationService.generate_recommendation",
            new_callable=AsyncMock,
            return_value=outfit,
        ) as mock_generate:
            mand_id = uuid4()
            response = await client.post(
                "/api/v1/outfits/suggest",
                json={
                    "occasion": "casual",
                    "include_items": [str(mand_id)],
                    "weather_override": {
                        "temperature": 20,
                        "condition": "clear",
                    },
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert mock_generate.call_args.kwargs["include_items"] == [mand_id]

    @pytest.mark.asyncio
    async def test_unresolved_include_item_raises_value_error(self, db_session, test_user):
        service = RecommendationService(db_session)
        weather_override = WeatherData(
            temperature=20,
            feels_like=20,
            humidity=50,
            precipitation_chance=0,
            precipitation_mm=0,
            wind_speed=0,
            condition="clear",
            condition_code=0,
            is_day=True,
            uv_index=0,
            timestamp=datetime.utcnow(),
        )
        fake_id = uuid4()
        test_user.preferences = None
        with pytest.raises(ValueError, match="could not be found"):
            await service.generate_recommendation(
                user=test_user,
                occasion="casual",
                weather_override=weather_override,
                include_items=[fake_id],
            )

    @pytest.mark.asyncio
    async def test_suggest_options_endpoint_returns_multiple(self, client, auth_headers):
        with patch.object(
            RecommendationService,
            "generate_recommendations",
            AsyncMock(),
        ) as mock_generate:
            fake_outfits = []
            for _ in range(3):
                o = MagicMock()
                o.id = uuid4()
                o.occasion = "casual"
                o.scheduled_for = None
                o.status = MagicMock(value="pending")
                o.name = None
                o.replaces_outfit_id = None
                o.cloned_from_outfit_id = None
                o.source = MagicMock(value="on_demand")
                o.reasoning = "Test"
                o.style_notes = "Test"
                o.season = None
                o.formality = None
                o.palette = None
                o.notes = None
                o.weather_data = None
                o.items = []
                o.feedback = []
                o.family_ratings = []
                o.created_at = datetime.utcnow()
                fake_outfits.append(o)
            mock_generate.return_value = fake_outfits

            response = await client.post(
                "/api/v1/outfits/suggest-options",
                json={"occasion": "casual"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 3
            assert mock_generate.call_args.kwargs["count"] == 3


class TestHotDayLegwear:
    def _resolve(self, kinds, picked, drop_legwear, mandatory=()):
        ids = [uuid4() for _ in kinds]
        resolved = resolve_outfit_items(
            {"items": picked},
            dict(enumerate(ids, start=1)),
            dict(zip(ids, kinds, strict=True)),
            {ids[n - 1] for n in mandatory} or None,
            drop_legwear=drop_legwear,
        )
        return ids, set(resolved)

    @pytest.mark.parametrize(
        ("drop_legwear", "mandatory", "tights_kept"),
        [(True, (), False), (False, (), True), (True, (3,), True)],
        ids=["hot", "not-hot", "hot-but-requested"],
    )
    def test_drops_only_unrequested_tights_on_a_hot_day(self, drop_legwear, mandatory, tights_kept):
        ids, kept = self._resolve(
            ("t-shirt", "skirt", "tights", "sneakers"), [1, 2, 3, 4], drop_legwear, mandatory
        )
        assert (ids[2] in kept) is tights_kept
        assert {ids[0], ids[1], ids[3]} <= kept

    def test_an_answer_of_only_tights_resolves_to_nothing(self):
        assert self._resolve(("tights",), [1], True)[1] == set()

    def test_unknown_and_non_numeric_picks_are_ignored(self):
        ids, kept = self._resolve(("shirt", "jeans"), [1, "two", 9, 1], False)
        assert kept == {ids[0]}

    async def _hot_day_outfits(
        self,
        db_session,
        user,
        ai_outfits,
        cached=None,
        count=1,
        cached_weather=None,
        unavailable=None,
        include=(),
        extras=(),
        single_outfit=False,
        kinds=("tights", "skirt", "t-shirt", "sneakers"),
    ):
        # Extras come first among the candidates and are numbered last, so that neither
        # candidate order nor prompt order can stand in for the fill ranking.
        extra_items = [
            ClothingItem(
                user_id=user.id,
                type=kind,
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
                primary_color="black",
            )
            for kind in extras
        ]
        db_session.add_all(extra_items)
        await db_session.commit()
        items = [
            ClothingItem(
                user_id=user.id,
                type=kind,
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
                primary_color="black",
            )
            for kind in kinds
        ]
        if unavailable == "archived":
            items[3].is_archived = True
        elif unavailable == "needs_wash":
            items[3].needs_wash = True
        db_session.add_all(items)
        await db_session.commit()
        items += extra_items
        number_map = {n: item.id for n, item in enumerate(items, start=1)}
        user.preferences = None
        options = [{"items": o, "headline": f"AI {n}"} for n, o in enumerate(ai_outfits, start=1)]
        ai = MagicMock()
        ai.generate_text = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(options[0] if single_outfit else {"outfits": options}),
                model="m",
                endpoint="e",
            )
        )
        self.ai = ai
        weather = _weather(temp=35)
        if cached is not None:
            cached = {
                "headline": "Cached",
                **cached,
                "_number_map": {str(k): str(v) for k, v in number_map.items()},
                "_context": suggestion_context(
                    cached_weather or weather, TimeOfDay.afternoon, None, user.body_measurements
                ),
            }
            cached = json.loads(json.dumps(cached))
        rejected = {items[3].id} if unavailable == "rejected" else set()
        service = RecommendationService(db_session)
        unpatched = service.get_candidate_items
        extra_ids = {item.id for item in extra_items}

        async def extras_first(**kwargs):
            return sorted(await unpatched(**kwargs), key=lambda item: item.id not in extra_ids)

        with (
            patch("app.services.recommendation_service.AIService", return_value=ai),
            patch(
                "app.services.recommendation_service.pop_suggestion",
                AsyncMock(side_effect=[cached, None]),
            ) as pop,
            patch("app.services.recommendation_service.push_suggestions", AsyncMock()) as push,
            patch.object(service, "_format_items_for_prompt", return_value=("", number_map)),
            patch.object(service, "_get_today_rejected_item_ids", AsyncMock(return_value=rejected)),
            patch.object(service, "get_candidate_items", extras_first),
        ):
            outfits = await service.generate_recommendations(
                user=user,
                occasion="casual",
                weather_override=weather,
                include_items=[items[n - 1].id for n in include],
                time_of_day=TimeOfDay.afternoon,
                count=count,
                single_outfit=single_outfit,
            )
        self.reasonings = [o.reasoning for o in outfits]
        self.pop = pop
        self.raw_responses = [o.ai_raw_response for o in outfits]
        self.pushed_contexts = (
            [od["_context"] for od in push.call_args.args[2]] if push.call_args else []
        )
        self.pushed = [od["items"] for od in push.call_args.args[2]] if push.call_args else []
        return items, [{oi.item_id for oi in o.items} for o in outfits]

    @pytest.mark.asyncio
    async def test_a_tights_only_option_is_skipped_not_fatal(self, db_session, test_user):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[3, 2, 4], [1], [2, 3, 4], [3, 2, 4]], count=2
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}] * 2
        assert self.reasonings == ["AI 1", "AI 3"]
        assert self.pushed == [[3, 2, 4]]

    @pytest.mark.asyncio
    async def test_a_tights_only_cached_suggestion_falls_through_to_a_fresh_one(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[3, 2, 4]], cached={"items": [1]}
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.reasonings == ["AI 1"]

    @pytest.mark.asyncio
    async def test_a_cached_suggestion_for_the_same_weather_is_served(self, db_session, test_user):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[3, 2, 4]], cached={"items": [2, 3, 4]}
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.reasonings == ["Cached"]
        self.ai.generate_text.assert_not_called()
        assert not {"_context", "_number_map"} & set(self.raw_responses[0])

    @pytest.mark.asyncio
    async def test_a_cached_suggestion_from_a_cold_day_is_not_served_on_a_hot_day(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session,
            test_user,
            [[3, 2, 4]],
            cached={"items": [2, 3, 4]},
            cached_weather=_weather(temp=2),
        )
        assert self.reasonings == ["AI 1"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("unavailable", ["archived", "needs_wash", "rejected"])
    async def test_a_cached_suggestion_with_an_unavailable_item_is_not_served(
        self, db_session, test_user, unavailable
    ):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[3, 2]], cached={"items": [2, 3, 4]}, unavailable=unavailable
        )
        assert outfits == [{items[1].id, items[2].id}]
        assert self.reasonings == ["AI 1"]
        assert self.pop.await_count == 2

    @pytest.mark.asyncio
    async def test_a_cached_suggestion_with_a_requested_item_is_served_even_if_it_needs_a_wash(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session,
            test_user,
            [[3, 2]],
            cached={"items": [2, 3, 4]},
            unavailable="needs_wash",
            include=(4,),
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.reasonings == ["Cached"]
        self.ai.generate_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_cached_options_record_the_weather_they_were_made_for(
        self, db_session, test_user
    ):
        await self._hot_day_outfits(db_session, test_user, [[3, 2, 4], [2, 3, 4]])
        assert self.pushed_contexts == [
            suggestion_context(
                _weather(temp=35), TimeOfDay.afternoon, None, test_user.body_measurements
            )
        ]

    @pytest.mark.asyncio
    async def test_a_tights_only_first_option_falls_through_to_the_next(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[1], [3, 2, 4], [2, 3, 4]]
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.reasonings == ["AI 2"]
        assert self.pushed == [[2, 3, 4]]

    @pytest.mark.asyncio
    async def test_an_option_without_shoes_is_skipped_for_a_complete_one(
        self, db_session, test_user
    ):
        await self._hot_day_outfits(db_session, test_user, [[3, 2], [3, 2, 4]])
        assert self.reasonings == ["AI 2"]
        assert "_filled_item_ids" not in self.raw_responses[0]

    @pytest.mark.asyncio
    async def test_incomplete_leftovers_are_not_cached(self, db_session, test_user):
        await self._hot_day_outfits(db_session, test_user, [[3, 2, 4], [3, 2], [2, 3, 4]])
        assert self.pushed == [[2, 3, 4]]

    @pytest.mark.asyncio
    async def test_when_no_option_is_complete_the_least_changed_one_is_filled_with_the_best_fit(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[3], [2, 4]], extras=("sweater",)
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.reasonings == ["AI 2"]
        assert self.raw_responses[0]["_filled_item_ids"] == [str(items[2].id)]

    @pytest.mark.asyncio
    async def test_a_single_outfit_missing_a_top_is_filled_with_the_best_fit(
        self, db_session, test_user
    ):
        items, outfits = await self._hot_day_outfits(
            db_session, test_user, [[2, 4]], extras=("sweater",), single_outfit=True
        )
        assert outfits == [{items[1].id, items[2].id, items[3].id}]
        assert self.raw_responses[0]["_filled_item_ids"] == [str(items[2].id)]

    # The only piece for the top is a dress, which cannot go over the skirt the AI chose.
    @pytest.mark.asyncio
    @pytest.mark.parametrize("single_outfit", [True, False], ids=["single", "options"])
    async def test_an_outfit_the_wardrobe_cannot_complete_is_not_saved(
        self, db_session, test_user, single_outfit
    ):
        with pytest.raises(AIRecommendationError, match="cannot be completed"):
            await self._hot_day_outfits(
                db_session,
                test_user,
                [[2, 4]],
                single_outfit=single_outfit,
                kinds=("tights", "skirt", "dress", "sneakers"),
            )
        saved = await db_session.scalar(
            select(func.count()).select_from(Outfit).where(Outfit.user_id == test_user.id)
        )
        assert saved == 0

    @pytest.mark.asyncio
    async def test_a_requested_item_the_wardrobe_cannot_complete_is_refused_before_the_ai(
        self, db_session, test_user
    ):
        with pytest.raises(ValueError, match="selected items cannot make a complete outfit"):
            await self._hot_day_outfits(
                db_session,
                test_user,
                [[2, 4]],
                include=(2,),
                kinds=("tights", "skirt", "dress", "sneakers"),
            )
        self.ai.generate_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_single_outfit_with_nothing_valid_is_not_built_from_scratch(
        self, db_session, test_user
    ):
        with pytest.raises(AIRecommendationError, match="did not select"):
            await self._hot_day_outfits(db_session, test_user, [[99]], single_outfit=True)

    @pytest.mark.asyncio
    async def test_options_with_nothing_valid_are_not_built_from_scratch(
        self, db_session, test_user
    ):
        with pytest.raises(AIRecommendationError, match="did not select"):
            await self._hot_day_outfits(db_session, test_user, [[99], [1]])

    @pytest.mark.asyncio
    async def test_an_accessory_only_single_outfit_is_not_built_from_scratch(
        self, db_session, test_user
    ):
        with pytest.raises(AIRecommendationError, match="did not select"):
            await self._hot_day_outfits(
                db_session, test_user, [[5]], extras=("bag",), single_outfit=True
            )

    @pytest.mark.asyncio
    async def test_the_fallback_fills_the_option_needing_the_fewest_additions(
        self, db_session, test_user
    ):
        await self._hot_day_outfits(db_session, test_user, [[5], [4], [3, 4]], extras=("bag",))
        assert self.reasonings == ["AI 3"]

    @pytest.mark.asyncio
    async def test_fewer_complete_options_than_asked_for_are_returned_as_they_are(
        self, db_session, test_user
    ):
        await self._hot_day_outfits(db_session, test_user, [[3, 2], [3, 2, 4], [2, 4]], count=3)
        assert self.reasonings == ["AI 2"]

    @pytest.mark.asyncio
    async def test_a_requested_item_counts_toward_completeness(self, db_session, test_user):
        await self._hot_day_outfits(db_session, test_user, [[3, 4], [3, 2, 4]], include=(2,))
        assert self.reasonings == ["AI 1"]

    @pytest.mark.asyncio
    async def test_an_incomplete_cached_suggestion_falls_through_to_a_fresh_one(
        self, db_session, test_user
    ):
        await self._hot_day_outfits(db_session, test_user, [[3, 2, 4]], cached={"items": [2, 4]})
        assert self.reasonings == ["AI 1"]
        self.ai.generate_text.assert_awaited_once()
