import hashlib
from datetime import UTC, datetime
from uuid import UUID


def item_revision(item_id: UUID, updated_at: datetime) -> str:
    timestamp = (
        updated_at.replace(tzinfo=UTC) if updated_at.tzinfo is None else updated_at.astimezone(UTC)
    )
    payload = f"{item_id}:{timestamp.isoformat(timespec='microseconds')}"
    return "v1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def if_match_accepts(header: str, revision: str) -> bool:
    if header.strip() == "*":
        return True

    candidates: list[str] = []
    start = 0
    in_quotes = False
    for index, char in enumerate(header):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            candidates.append(header[start:index].strip())
            start = index + 1
    candidates.append(header[start:].strip())

    for candidate in candidates:
        if candidate.startswith("W/"):
            continue
        if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
            candidate = candidate[1:-1]
        if candidate == revision:
            return True
    return False
