import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.users import (
    BodyMeasurementWriteRequest,
    UserProfileUpdate,
    record_body_measurements,
    update_profile,
)
from app.main import app
from app.models import User


@pytest.mark.asyncio
async def test_explicit_remeasurement_records_same_value_again(client: AsyncClient, auth_headers):
    initial = await client.patch(
        "/api/v1/users/me",
        json={"body_measurements": {"waist": 104}},
        headers=auth_headers,
    )
    assert initial.status_code == 200

    response = await client.post(
        "/api/v1/users/me/body-measurements",
        json={"measurements": {"waist": 104}},
        headers=auth_headers,
    )
    assert response.status_code == 200

    history = await client.get("/api/v1/users/me/body-measurements/history", headers=auth_headers)
    waist = [row for row in history.json()["observations"] if row["metric"] == "waist"]
    assert [row["value"] for row in waist] == [104.0, 104.0]
    assert all(row["measured_at"] is not None for row in waist)


@pytest.mark.asyncio
async def test_explicit_remeasurement_updates_only_submitted_metrics(
    client: AsyncClient, auth_headers
):
    initial = await client.patch(
        "/api/v1/users/me",
        json={"body_measurements": {"waist": 104, "hips": 100}},
        headers=auth_headers,
    )
    assert initial.status_code == 200

    before = await client.get("/api/v1/users/me/body-measurements", headers=auth_headers)
    hips_measured_at = before.json()["measurements"]["hips"]["measured_at"]

    response = await client.post(
        "/api/v1/users/me/body-measurements",
        json={"measurements": {"waist": 101}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    current = response.json()["measurements"]
    assert current["waist"]["value"] == 101.0
    assert current["hips"]["value"] == 100.0
    assert current["hips"]["measured_at"] == hips_measured_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "measurements",
    [
        {"pants_waist": 90},
        {"waist": 0},
        {"waist": -1},
    ],
)
async def test_explicit_remeasurement_rejects_invalid_metrics_or_values(
    client: AsyncClient, auth_headers, measurements
):
    response = await client.post(
        "/api/v1/users/me/body-measurements",
        json={"measurements": measurements},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_partial_profile_measurement_patch_preserves_other_values(
    client: AsyncClient, test_user, auth_headers, db_session
):
    test_user.body_measurements = {
        "weight": 84,
        "waist": 104,
        "shirt_size": "M",
    }
    await db_session.commit()

    response = await client.patch(
        "/api/v1/users/me",
        json={"body_measurements": {"shirt_size": "L"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["body_measurements"] == {
        "weight": 84,
        "waist": 104,
        "shirt_size": "L",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
async def test_explicit_remeasurement_rejects_non_finite_values(
    client: AsyncClient, auth_headers, literal
):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        response = await raw_client.post(
            "/api/v1/users/me/body-measurements",
            content=f'{{"measurements":{{"waist":{literal}}}}}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
async def test_profile_patch_rejects_non_finite_measurements(
    client: AsyncClient, auth_headers, literal
):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        response = await raw_client.patch(
            "/api/v1/users/me",
            content=f'{{"body_measurements":{{"waist":{literal}}}}}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", ["0.00001", "100000000"])
async def test_explicit_remeasurement_rejects_values_outside_storage_precision(
    client: AsyncClient, auth_headers, literal
):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        response = await raw_client.post(
            "/api/v1/users/me/body-measurements",
            content=f'{{"measurements":{{"waist":{literal}}}}}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", ["0.00001", "100000000"])
async def test_profile_patch_rejects_values_outside_storage_precision(
    client: AsyncClient, auth_headers, literal
):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        response = await raw_client.patch(
            "/api/v1/users/me",
            content=f'{{"body_measurements":{{"waist":{literal}}}}}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_explicit_remeasurement_uses_storage_precision_for_snapshot_and_history(
    client: AsyncClient, auth_headers
):
    response = await client.post(
        "/api/v1/users/me/body-measurements",
        json={"measurements": {"waist": 99.12345}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["measurements"]["waist"]["value"] == 99.1235
    assert response.json()["measurements"]["waist"]["source"] == "manual"

    profile = await client.get("/api/v1/users/me", headers=auth_headers)
    assert profile.json()["body_measurements"]["waist"] == 99.1235

    history = await client.get("/api/v1/users/me/body-measurements/history", headers=auth_headers)
    waist = [row for row in history.json()["observations"] if row["metric"] == "waist"]
    assert waist[0]["value"] == 99.1235


@pytest.mark.asyncio
async def test_concurrent_partial_profile_measurement_patches_preserve_both_metrics(
    async_engine, db_session, test_user
):
    test_user.body_measurements = {"waist": 100, "hips": 100}
    await db_session.commit()

    maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with maker() as first_session, maker() as second_session:
        first_user = await first_session.get(User, test_user.id)
        second_user = await second_session.get(User, test_user.id)
        assert first_user is not None
        assert second_user is not None

        await asyncio.gather(
            update_profile(
                UserProfileUpdate(body_measurements={"waist": 90}),
                first_session,
                first_user,
            ),
            update_profile(
                UserProfileUpdate(body_measurements={"hips": 95}),
                second_session,
                second_user,
            ),
        )

    async with maker() as verify_session:
        saved_user = await verify_session.get(User, test_user.id)
        assert saved_user is not None
        assert saved_user.body_measurements["waist"] == 90
        assert saved_user.body_measurements["hips"] == 95


@pytest.mark.asyncio
async def test_concurrent_explicit_remeasurements_preserve_both_metrics(
    async_engine, db_session, test_user
):
    test_user.body_measurements = {"waist": 100, "hips": 100}
    await db_session.commit()

    maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with maker() as first_session, maker() as second_session:
        first_user = await first_session.get(User, test_user.id)
        second_user = await second_session.get(User, test_user.id)
        assert first_user is not None
        assert second_user is not None

        await asyncio.gather(
            record_body_measurements(
                BodyMeasurementWriteRequest(measurements={"waist": 90}),
                first_session,
                first_user,
            ),
            record_body_measurements(
                BodyMeasurementWriteRequest(measurements={"hips": 95}),
                second_session,
                second_user,
            ),
        )

    async with maker() as verify_session:
        saved_user = await verify_session.get(User, test_user.id)
        assert saved_user is not None
        assert saved_user.body_measurements["waist"] == 90
        assert saved_user.body_measurements["hips"] == 95
