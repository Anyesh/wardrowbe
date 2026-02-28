import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.user import User
from app.services.weather_service import WeatherService, WeatherServiceError
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["Weather"])


class WeatherResponse(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    feels_like: float = Field(description="Apparent temperature in Celsius")
    humidity: int = Field(description="Relative humidity percentage")
    precipitation_chance: int = Field(description="Chance of precipitation percentage")
    precipitation_mm: float = Field(description="Current precipitation in mm")
    wind_speed: float = Field(description="Wind speed in km/h")
    condition: str = Field(description="Weather condition description")
    condition_code: int = Field(description="WMO weather code")
    is_day: bool = Field(description="Whether it's daytime")
    uv_index: float = Field(description="UV index")
    timestamp: str = Field(description="Timestamp of weather data")


class ForecastDayResponse(BaseModel):
    date: str = Field(description="Date in YYYY-MM-DD format")
    temp_min: float = Field(description="Minimum temperature in Celsius")
    temp_max: float = Field(description="Maximum temperature in Celsius")
    precipitation_chance: int = Field(description="Maximum precipitation chance percentage")
    condition: str = Field(description="Weather condition description")
    condition_code: int = Field(description="WMO weather code")


class ForecastResponse(BaseModel):
    latitude: float
    longitude: float
    forecast: list[ForecastDayResponse]


class WeatherOverride(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    condition: str = Field(default="unknown", description="Weather condition")
    precipitation_chance: int = Field(default=0, ge=0, le=100)


@router.get("/current", response_model=WeatherResponse)
async def get_current_weather(
    current_user: Annotated[User, Depends(get_current_user)],
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
) -> WeatherResponse:
    # Use provided coordinates or fall back to user's location
    lat = latitude if latitude is not None else current_user.location_lat
    lon = longitude if longitude is not None else current_user.location_lon

    if lat is None or lon is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location not set. Please provide coordinates or set your location in settings.",
        )

    weather_service = WeatherService()

    try:
        weather = await weather_service.get_current_weather(float(lat), float(lon))
    except WeatherServiceError as e:
        logger.error(f"Weather service error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable",
        ) from None

    return WeatherResponse(
        temperature=weather.temperature,
        feels_like=weather.feels_like,
        humidity=weather.humidity,
        precipitation_chance=weather.precipitation_chance,
        precipitation_mm=weather.precipitation_mm,
        wind_speed=weather.wind_speed,
        condition=weather.condition,
        condition_code=weather.condition_code,
        is_day=weather.is_day,
        uv_index=weather.uv_index,
        timestamp=weather.timestamp.isoformat(),
    )


@router.get("/forecast", response_model=ForecastResponse)
async def get_weather_forecast(
    current_user: Annotated[User, Depends(get_current_user)],
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    days: int = Query(7, ge=1, le=16),
) -> ForecastResponse:
    # Use provided coordinates or fall back to user's location
    lat = latitude if latitude is not None else current_user.location_lat
    lon = longitude if longitude is not None else current_user.location_lon

    if lat is None or lon is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location not set. Please provide coordinates or set your location in settings.",
        )

    weather_service = WeatherService()

    try:
        forecast = await weather_service.get_daily_forecast(float(lat), float(lon), days)
    except WeatherServiceError as e:
        logger.error(f"Weather service error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable",
        ) from None

    return ForecastResponse(
        latitude=float(lat),
        longitude=float(lon),
        forecast=[
            ForecastDayResponse(
                date=day.date,
                temp_min=day.temp_min,
                temp_max=day.temp_max,
                precipitation_chance=day.precipitation_chance,
                condition=day.condition,
                condition_code=day.condition_code,
            )
            for day in forecast
        ],
    )
