"""Editing an item's tags by hand: validation, no-op nulls and edit tracking."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.utils.garment_vocabulary import FITS, FORMALITY, MATERIALS, PATTERNS, SEASONS, STYLES
from app.utils.tag_validation import normalize_tag_edits

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


async def _make_item(db_session: AsyncSession, test_user, **kwargs) -> ClothingItem:
    item = ClothingItem(
        user_id=test_user.id,
        type=kwargs.pop("type", "shirt"),
        image_path="test/image.jpg",
        status=ItemStatus.ready,
        tags=kwargs.pop("tags", {}),
        **kwargs,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _reload(db_session: AsyncSession, item_id) -> ClothingItem:
    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


async def _patch(client: AsyncClient, auth_headers, item_id, body: dict):
    return await client.patch(f"/api/v1/items/{item_id}", json=body, headers=auth_headers)


# --------------------------------------------------------------------------
# normalize_tag_edits
# --------------------------------------------------------------------------


class TestNormalizeTagEdits:
    def test_strips_and_lowercases_single_values(self):
        cleaned = normalize_tag_edits({"pattern": " Striped ", "fit": "SLIM"})
        assert cleaned == {"pattern": "striped", "fit": "slim"}

    def test_cleans_lists_and_drops_repeats(self):
        cleaned = normalize_tag_edits(
            {"style": ["Casual", "casual", " Sporty"], "season": ["Fall"]}
        )
        assert cleaned == {"style": ["casual", "sporty"], "season": ["fall"]}

    def test_null_passes_through_because_it_clears_a_tag(self):
        assert normalize_tag_edits({"pattern": None, "style": None}) == {
            "pattern": None,
            "style": None,
        }

    def test_keys_not_sent_are_not_checked_or_added(self):
        assert normalize_tag_edits({"pattern": "solid"}) == {"pattern": "solid"}

    def test_colours_and_free_text_keys_are_left_alone(self):
        edits = {"colors": ["Sea Foam"], "primary_color": "Sea Foam", "size": "M"}
        assert normalize_tag_edits(edits) == edits

    def test_material_is_a_closed_list(self):
        assert normalize_tag_edits({"material": " Linen "}) == {"material": "linen"}
        with pytest.raises(ValueError, match="material '100% Linen'"):
            normalize_tag_edits({"material": "100% Linen"})

    def test_an_off_list_value_the_item_has_is_kept_exactly_as_stored(self):
        cleaned = normalize_tag_edits({"material": "100% linen "}, {"material": "100% Linen"})
        assert cleaned == {"material": "100% Linen"}

    def test_none_is_not_a_pattern_on_an_item_without_one(self):
        with pytest.raises(ValueError, match="pattern 'none'"):
            normalize_tag_edits({"pattern": "none"}, {})

    def test_rejects_every_unknown_value(self):
        with pytest.raises(ValueError) as error:
            normalize_tag_edits({"pattern": "swirly", "style": ["casual", "goth"], "fit": "tight"})
        message = str(error.value)
        assert "pattern 'swirly'" in message
        assert "style 'goth'" in message
        assert "fit 'tight'" in message

    def test_does_not_modify_the_input(self):
        edits = {"pattern": " Striped "}
        normalize_tag_edits(edits)
        assert edits == {"pattern": " Striped "}

    @pytest.mark.parametrize(
        ("key", "values"),
        [
            ("pattern", PATTERNS),
            ("material", MATERIALS),
            ("formality", FORMALITY),
            ("fit", FITS),
            ("style", STYLES),
            ("season", SEASONS),
        ],
    )
    def test_every_vocabulary_value_is_accepted(self, key, values):
        for value in values:
            edit = {key: [value] if key in ("style", "season") else value}
            assert normalize_tag_edits(edit) == edit


# --------------------------------------------------------------------------
# PATCH /items/{id}
# --------------------------------------------------------------------------


class TestPatchTags:
    @pytest.mark.asyncio
    async def test_null_tags_leave_every_tag_alone(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # The item dialog sends tags: null when only the name or notes were edited.
        stored = {
            "pattern": "solid",
            "size": "M",
            "logprobs_confidence": 0.66,
            "user_edited_keys": ["fit"],
        }
        item = await _make_item(db_session, test_user, tags=dict(stored), pattern="solid")

        response = await _patch(client, auth_headers, item.id, {"name": "renamed", "tags": None})

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert refreshed.name == "renamed"
        assert refreshed.tags == stored
        assert refreshed.pattern == "solid"

    @pytest.mark.asyncio
    async def test_empty_tags_leave_every_tag_alone(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid", "size": "M"})

        response = await _patch(client, auth_headers, item.id, {"tags": {}})

        assert response.status_code == 200
        assert (await _reload(db_session, item.id)).tags == {"pattern": "solid", "size": "M"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tags",
        [
            {"pattern": "swirly"},
            {"pattern": "none"},
            {"style": ["goth"]},
            {"material": "unobtainium"},
            {"material": "x" * 60},
        ],
        ids=["pattern", "pattern-none", "style", "material", "long-material"],
    )
    async def test_unknown_value_is_rejected_with_a_code_and_nothing_changes(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, tags
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid"}, pattern="solid")

        response = await _patch(client, auth_headers, item.id, {"tags": tags})

        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "INVALID_TAG_VALUE"
        refreshed = await _reload(db_session, item.id)
        assert refreshed.tags == {"pattern": "solid"}
        assert refreshed.pattern == "solid"

    @pytest.mark.asyncio
    async def test_an_old_off_list_value_does_not_block_other_edits(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # Rows tagged before the vocabulary settled can hold values it no longer lists.
        item = await _make_item(
            db_session,
            test_user,
            tags={"pattern": "paisley", "material": "100% Linen", "fit": "regular"},
            pattern="paisley",
            material="100% Linen",
        )

        response = await _patch(client, auth_headers, item.id, {"tags": {"fit": "slim"}})

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert refreshed.tags["pattern"] == "paisley"
        assert refreshed.pattern == "paisley"
        assert refreshed.tags["material"] == "100% Linen"
        assert refreshed.tags["fit"] == "slim"

    @pytest.mark.asyncio
    async def test_an_old_off_list_value_sent_back_unchanged_is_left_as_it_was(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            tags={"pattern": "paisley", "material": "100% Linen"},
            pattern="paisley",
            material="100% Linen",
        )

        response = await _patch(
            client,
            auth_headers,
            item.id,
            {"tags": {"pattern": "paisley", "material": "100% linen"}},
        )

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert refreshed.tags == {"pattern": "paisley", "material": "100% Linen"}
        assert refreshed.material == "100% Linen"

    @pytest.mark.asyncio
    async def test_stored_values_are_cleaned_in_json_and_column(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid"}, pattern="solid")

        response = await _patch(
            client, auth_headers, item.id, {"tags": {"pattern": " Striped ", "style": ["Casual"]}}
        )

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert refreshed.tags["pattern"] == "striped"
        assert refreshed.pattern == "striped"
        assert refreshed.tags["style"] == ["casual"]
        assert refreshed.style == ["casual"]

    @pytest.mark.asyncio
    async def test_null_inside_tags_clears_that_one_tag_and_its_column(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            tags={"pattern": "striped", "fit": "slim"},
            pattern="striped",
        )

        response = await _patch(client, auth_headers, item.id, {"tags": {"pattern": None}})

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert "pattern" not in refreshed.tags
        assert refreshed.pattern is None
        assert refreshed.tags["fit"] == "slim"

    @pytest.mark.asyncio
    async def test_secondary_colour_and_primary_stay_in_step(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            tags={"colors": ["white"], "primary_color": "white"},
            colors=["white"],
            primary_color="white",
        )

        response = await _patch(
            client,
            auth_headers,
            item.id,
            {"tags": {"colors": ["navy", "white"], "primary_color": "navy"}},
        )

        assert response.status_code == 200
        refreshed = await _reload(db_session, item.id)
        assert refreshed.colors == ["navy", "white"]
        assert refreshed.primary_color == "navy"
        assert refreshed.tags["colors"] == ["navy", "white"]


class TestUserEditedKeys:
    @pytest.mark.asyncio
    async def test_records_only_tags_that_actually_changed(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid"}, pattern="solid")

        await _patch(client, auth_headers, item.id, {"tags": {"pattern": "solid", "fit": "slim"}})

        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["fit"]

    @pytest.mark.asyncio
    async def test_accumulates_without_repeats(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid"}, pattern="solid")

        await _patch(client, auth_headers, item.id, {"tags": {"fit": "slim"}})
        await _patch(
            client, auth_headers, item.id, {"tags": {"fit": "relaxed", "style": ["casual"]}}
        )

        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["fit", "style"]

    @pytest.mark.asyncio
    async def test_clearing_a_tag_counts_as_an_edit(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, tags={"pattern": "striped"}, pattern="striped"
        )

        await _patch(client, auth_headers, item.id, {"tags": {"pattern": None}})

        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_changing_the_primary_colour_outside_tags_is_recorded(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, tags={"primary_color": "white"}, primary_color="white"
        )

        await _patch(client, auth_headers, item.id, {"primary_color": "navy"})

        # The server reorders the colour list for the new primary; the person did not edit it.
        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["primary_color"]

    @pytest.mark.asyncio
    async def test_changing_type_or_subtype_is_recorded(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, type="shirt", tags={"pattern": "solid"})

        await _patch(client, auth_headers, item.id, {"type": "t-shirt", "subtype": "crew"})

        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["type", "subtype"]

    @pytest.mark.asyncio
    async def test_setting_the_type_back_to_unknown_hands_it_to_the_ai(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, type="shirt", tags={"user_edited_keys": ["type", "pattern"]}
        )

        response = await _patch(client, auth_headers, item.id, {"type": "unknown"})

        assert response.status_code == 200
        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_unlocking_the_only_locked_key_leaves_no_list(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, type="shirt", tags={"user_edited_keys": ["type"]}
        )

        await _patch(client, auth_headers, item.id, {"type": "unknown"})

        assert "user_edited_keys" not in (await _reload(db_session, item.id)).tags

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [{"primary_color": "unknown"}, {"tags": {"primary_color": "unknown"}}],
        ids=["top-level", "in-tags"],
    )
    async def test_an_unknown_primary_colour_hands_it_to_the_ai(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, body
    ):
        item = await _make_item(
            db_session,
            test_user,
            primary_color="white",
            colors=["white", "black"],
            tags={
                "primary_color": "white",
                "colors": ["white", "black"],
                "user_edited_keys": ["primary_color", "pattern"],
            },
        )

        response = await _patch(client, auth_headers, item.id, body)

        assert response.status_code == 200
        done = await _reload(db_session, item.id)
        assert done.tags["user_edited_keys"] == ["pattern"]
        assert done.colors == ["white", "black"]

    @pytest.mark.asyncio
    async def test_a_subtype_cleared_with_a_type_change_is_handed_back(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # The form drops a subtype that belonged to the old type; the AI may suggest a new one.
        item = await _make_item(
            db_session,
            test_user,
            type="t-shirt",
            subtype="button-down",
            tags={"user_edited_keys": ["subtype"]},
        )

        await _patch(client, auth_headers, item.id, {"type": "polo", "subtype": None})

        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["type"]

    @pytest.mark.asyncio
    async def test_resending_unchanged_form_fields_records_nothing(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # The edit form sends type and subtype on every save, whatever was touched.
        item = await _make_item(
            db_session, test_user, type="shirt", subtype="oxford", tags={"pattern": "solid"}
        )

        response = await _patch(
            client,
            auth_headers,
            item.id,
            {"type": "shirt", "subtype": "oxford", "name": "My oxford", "tags": None},
        )

        assert response.status_code == 200
        assert "user_edited_keys" not in (await _reload(db_session, item.id)).tags

    @pytest.mark.asyncio
    async def test_user_owned_keys_are_not_ai_overrides(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"pattern": "solid"})

        await _patch(
            client,
            auth_headers,
            item.id,
            {"tags": {"size": "M", "care_instructions": "Wash cold"}},
        )

        refreshed = await _reload(db_session, item.id)
        assert refreshed.tags["size"] == "M"
        assert "user_edited_keys" not in refreshed.tags

    @pytest.mark.asyncio
    async def test_a_client_cannot_set_or_clear_the_list(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, tags={"pattern": "solid", "user_edited_keys": ["fit"]}
        )

        await _patch(
            client, auth_headers, item.id, {"tags": {"user_edited_keys": ["pattern", "x"]}}
        )
        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["fit"]

        await _patch(client, auth_headers, item.id, {"tags": {"user_edited_keys": []}})
        assert (await _reload(db_session, item.id)).tags["user_edited_keys"] == ["fit"]


class TestColoursStayInStep:
    """A colour change sent outside `tags` reaches the tags JSON and the colour list (#294)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [{"primary_color": "navy"}, {"tags": {"primary_color": "navy"}}],
        ids=["top-level", "in-tags"],
    )
    async def test_a_new_primary_replaces_the_old_one_at_the_front_of_the_list(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, body
    ):
        item = await _make_item(
            db_session,
            test_user,
            primary_color="white",
            colors=["white", "black"],
            tags={"primary_color": "white", "colors": ["white", "black"]},
        )

        response = await _patch(client, auth_headers, item.id, body)

        assert response.status_code == 200
        done = await _reload(db_session, item.id)
        assert done.primary_color == "navy"
        assert done.colors == ["navy", "black"]
        assert done.tags["primary_color"] == "navy"
        assert done.tags["colors"] == ["navy", "black"]

    @pytest.mark.asyncio
    async def test_a_new_primary_replaces_the_first_colour_when_no_primary_is_recorded(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, colors=["red", "blue"], tags={"colors": ["red", "blue"]}
        )

        await _patch(client, auth_headers, item.id, {"primary_color": "green"})

        done = await _reload(db_session, item.id)
        assert done.colors == ["green", "blue"]
        assert done.tags["colors"] == ["green", "blue"]

    @pytest.mark.asyncio
    async def test_unknown_as_the_primary_leaves_the_colour_list_alone(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            primary_color="white",
            colors=["white", "black"],
            tags={"primary_color": "white", "colors": ["white", "black"]},
        )

        await _patch(client, auth_headers, item.id, {"primary_color": "unknown"})

        done = await _reload(db_session, item.id)
        assert done.colors == ["white", "black"]
        assert done.tags["colors"] == ["white", "black"]

    @pytest.mark.asyncio
    async def test_a_colour_list_sent_at_the_top_level_reaches_the_tags(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, colors=["white"], tags={"colors": ["white"]})

        await _patch(client, auth_headers, item.id, {"colors": ["white", "red"]})

        done = await _reload(db_session, item.id)
        assert done.colors == ["white", "red"]
        assert done.tags["colors"] == ["white", "red"]

    @pytest.mark.asyncio
    async def test_resending_the_same_primary_changes_nothing(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            primary_color="white",
            colors=["white", "black"],
            tags={"primary_color": "white", "colors": ["white", "black"]},
        )

        await _patch(client, auth_headers, item.id, {"primary_color": "white"})

        done = await _reload(db_session, item.id)
        assert done.colors == ["white", "black"]
        assert "user_edited_keys" not in done.tags

    @pytest.mark.asyncio
    async def test_an_explicit_list_with_the_new_primary_is_kept_as_sent(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session, test_user, primary_color="white", colors=["white", "black"]
        )

        await _patch(
            client,
            auth_headers,
            item.id,
            {"primary_color": "navy", "tags": {"colors": ["navy", "white"]}},
        )

        done = await _reload(db_session, item.id)
        assert done.colors == ["navy", "white"]
        assert done.tags["colors"] == ["navy", "white"]


class TestOffListStyleAlreadyOnTheItem:
    @pytest.mark.asyncio
    async def test_an_old_off_list_style_left_switched_on_does_not_block_a_save(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"style": ["grunge", "casual"]})

        response = await _patch(
            client, auth_headers, item.id, {"tags": {"style": ["grunge", "sporty"]}}
        )

        assert response.status_code == 200
        assert (await _reload(db_session, item.id)).tags["style"] == ["grunge", "sporty"]

    @pytest.mark.asyncio
    async def test_a_new_off_list_style_is_still_rejected(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, tags={"style": ["casual"]})

        response = await _patch(client, auth_headers, item.id, {"tags": {"style": ["goth"]}})

        assert response.status_code == 422
        assert "goth" in response.text
        assert (await _reload(db_session, item.id)).tags["style"] == ["casual"]

    def test_the_check_accepts_values_the_item_already_has(self):
        cleaned = normalize_tag_edits({"season": ["Monsoon", "summer"]}, {"season": ["monsoon"]})
        assert cleaned == {"season": ["monsoon", "summer"]}
