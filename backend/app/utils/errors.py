from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException


class CodedHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        params: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = error_code
        self.params = params
