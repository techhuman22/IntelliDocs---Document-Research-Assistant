"""
Shared Pydantic v2 base schemas and response envelopes.

All API response schemas inherit from BaseResponse.
All API request schemas inherit from BaseRequest.

The standard error envelope is defined in core/exceptions.py.
"""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class BaseRequest(BaseModel):
    """Base for all request schemas. Forbids extra fields by default."""

    model_config = ConfigDict(
        extra="forbid",             # reject unknown fields — fail fast on typos
        str_strip_whitespace=True,  # strip leading/trailing whitespace from strings
    )


class BaseResponse(BaseModel):
    """Base for all response schemas. Allows ORM model instances as input."""

    model_config = ConfigDict(
        from_attributes=True,       # enables model_validate(orm_instance)
        populate_by_name=True,
    )


class PaginatedResponse(BaseResponse, Generic[DataT]):
    """
    Standard pagination envelope for list endpoints.

    Usage:
        response: PaginatedResponse[DocumentResponse] = PaginatedResponse(
            items=docs, total=100, page=1, limit=20
        )
    """

    items: list[DataT]
    total: int
    page: int
    limit: int

    @property
    def pages(self) -> int:
        if self.limit == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1
