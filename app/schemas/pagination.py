import math
from typing import Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    pages: int
    limit: int

    @classmethod
    def crear(cls, items: List[T], total: int, page: int, limit: int):
        pages = math.ceil(total / limit) if limit > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            pages=pages,
            limit=limit
        )