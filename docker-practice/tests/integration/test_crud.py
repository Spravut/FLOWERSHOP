"""
Integration tests for app/crud.py.

Each test runs against a fresh in-memory SQLite database provided by the
``db`` fixture from tests/conftest.py. No HTTP layer is involved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models, schemas
from tests.helpers import make_review


# ══════════════════════════════════════════════════════════════════════════════
# create_review
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateReview:

    def test_returns_model_instance_with_id(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        assert isinstance(review, models.Review)
        assert review.id is not None

    def test_all_fields_are_persisted(self, db):
        data = make_review(product_id=7, user_id=3, name="Alice", text="Lovely roses.", rating=4)
        review = crud.create_review(db, data, is_approved=True)
        assert review.product_id == 7
        assert review.user_id == 3
        assert review.name == "Alice"
        assert review.text == "Lovely roses."
        assert review.rating == 4
        assert review.is_approved is True

    def test_is_approved_false_is_stored(self, db):
        review = crud.create_review(db, make_review(), is_approved=False)
        assert review.is_approved is False

    def test_created_at_is_populated(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        assert review.created_at is not None

    def test_product_id_none_allowed(self, db):
        review = crud.create_review(db, make_review(product_id=None), is_approved=True)
        assert review.product_id is None

    def test_user_id_none_allowed(self, db):
        review = crud.create_review(db, make_review(user_id=None), is_approved=True)
        assert review.user_id is None

    def test_each_review_gets_unique_id(self, db):
        r1 = crud.create_review(db, make_review(), is_approved=True)
        r2 = crud.create_review(db, make_review(), is_approved=True)
        assert r1.id != r2.id


# ══════════════════════════════════════════════════════════════════════════════
# get_review
# ══════════════════════════════════════════════════════════════════════════════

class TestGetReview:

    def test_returns_review_by_id(self, db):
        created = crud.create_review(db, make_review(), is_approved=True)
        fetched = crud.get_review(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_returned_review_has_correct_data(self, db):
        created = crud.create_review(db, make_review(name="Bob", rating=2), is_approved=False)
        fetched = crud.get_review(db, created.id)
        assert fetched.name == "Bob"
        assert fetched.rating == 2
        assert fetched.is_approved is False

    def test_returns_none_for_nonexistent_id(self, db):
        assert crud.get_review(db, 99999) is None

    def test_returns_none_for_zero_id(self, db):
        assert crud.get_review(db, 0) is None


# ══════════════════════════════════════════════════════════════════════════════
# get_reviews – helper
# ══════════════════════════════════════════════════════════════════════════════

def _get(db, **kwargs):
    """Call get_reviews with sensible defaults, override via kwargs."""
    params = dict(
        limit=100,
        offset=0,
        approved_only=None,
        product_id=None,
        min_rating=None,
        max_rating=None,
        sort="created_at_desc",
    )
    params.update(kwargs)
    return crud.get_reviews(db, **params)


# ══════════════════════════════════════════════════════════════════════════════
# get_reviews
# ══════════════════════════════════════════════════════════════════════════════

class TestGetReviews:
    """
    Seed once per test via autouse fixture (set on self.* so tests can compare).

    Seed contents:
      r1 – product_id=1, rating=5, approved,   created_at = base
      r2 – product_id=1, rating=3, approved,   created_at = base + 1h
      r3 – product_id=2, rating=4, unapproved, created_at = base + 2h
      r4 – product_id=None, rating=2, approved, created_at = base + 3h
    """

    @pytest.fixture(autouse=True)
    def seed(self, db):
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        def _create(offset_h, rating, product_id, is_approved):
            r = crud.create_review(
                db,
                make_review(product_id=product_id, rating=rating),
                is_approved=is_approved,
            )
            r.created_at = base + timedelta(hours=offset_h)
            db.commit()
            db.refresh(r)
            return r

        self.r1 = _create(0, 5, product_id=1,    is_approved=True)
        self.r2 = _create(1, 3, product_id=1,    is_approved=True)
        self.r3 = _create(2, 4, product_id=2,    is_approved=False)
        self.r4 = _create(3, 2, product_id=None, is_approved=True)

    # — No filters ─────────────────────────────────────────────────────────────

    def test_returns_all_reviews_without_filters(self, db):
        items, total = _get(db)
        assert total == 4
        assert len(items) == 4

    def test_total_equals_item_count_without_limit(self, db):
        items, total = _get(db)
        assert total == len(items)

    # — approved_only filter ───────────────────────────────────────────────────

    def test_approved_only_true_excludes_unapproved(self, db):
        items, total = _get(db, approved_only=True)
        assert total == 3
        assert all(r.is_approved for r in items)

    def test_approved_only_false_returns_only_unapproved(self, db):
        items, total = _get(db, approved_only=False)
        assert total == 1
        assert items[0].id == self.r3.id

    def test_approved_only_none_returns_all(self, db):
        _, total = _get(db, approved_only=None)
        assert total == 4

    # — product_id filter ──────────────────────────────────────────────────────

    def test_product_id_filter_returns_matching(self, db):
        items, total = _get(db, product_id=1)
        assert total == 2
        assert all(r.product_id == 1 for r in items)

    def test_product_id_filter_nonexistent_returns_empty(self, db):
        items, total = _get(db, product_id=999)
        assert total == 0
        assert items == []

    def test_product_id_none_disables_filter(self, db):
        # product_id=None in get_reviews means "no product_id filter"
        _, total = _get(db, product_id=None)
        assert total == 4

    # — rating filters ─────────────────────────────────────────────────────────

    def test_min_rating_filter(self, db):
        items, total = _get(db, min_rating=4)
        assert total == 2  # r1(5), r3(4)
        assert all(r.rating >= 4 for r in items)

    def test_max_rating_filter(self, db):
        items, total = _get(db, max_rating=3)
        assert total == 2  # r2(3), r4(2)
        assert all(r.rating <= 3 for r in items)

    def test_rating_range_inclusive(self, db):
        items, total = _get(db, min_rating=3, max_rating=4)
        assert total == 2  # r2(3), r3(4)
        assert all(3 <= r.rating <= 4 for r in items)

    def test_impossible_rating_range_returns_empty(self, db):
        items, total = _get(db, min_rating=5, max_rating=1)
        assert total == 0

    # — pagination ─────────────────────────────────────────────────────────────

    def test_limit_restricts_result_count(self, db):
        items, total = _get(db, limit=2)
        assert total == 4        # total is still the full count
        assert len(items) == 2

    def test_offset_skips_rows(self, db):
        all_items, _ = _get(db, sort="created_at_asc")
        paged_items, total = _get(db, offset=2, sort="created_at_asc")
        assert total == 4
        assert len(paged_items) == 2
        assert paged_items[0].id == all_items[2].id

    def test_offset_beyond_total_returns_empty(self, db):
        items, total = _get(db, offset=100)
        assert total == 4
        assert items == []

    # — sorting ────────────────────────────────────────────────────────────────

    def test_sort_created_at_desc(self, db):
        items, _ = _get(db, sort="created_at_desc")
        dates = [r.created_at for r in items]
        assert dates == sorted(dates, reverse=True)

    def test_sort_created_at_asc(self, db):
        items, _ = _get(db, sort="created_at_asc")
        dates = [r.created_at for r in items]
        assert dates == sorted(dates)

    def test_sort_rating_desc(self, db):
        items, _ = _get(db, sort="rating_desc")
        ratings = [r.rating for r in items]
        assert ratings == sorted(ratings, reverse=True)

    def test_sort_rating_asc(self, db):
        items, _ = _get(db, sort="rating_asc")
        ratings = [r.rating for r in items]
        assert ratings == sorted(ratings)


# ══════════════════════════════════════════════════════════════════════════════
# update_review
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateReview:

    def test_approve_unapproved_review(self, db):
        review = crud.create_review(db, make_review(), is_approved=False)
        updated = crud.update_review(db, review, schemas.ReviewUpdate(is_approved=True))
        assert updated.is_approved is True

    def test_disapprove_approved_review(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        updated = crud.update_review(db, review, schemas.ReviewUpdate(is_approved=False))
        assert updated.is_approved is False

    def test_update_preserves_id(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        original_id = review.id
        crud.update_review(db, review, schemas.ReviewUpdate(is_approved=False))
        assert review.id == original_id

    def test_update_persists_to_db(self, db):
        review = crud.create_review(db, make_review(), is_approved=False)
        crud.update_review(db, review, schemas.ReviewUpdate(is_approved=True))
        reloaded = crud.get_review(db, review.id)
        assert reloaded.is_approved is True

    def test_update_does_not_change_other_fields(self, db):
        data = make_review(name="Unique Name", rating=2)
        review = crud.create_review(db, data, is_approved=False)
        crud.update_review(db, review, schemas.ReviewUpdate(is_approved=True))
        assert review.name == "Unique Name"
        assert review.rating == 2


# ══════════════════════════════════════════════════════════════════════════════
# delete_review
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteReview:

    def test_deleted_review_not_findable(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        review_id = review.id
        crud.delete_review(db, review)
        assert crud.get_review(db, review_id) is None

    def test_delete_returns_none(self, db):
        review = crud.create_review(db, make_review(), is_approved=True)
        result = crud.delete_review(db, review)
        assert result is None

    def test_delete_does_not_affect_other_reviews(self, db):
        r1 = crud.create_review(db, make_review(name="Keep"), is_approved=True)
        r2 = crud.create_review(db, make_review(name="Delete"), is_approved=True)
        crud.delete_review(db, r2)
        assert crud.get_review(db, r1.id) is not None

    def test_total_count_decreases_after_delete(self, db):
        r1 = crud.create_review(db, make_review(), is_approved=True)
        r2 = crud.create_review(db, make_review(), is_approved=True)
        _, before = _get(db)
        crud.delete_review(db, r1)
        _, after = _get(db)
        assert after == before - 1


# ══════════════════════════════════════════════════════════════════════════════
# get_rating_summary
# ══════════════════════════════════════════════════════════════════════════════

class TestGetRatingSummary:

    def test_empty_db_returns_none_average_and_zero_count(self, db):
        avg, count = crud.get_rating_summary(db, product_id=None, approved_only=True)
        assert avg is None
        assert count == 0

    def test_single_approved_review_average_equals_its_rating(self, db):
        crud.create_review(db, make_review(product_id=None, rating=4), is_approved=True)
        avg, count = crud.get_rating_summary(db, product_id=None, approved_only=True)
        assert avg == 4.0
        assert count == 1

    def test_average_is_rounded_to_two_decimals(self, db):
        for rating in (1, 2):
            crud.create_review(db, make_review(product_id=None, rating=rating), is_approved=True)
        avg, _ = crud.get_rating_summary(db, product_id=None, approved_only=True)
        assert avg == round(1.5, 2)

    def test_approved_only_true_excludes_unapproved(self, db):
        crud.create_review(db, make_review(product_id=None, rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=1), is_approved=False)
        avg, count = crud.get_rating_summary(db, product_id=None, approved_only=True)
        assert count == 1
        assert avg == 5.0

    def test_approved_only_false_includes_all(self, db):
        crud.create_review(db, make_review(product_id=None, rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=1), is_approved=False)
        avg, count = crud.get_rating_summary(db, product_id=None, approved_only=False)
        assert count == 2
        assert avg == 3.0

    def test_product_id_filter_isolates_product(self, db):
        crud.create_review(db, make_review(product_id=5,    rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=1), is_approved=True)
        avg, count = crud.get_rating_summary(db, product_id=5, approved_only=False)
        assert count == 1
        assert avg == 5.0

    def test_product_id_none_only_counts_null_product_reviews(self, db):
        # product_id=None in the summary means "reviews with NULL product_id"
        crud.create_review(db, make_review(product_id=None, rating=3), is_approved=True)
        crud.create_review(db, make_review(product_id=1,    rating=5), is_approved=True)
        avg, count = crud.get_rating_summary(db, product_id=None, approved_only=True)
        assert count == 1
        assert avg == 3.0

    def test_nonexistent_product_returns_none_average(self, db):
        crud.create_review(db, make_review(product_id=1, rating=5), is_approved=True)
        avg, count = crud.get_rating_summary(db, product_id=999, approved_only=False)
        assert avg is None
        assert count == 0
