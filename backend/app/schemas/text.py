import unicodedata
from typing import Annotated

from pydantic import AfterValidator

# Names are interpolated into email Subject headers and chat messages, where a line break could
# inject a header or forge a message line, so control characters and line separators are refused.
_FORBIDDEN_CATEGORIES = {"Cc", "Zl", "Zp"}


def reject_control_characters(value: str) -> str:
    if any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in value):
        raise ValueError("must not contain line breaks or control characters")
    return value


SingleLineText = Annotated[str, AfterValidator(reject_control_characters)]
