"""
Unit tests for app/schemas.py (Pydantic models).

No database, no HTTP client – only schema instantiation and validation.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    RatingSummary,
    ReviewCreate,
    ReviewList,
    ReviewResponse,
    ReviewUpdate,
)

# ══════════════════════════════════════════════════════════════════════════════
# ReviewCreate  (inherits ReviewBase validators)
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewCreate:

    # — Happy path ─────────────────────────────────────────────────────────────

    def test_valid_minimal(self):
        r = ReviewCreate(name="Alice", text="Nice flowers!", rating=3)
        assert r.name == "Alice"
        assert r.text == "Nice flowers!"
        assert r.rating == 3
        assert r.product_id is None
        assert r.user_id is None

    def test_valid_with_all_optional_fields(self):
        r = ReviewCreate(
            name="Bob", text="Good.", rating=5, product_id=7, user_id=42
        )
        assert r.product_id == 7
        assert r.user_id == 42

    def test_rating_lower_boundary(self):
        r = ReviewCreate(name="X", text="Ok.", rating=1)
        assert r.rating == 1

    def test_rating_upper_boundary(self):
        r = ReviewCreate(name="X", text="Ok.", rating=5)
        assert r.rating == 5

    def test_name_exactly_100_chars(self):
        name = "A" * 100
        r = ReviewCreate(name=name, text="Good.", rating=3)
        assert len(r.name) == 100

    # — Whitespace stripping (not_empty validator) ─────────────────────────────

    def test_name_with_leading_trailing_spaces_is_stripped(self):
        r = ReviewCreate(name="  Alice  ", text="Good.", rating=3)
        assert r.name == "Alice"

    def test_text_with_leading_trailing_spaces_is_stripped(self):
        r = ReviewCreate(name="Alice", text="  Nice!  ", rating=3)
        assert r.text == "Nice!"

    # — Empty / blank field validation ────────────────────────────────────────

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewCreate(name="", text="Nice!", rating=4)
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewCreate(name="   ", text="Nice!", rating=4)
        assert "empty" in str(exc_info.value).lower()

    def test_tab_only_name_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="\t\n", text="Nice!", rating=4)

    def test_empty_text_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ReviewCreate(name="Alice", text="", rating=4)
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", text="   ", rating=4)

    # — Rating out-of-range ────────────────────────────────────────────────────

    def test_rating_zero_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", text="Ok.", rating=0)

    def test_rating_six_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", text="Ok.", rating=6)

    def test_rating_negative_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", text="Ok.", rating=-1)

    # — Field length ───────────────────────────────────────────────────────────

    def test_name_101_chars_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="A" * 101, text="Good.", rating=3)

    # — Missing required fields ────────────────────────────────────────────────

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(text="Nice!", rating=4)  # type: ignore[call-arg]

    def test_missing_text_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", rating=4)  # type: ignore[call-arg]

    def test_missing_rating_raises(self):
        with pytest.raises(ValidationError):
            ReviewCreate(name="Alice", text="Nice!")  # type: ignore[call-arg]


# ══════════════════════════════════════════════════════════════════════════════
# ReviewUpdate
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewUpdate:

    # — Happy path ─────────────────────────────────────────────────────────────

    def test_set_approved_true(self):
        u = ReviewUpdate(is_approved=True)
        assert u.is_approved is True

    def test_set_approved_false(self):
        u = ReviewUpdate(is_approved=False)
        assert u.is_approved is False

    def test_all_defaults_none_is_schema_valid(self):
        # Schema allows empty; the API layer rejects it with 422.
        u = ReviewUpdate()
        assert u.is_approved is None

    # — Extra fields are forbidden ─────────────────────────────────────────────

    def test_extra_field_name_raises(self):
        with pytest.raises(ValidationError):
            ReviewUpdate(is_approved=True, name="hacker")  # type: ignore[call-arg]

    def test_extra_field_text_raises(self):
        with pytest.raises(ValidationError):
            ReviewUpdate(text="injected")  # type: ignore[call-arg]

    def test_extra_field_rating_raises(self):
        with pytest.raises(ValidationError):
            ReviewUpdate(rating=5)  # type: ignore[call-arg]

    # — model_dump exclude_unset semantics ────────────────────────────────────

    def test_model_dump_exclude_unset_empty_when_nothing_set(self):
        u = ReviewUpdate()
        assert u.model_dump(exclude_unset=True) == {}

    def test_model_dump_exclude_unset_contains_only_set_field(self):
        u = ReviewUpdate(is_approved=False)
        assert u.model_dump(exclude_unset=True) == {"is_approved": False}


# ══════════════════════════════════════════════════════════════════════════════
# ReviewResponse
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewResponse:
    def _now(self):
        return datetime.now(timezone.utc)

    def test_all_fields_populated(self):
        now = self._now()
        resp = ReviewResponse(
            id=1,
            product_id=2,
            user_id=3,
            name="Alice",
            text="Great!",
            rating=5,
            is_approved=True,
            created_at=now,
        )
        assert resp.id == 1
        assert resp.product_id == 2
        assert resp.name == "Alice"
        assert resp.is_approved is True
        assert resp.created_at == now

    def test_optional_fields_can_be_none(self):
        resp = ReviewResponse(
            id=7,
            product_id=None,
            user_id=None,
            name="User",
            text="Good.",
            rating=4,
            is_approved=False,
            created_at=self._now(),
        )
        assert resp.product_id is None
        assert resp.user_id is None


# ══════════════════════════════════════════════════════════════════════════════
# ReviewList
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewList:
    def _make_response(self, **kwargs):
        defaults = dict(
            id=1, name="User", text="Nice.", rating=5,
            is_approved=True, created_at=datetime.now(timezone.utc)
        )
        return ReviewResponse(**{**defaults, **kwargs})

    def test_empty_list(self):
        rl = ReviewList(items=[], total=0)
        assert rl.total == 0
        assert rl.items == []

    def test_list_with_one_item(self):
        item = self._make_response(id=1)
        rl = ReviewList(items=[item], total=1)
        assert rl.total == 1
        assert len(rl.items) == 1

    def test_total_can_exceed_items_count(self):
        # e.g. page 2 of 10 items; total reflects full count
        item = self._make_response(id=1)
        rl = ReviewList(items=[item], total=50)
        assert rl.total == 50
        assert len(rl.items) == 1


# ══════════════════════════════════════════════════════════════════════════════
# RatingSummary
# ══════════════════════════════════════════════════════════════════════════════

class TestRatingSummary:
    def test_with_average_and_product_id(self):
        rs = RatingSummary(average=4.5, count=10, product_id=1)
        assert rs.average == 4.5
        assert rs.count == 10
        assert rs.product_id == 1

    def test_average_can_be_none_when_no_reviews(self):
        rs = RatingSummary(average=None, count=0, product_id=None)
        assert rs.average is None
        assert rs.count == 0
        assert rs.product_id is None

    def test_product_id_optional(self):
        rs = RatingSummary(average=3.0, count=5)
        assert rs.product_id is None
