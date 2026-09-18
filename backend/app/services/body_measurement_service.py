"""Body measurement history and current-state projection."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_measurement import BodyMeasurementObservation
from app.models.user import User

MEASUREMENT_UNITS: dict[str, str] = {
    "weight": "kg",
    "chest": "cm",
    "waist": "cm",
    "hips": "cm",
    "inseam": "cm",
    "height": "cm",
}


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not result.is_finite():
        return None
    return result if result > 0 else None


async def lock_user_for_measurement_update(db: AsyncSession, user: User) -> User:
    result = await db.execute(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


class BodyMeasurementService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_measurements(
        self,
        user: User,
        measurements: dict,
        *,
        source: str = "manual",
        measured_at: datetime | None = None,
    ) -> None:
        user = await lock_user_for_measurement_update(self.db, user)
        observed_at = measured_at or datetime.now(UTC)
        snapshot = dict(user.body_measurements or {})

        for metric, raw_value in measurements.items():
            unit = MEASUREMENT_UNITS.get(metric)
            value = _number(raw_value)
            if unit is None or value is None:
                raise ValueError(f"invalid body measurement: {metric}")
            self.db.add(
                BodyMeasurementObservation(
                    user_id=user.id,
                    metric=metric,
                    value=value,
                    unit=unit,
                    measured_at=observed_at,
                    source=source,
                )
            )
            snapshot[metric] = float(value)

        user.body_measurements = snapshot

    async def record_profile_changes(
        self,
        user: User,
        new_measurements: dict | None,
        *,
        source: str = "manual",
        measured_at: datetime | None = None,
    ) -> None:
        user = await lock_user_for_measurement_update(self.db, user)
        old = user.body_measurements or {}
        new = new_measurements or {}
        observed_at = measured_at or datetime.now(UTC)

        for metric, unit in MEASUREMENT_UNITS.items():
            new_value = _number(new.get(metric))
            if new_value is None:
                continue
            old_value = _number(old.get(metric))
            if old_value == new_value:
                continue
            self.db.add(
                BodyMeasurementObservation(
                    user_id=user.id,
                    metric=metric,
                    value=new_value,
                    unit=unit,
                    measured_at=observed_at,
                    source=source,
                )
            )

    async def current_state(self, user: User) -> dict[str, dict]:
        snapshot = user.body_measurements or {}
        if not snapshot:
            return {}

        current_metrics = [
            metric for metric in MEASUREMENT_UNITS if _number(snapshot.get(metric)) is not None
        ]
        result = await self.db.execute(
            select(BodyMeasurementObservation)
            .where(
                BodyMeasurementObservation.user_id == user.id,
                BodyMeasurementObservation.metric.in_(current_metrics),
            )
            .distinct(BodyMeasurementObservation.metric)
            .order_by(
                BodyMeasurementObservation.metric,
                BodyMeasurementObservation.measured_at.desc().nullslast(),
                BodyMeasurementObservation.created_at.desc(),
            )
        )
        latest = {row.metric: row for row in result.scalars()}

        state: dict[str, dict] = {}
        for metric, unit in MEASUREMENT_UNITS.items():
            current_value = _number(snapshot.get(metric))
            if current_value is None:
                continue
            observation = latest.get(metric)
            if observation is not None and observation.value == current_value:
                state[metric] = {
                    "value": float(current_value),
                    "unit": observation.unit,
                    "measured_at": observation.measured_at,
                    "source": observation.source,
                }
            else:
                state[metric] = {
                    "value": float(current_value),
                    "unit": unit,
                    "measured_at": None,
                    "source": "legacy_profile",
                }
        return state

    async def history(self, user: User, *, limit: int = 200) -> list[dict]:
        result = await self.db.execute(
            select(BodyMeasurementObservation)
            .where(BodyMeasurementObservation.user_id == user.id)
            .order_by(
                BodyMeasurementObservation.measured_at.desc().nullslast(),
                BodyMeasurementObservation.created_at.desc(),
            )
            .limit(limit)
        )
        return [
            {
                "id": str(observation.id),
                "metric": observation.metric,
                "value": float(observation.value),
                "unit": observation.unit,
                "measured_at": observation.measured_at,
                "source": observation.source,
                "created_at": observation.created_at,
            }
            for observation in result.scalars()
        ]
