from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

ErrorParams = dict[str, str | int | float]


class CodedHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        params: ErrorParams | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = error_code
        self.params = params


class Coded:
    code: str

    def __init__(self, message: str, *, code: str | None = None, **params: Any) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.params: ErrorParams = params


class CodedValueError(Coded, ValueError):
    code = "INVALID_INPUT"


def http_error(
    status_code: int,
    exc: BaseException,
    fallback_code: str,
    headers: Mapping[str, str] | None = None,
) -> CodedHTTPException:
    if isinstance(exc, Coded):
        return CodedHTTPException(status_code, exc.code, str(exc), exc.params or None, headers)
    return CodedHTTPException(status_code, fallback_code, str(exc), None, headers)
