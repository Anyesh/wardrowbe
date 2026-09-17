import pytest
from httpx import AsyncClient


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
