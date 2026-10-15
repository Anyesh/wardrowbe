import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.database import DbSession
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.packing_service import (
    FORECAST_HORIZON_DAYS,
    MAX_TRIP_DAYS,
    PackingService,
    trip_length,
)
from app.services.weather_service import GeocodingServiceError, WeatherService, WeatherServiceError
from app.utils.auth import get_current_user
from app.utils.garment_vocabulary import OCCASIONS
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/packing", tags=["Packing"])


class PackingRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    occasion: str = "travel"
    laundry: bool = False

    @field_validator("destination")
    @classmethod
    def strip_destination(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Destination is required")
        return value

    @field_validator("occasion")
    @classmethod
    def known_occasion(cls, value: str) -> str:
        if value not in OCCASIONS:
            raise ValueError(f"Unknown occasion: {value}")
        return value

    @model_validator(mode="after")
    def valid_range(self) -> "PackingRequest":
        if self.end_date < self.start_date:
            raise ValueError("The trip cannot end before it starts")
        if trip_length(self.start_date, self.end_date) > MAX_TRIP_DAYS:
            raise ValueError(f"Trips are limited to {MAX_TRIP_DAYS} days")
        return self


class PackingDayResponse(BaseModel):
    date: str
    temp_min: float
    temp_max: float
    precipitation_chance: int
    condition: str


class PackingGroupResponse(BaseModel):
    role: str
    needed: int
    items: list[ItemResponse]


class PackingResponse(BaseModel):
    destination: str
    latitude: float
    longitude: float
    start_date: date
    end_date: date
    days: int
    season: str
    estimated: bool
    temp_min: float
    temp_max: float
    rain_days: int
    forecast: list[PackingDayResponse]
    groups: list[PackingGroupResponse]
    missing_roles: list[str]


@router.post("", response_model=PackingResponse)
async def plan_packing(
    request: PackingRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackingResponse:
    today = get_user_today(current_user)
    if request.end_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The trip is already over"
        )

    weather_service = WeatherService()
    try:
        place = await weather_service.geocode_location_name(request.destination)
    except GeocodingServiceError as e:
        logger.error(f"Geocoding service error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location search is temporarily unavailable",
        ) from None
    if not place:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")
    latitude, longitude, name = place

    forecast = []
    days_ahead = (request.start_date - today).days
    if days_ahead < FORECAST_HORIZON_DAYS:
        span = min(FORECAST_HORIZON_DAYS, (request.end_date - today).days + 1)
        try:
            forecast = await weather_service.get_daily_forecast(latitude, longitude, max(1, span))
        except WeatherServiceError as e:
            # A seasonal estimate still gives a usable list; the response says it is estimated.
            logger.warning(f"Forecast unavailable for packing: {e}")

    weather, season, groups = await PackingService(db).plan(
        current_user,
        request.start_date,
        request.end_date,
        latitude,
        forecast,
        request.occasion,
        request.laundry,
    )

    return PackingResponse(
        destination=name or request.destination,
        latitude=latitude,
        longitude=longitude,
        start_date=request.start_date,
        end_date=request.end_date,
        days=trip_length(request.start_date, request.end_date),
        season=season,
        estimated=weather.estimated,
        temp_min=round(weather.temp_min, 1),
        temp_max=round(weather.temp_max, 1),
        rain_days=weather.rain_days,
        forecast=[
            PackingDayResponse(
                date=d.date,
                temp_min=d.temp_min,
                temp_max=d.temp_max,
                precipitation_chance=d.precipitation_chance,
                condition=d.condition,
            )
            for d in weather.days
        ],
        groups=[
            PackingGroupResponse(
                role=g.role,
                needed=g.needed,
                items=[ItemResponse.model_validate(i) for i in g.items],
            )
            for g in groups
        ],
        missing_roles=[g.role for g in groups if len(g.items) < g.needed],
    )
