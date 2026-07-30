DEFAULT_LOCALE = "en"

# Order is the order the UI language picker renders; keep it stable.
SUPPORTED_LOCALES: tuple[str, ...] = (
    "en",
    "zh-CN",
    "zh-TW",
    "ko",
    "ja",
    "fr",
    "de",
    "it",
)

_SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)


def is_supported_locale(value: object) -> bool:
    return isinstance(value, str) and value in _SUPPORTED_LOCALE_SET
