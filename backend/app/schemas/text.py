import unicodedata
from itertools import groupby
from typing import Annotated

from pydantic import AfterValidator

# Names are interpolated into email Subject headers and chat messages, where a line break could
# inject a header or forge a message line, so control characters and line separators are refused,
# or flattened to spaces in text an outside system owns.
_FORBIDDEN_CATEGORIES = {"Cc", "Zl", "Zp"}

# A name made only of these renders blank, and str.strip keeps them. Python has no property for
# Default_Ignorable_Code_Point, so these are its ranges from DerivedCoreProperties.txt (Unicode
# 18.0), plus three that are not ignorable but render nothing on their own: the Braille blank, the
# interlinear annotation controls and the Egyptian hieroglyph format controls. Matching the Cf
# category instead would refuse visible format characters such as U+06DD END OF AYAH.
_INVISIBLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x2800, 0x2800),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0xFFF9, 0xFFFB),
    (0x13430, 0x1343F),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


# A combining mark draws on the character before it, so a name of marks alone has nothing to show.
_COMBINING_CATEGORIES = {"Mn", "Me"}


def _is_invisible(char: str) -> bool:
    if char.isspace() or unicodedata.category(char) in _COMBINING_CATEGORIES:
        return True
    code = ord(char)
    return any(low <= code <= high for low, high in _INVISIBLE_RANGES)


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
    return all(_is_invisible(char) for char in value)


def reject_blank(value: str) -> str:
    if is_blank(value):
        raise ValueError("must not be blank")
    return value


SingleLineText = Annotated[str, AfterValidator(reject_control_characters)]
SingleLineName = Annotated[SingleLineText, AfterValidator(reject_blank)]
