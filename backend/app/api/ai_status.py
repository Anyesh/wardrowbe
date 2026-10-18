import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.models.user import User
from app.services.ai_service import get_ai_service
from app.utils.auth import get_current_user

router = APIRouter(prefix="/ai", tags=["AI"])

# The sidebar asks every minute from every open tab; one probe per window is plenty.
CACHE_SECONDS = 20
_cache: dict[str, tuple[float, "AIStatusResponse"]] = {}


class AIStatusResponse(BaseModel):
    status: Literal["online", "model_missing", "offline", "disabled"]
    vision_model: str | None = None
    text_model: str | None = None
    missing_models: list[str] = []


def _matches(model: str, available: list[str]) -> bool:
    """A configured model setting is there when any of its models is: the setting can be a
    comma-separated rotation, and Ollama lists "name:tag" (no tag means ":latest")."""
    for choice in (part.strip() for part in model.split(",")):
        if not choice:
            continue
        candidates = {choice, choice if ":" in choice else f"{choice}:latest"}
        if any(name in candidates for name in available):
            return True
    return False


def _wanted(vision_model: str | None, text_model: str | None) -> list[str]:
    """The models in use: a capability that is switched off cannot be missing."""
    settings = get_settings()
    wanted = []
    if vision_model and settings.effective_ai_vision_enabled:
        wanted.append(vision_model)
    if text_model and settings.effective_ai_text_enabled:
        wanted.append(text_model)
    return wanted


def summarize(raw: dict) -> AIStatusResponse:
    endpoints = raw.get("endpoints", [])
    healthy = [ep for ep in endpoints if ep.get("status") == "healthy"]
    if not healthy:
        first = endpoints[0] if endpoints else {}
        return AIStatusResponse(
            status="offline",
            vision_model=first.get("vision_model"),
            text_model=first.get("text_model"),
        )
    endpoint = healthy[0]
    available = endpoint.get("available_models") or []
    wanted = _wanted(endpoint.get("vision_model"), endpoint.get("text_model"))
    missing = sorted({m for m in wanted if not _matches(m, available)})
    return AIStatusResponse(
        status="model_missing" if missing else "online",
        vision_model=endpoint.get("vision_model"),
        text_model=endpoint.get("text_model"),
        missing_models=missing,
    )


@router.get("/status", response_model=AIStatusResponse)
async def ai_status(_: Annotated[User, Depends(get_current_user)]) -> AIStatusResponse:
    if not get_settings().ai_enabled:
        return AIStatusResponse(status="disabled")
    cached = _cache.get("status")
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    result = summarize(await get_ai_service().check_health())
    _cache["status"] = (time.monotonic(), result)
    return result
