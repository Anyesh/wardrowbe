import unicodedata
from itertools import groupby
from typing import Annotated

from pydantic import AfterValidator

# Names are interpolated into email Subject headers and chat messages, where a line break could
# inject a header or forge a message line, so control characters and line separators are refused,
# or flattened to spaces in text an outside system owns.
_FORBIDDEN_CATEGORIES = {"Cc", "Zl", "Zp"}


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


SingleLineText = Annotated[str, AfterValidator(reject_control_characters)]
