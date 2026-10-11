from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_acceptance_trend_sends_iso_period_starts_alongside_the_old_label(
    client: AsyncClient, test_user, auth_headers
):
    response = await client.get("/api/v1/analytics?days=21", headers=auth_headers)

    assert response.status_code == 200
    trend = response.json()["acceptance_trend"]
    assert len(trend) == 3
    starts = [date.fromisoformat(week["period_start"]) for week in trend]
    assert starts[-1] == (datetime.utcnow() - timedelta(days=7)).date()
    assert [b - a for a, b in zip(starts, starts[1:], strict=False)] == [timedelta(days=7)] * 2
    assert [week["period"] for week in trend] == [s.strftime("%b %d") for s in starts]
