from typing import Annotated

import email_validator
from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

# Self-hosted installs sign in with addresses such as admin@nas.local or alice@home.arpa that
# never leave the LAN, so those special-use names must be accepted. The library exposes this only
# as a module-level list (its documented knob) because validate_email has no per-call flag for it.
# .invalid and .onion stay rejected because no LAN install uses them.
LAN_DOMAIN_SUFFIXES = ("arpa", "local", "localhost", "test")
email_validator.SPECIAL_USE_DOMAIN_NAMES[:] = [
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES if name not in LAN_DOMAIN_SUFFIXES
]


def normalise_email(value: str) -> str:
    try:
        result = validate_email(
            value.strip(), check_deliverability=False, globally_deliverable=False
        )
    except EmailNotValidError as e:
        raise ValueError(str(e)) from e
    return result.normalized.lower()


EmailAddress = Annotated[str, AfterValidator(normalise_email)]
