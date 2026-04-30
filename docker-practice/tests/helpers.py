"""
Utility functions shared across the test suite.
Not a conftest – import these directly where needed.
"""
from __future__ import annotations

from app import schemas

_DEFAULTS: dict = dict(
    product_id=None,
    user_id=None,
    name="Test User",
    text="Great flowers, fast delivery.",
    rating=5,
)


def make_review(**overrides) -> schemas.ReviewCreate:
    """Return a ReviewCreate with sensible defaults, overriding specific fields."""
    return schemas.ReviewCreate(**{**_DEFAULTS, **overrides})
