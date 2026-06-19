from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int

    @classmethod
    def create(cls, items: list[Any], total: int) -> "PaginatedResponse[T]":
        return cls(items=items, total=total)
