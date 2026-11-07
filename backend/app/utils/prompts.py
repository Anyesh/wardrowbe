import json
import logging
import re
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PAIRS_WELL_WITH = "pairs well with:"


def load_prompt(name: str) -> str:
    prompt_path = PROMPTS_DIR / f"{name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text().strip()


def _json(value: object) -> object:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return value
    return value


def _decoded(value: object) -> object:
    value = _json(value)
    while isinstance(value, list) and len(value) == 1:
        value = _json(value[0])
    return value


# Prompts label items as "[12] description", and some models echo the label (or the whole line)
# back as [12], "[12]" or "[12] description". The partner labels a line lists are not picks.
def _numbers_named(text: str) -> list[str]:
    if re.fullmatch(r"[\d\s,]*", text):
        return re.findall(r"\d+", text)
    text = re.sub(rf"{re.escape(PAIRS_WELL_WITH)}(\s*\[\s*\d+\s*\]\s*,?)+", "", text)
    if not re.match(r"\s*\[\s*\d+\s*\]", text):
        return []
    return re.findall(r"\[\s*(\d+)\s*\]", text)


def _item_number(value: object) -> int | None:
    value = _decoded(value)
    if isinstance(value, str):
        named = _numbers_named(value)
        value = named[0] if len(named) == 1 else value
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return None


def _names_several_items(entry: object) -> bool:
    if isinstance(entry, list):
        return len(entry) > 1
    return isinstance(entry, str) and len(_numbers_named(entry)) > 1


# An entry naming several items is a separate look or a run-on line, so no outfit is built from
# the answer; a prose answer is not read either, because one line would leave the rest behind.
def _entries(numbers: object) -> list[object] | None:
    numbers = _json(numbers)
    if isinstance(numbers, int | float):
        numbers = [numbers]
    if not isinstance(numbers, list):
        return None
    if len(numbers) == 1 and isinstance(inner := _decoded(numbers[0]), list):
        numbers = inner
    entries = [_decoded(entry) for entry in numbers]
    if any(_names_several_items(entry) for entry in entries):
        return None
    return entries


def picked_item_ids(numbers: object, number_map: dict[int, UUID]) -> list[UUID]:
    entries = _entries(numbers)
    if entries is None:
        logger.warning(f"AI returned items that are not one list of item numbers: {numbers!r}")
        entries = []
    picked: list[UUID] = []
    for num in entries:
        num_int = _item_number(num)
        if num_int is None:
            logger.warning(f"AI returned non-numeric item: {num}")
        elif num_int not in number_map:
            logger.warning(f"AI selected invalid item number: {num}")
        elif number_map[num_int] not in picked:
            picked.append(number_map[num_int])
    return picked
