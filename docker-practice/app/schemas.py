from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewBase(BaseModel):
    product_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str = Field(..., max_length=100)
    text: str
    rating: int = Field(..., ge=1, le=5)

    @field_validator("name", "text")
    @classmethod
    def not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(BaseModel):
    is_approved: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class ReviewResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    text: str
    rating: int
    is_approved: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewList(BaseModel):
    items: list[ReviewResponse]
    total: int


class RatingSummary(BaseModel):
    average: Optional[float] = None
    count: int
    product_id: Optional[int] = None


class ErrorResponse(BaseModel):
    error: str
    code: int
    details: Optional[dict] = None
