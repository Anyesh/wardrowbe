import unicodedata
from itertools import groupby
from typing import Annotated

from pydantic import AfterValidator

# Names are interpolated into email Subject headers and chat messages, where a line break could
# inject a header or forge a message line, so control characters and line separators are refused,
# or flattened to spaces in text an outside system owns.
_FORBIDDEN_CATEGORIES = {"Cc", "Zl", "Zp"}

# str.strip keeps these zero-width characters, so a name made only of them renders blank.
_INVISIBLE_CHARACTERS = {"\u200b", "\u2060", "\ufeff"}


def _is_forbidden(char: str) -> bool:
    return unicodedata.category(char) in _FORBIDDEN_CATEGORIES


def reject_control_characters(value: str) -> str:
    if any(_is_forbidden(char) for char in value):
        raise ValueError("must not contain line breaks or control characters")
    return value


def flatten_control_characters(value: object) -> object:
    if not isinstance(value, str):
        return value
    runs = groupby(value, key=_is_forbidden)
    return "".join(" " if forbidden else "".join(run) for forbidden, run in runs).strip()


def is_blank(value: str) -> bool:
    return all(char.isspace() or char in _INVISIBLE_CHARACTERS for char in value)


def reject_blank(value: str) -> str:
    if is_blank(value):
        raise ValueError("must not be blank")
    return value


SingleLineText = Annotated[str, AfterValidator(reject_control_characters)]
SingleLineName = Annotated[SingleLineText, AfterValidator(reject_blank)]
