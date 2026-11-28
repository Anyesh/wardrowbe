"""User-configured AI endpoints as stored in UserPreference.ai_endpoints.

Each stored endpoint is a dict with id, name, url, vision_model, text_model, enabled and api_key.
The key is write-only: clients only ever see whether one is set.

An endpoint saved before endpoints had keys of their own has no "api_key" entry at all, and is still
sent the server's AI_API_KEY so that existing setups keep working. An endpoint saved since then is
sent only its own key (or none), so a URL typed into Settings never receives the server's key.
"""

import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Protocol


class EndpointInput(Protocol):
    id: str | None
    name: str
    url: str
    vision_model: str | None
    text_model: str | None
    enabled: bool
    api_key: str | None


def same_url(a: str | None, b: str | None) -> bool:
    return (a or "").strip().rstrip("/") == (b or "").strip().rstrip("/")


def uses_server_key(stored: Mapping[str, Any]) -> bool:
    return "api_key" not in stored


def endpoint_api_key(stored: Mapping[str, Any], server_key: str | None) -> str | None:
    if uses_server_key(stored):
        return server_key
    return stored.get("api_key") or None


def _find_previous(
    endpoint: EndpointInput, by_id: dict[str, dict], legacy: list[dict]
) -> dict | None:
    if endpoint.id and endpoint.id in by_id:
        return by_id.pop(endpoint.id)
    # Endpoints saved before they had ids come back without one; their URL is all that ties the
    # edited copy to the stored one.
    if not endpoint.id:
        for candidate in legacy:
            if same_url(candidate.get("url"), endpoint.url):
                legacy.remove(candidate)
                return candidate
    return None


def merge_endpoints(incoming: Iterable[EndpointInput], stored: list[dict] | None) -> list[dict]:
    """The endpoint list to store, carrying each endpoint's key over from what was stored.

    api_key on an incoming endpoint is None to keep the stored key, "" to remove it, or a new key.
    A kept key follows the endpoint only while its URL is unchanged: pointing an endpoint at a
    different server drops the key, so it is never sent somewhere it was not entered for.
    """
    stored = [dict(ep) for ep in (stored or []) if isinstance(ep, Mapping)]
    by_id = {ep["id"]: ep for ep in stored if ep.get("id")}
    legacy = [ep for ep in stored if not ep.get("id")]

    merged = []
    for endpoint in incoming:
        previous = _find_previous(endpoint, by_id, legacy)
        entry: dict[str, Any] = {
            "id": previous["id"] if previous and previous.get("id") else uuid.uuid4().hex,
            "name": endpoint.name,
            "url": endpoint.url,
            "vision_model": endpoint.vision_model,
            "text_model": endpoint.text_model,
            "enabled": endpoint.enabled,
        }
        if endpoint.api_key is not None:
            entry["api_key"] = endpoint.api_key.strip() or None
        elif previous is not None and same_url(previous.get("url"), endpoint.url):
            if not uses_server_key(previous):
                entry["api_key"] = previous.get("api_key")
            # else: a legacy endpoint left as it was keeps using the server key.
        else:
            entry["api_key"] = None
        merged.append(entry)
    return merged


def public_endpoint(stored: Mapping[str, Any]) -> dict:
    """What a client may see of a stored endpoint: everything but the key itself."""
    return {
        "id": stored.get("id"),
        "name": stored.get("name", ""),
        "url": stored.get("url", ""),
        "vision_model": stored.get("vision_model", "moondream"),
        "text_model": stored.get("text_model", "phi3:mini"),
        "enabled": stored.get("enabled", True),
        "has_api_key": bool(stored.get("api_key")),
        "uses_server_key": uses_server_key(stored),
    }


def find_stored_endpoint(
    stored: list[dict] | None, *, endpoint_id: str | None, url: str
) -> dict | None:
    """The stored endpoint a connection test refers to, only if it still points at that URL."""
    for ep in stored or []:
        if not isinstance(ep, Mapping) or not same_url(ep.get("url"), url):
            continue
        if endpoint_id and ep.get("id") == endpoint_id:
            return dict(ep)
        if not endpoint_id and not ep.get("id"):
            return dict(ep)
    return None
