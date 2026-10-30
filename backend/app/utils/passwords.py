import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2-cffi's defaults are the RFC 9106 low-memory Argon2id profile (t=3, m=64 MiB, p=4).
_hasher = PasswordHasher()

PASSWORD_MIN_LENGTH = 8
# Long enough for any passphrase or password-manager output, short enough that a request cannot
# make the server hash megabytes.
PASSWORD_MAX_LENGTH = 256

# Verified against when the email is unknown, so that a sign-in for a missing account costs the
# same time as one with a wrong password and the response time does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("wardrowbe-timing-equaliser")


async def hash_password(password: str) -> str:
    # Hashing takes tens of milliseconds of CPU by design, so it runs off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def verify_password(password_hash: str | None, password: str) -> bool:
    if password_hash is None:
        await asyncio.to_thread(_verify, _DUMMY_HASH, password)
        return False
    return await asyncio.to_thread(_verify, password_hash, password)


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
