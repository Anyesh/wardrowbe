from dataclasses import dataclass

from fastapi import Query

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class PaginationParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    def has_more(self, total: int) -> bool:
        return self.page * self.page_size < total
