"""
Integration tests for all FastAPI endpoints in app/main.py.

The ``client`` fixture (from tests/conftest.py) provides a TestClient wired
to an in-memory SQLite database.  Data seeded via the ``db``-based fixtures
(``approved_review``, ``unapproved_review``, ``five_reviews``) is immediately
visible to the API because both share the same SQLAlchemy session.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud
from tests.helpers import make_review

# ── shortcuts ─────────────────────────────────────────────────────────────────

VALID_PAYLOAD = dict(
    name="Anna",
    text="Great bouquet, fast delivery.",
    rating=5,
)


# ══════════════════════════════════════════════════════════════════════════════
# GET /
# ══════════════════════════════════════════════════════════════════════════════

class TestRoot:
    def test_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_message_key(self, client):
        data = client.get("/").json()
        assert "message" in data

    def test_contains_status_running(self, client):
        data = client.get("/").json()
        assert "status" in data


# ══════════════════════════════════════════════════════════════════════════════
# GET /reviews
# ══════════════════════════════════════════════════════════════════════════════

class TestGetReviews:

    # — Empty database ─────────────────────────────────────────────────────────

    def test_empty_db_returns_200(self, client):
        assert client.get("/reviews").status_code == 200

    def test_empty_db_returns_empty_list_and_zero_total(self, client):
        data = client.get("/reviews").json()
        assert data["items"] == []
        assert data["total"] == 0

    # — Basic listing ──────────────────────────────────────────────────────────

    def test_returns_all_reviews(self, client, five_reviews):
        data = client.get("/reviews").json()
        assert data["total"] == 5

    def test_response_schema_has_items_and_total(self, client, approved_review):
        data = client.get("/reviews").json()
        assert "items" in data
        assert "total" in data

    def test_review_item_has_expected_fields(self, client, approved_review):
        item = client.get("/reviews").json()["items"][0]
        for field in ("id", "name", "text", "rating", "is_approved", "created_at"):
            assert field in item

    # — Pagination ─────────────────────────────────────────────────────────────

    def test_limit_restricts_returned_items(self, client, five_reviews):
        data = client.get("/reviews?limit=2").json()
        assert len(data["items"]) == 2
        assert data["total"] == 5          # total still reflects full count

    def test_offset_skips_rows(self, client, five_reviews):
        all_ids   = [r["id"] for r in client.get("/reviews?limit=100").json()["items"]]
        paged_ids = [r["id"] for r in client.get("/reviews?offset=2&limit=100").json()["items"]]
        assert paged_ids == all_ids[2:]

    def test_limit_zero_returns_422(self, client):
        assert client.get("/reviews?limit=0").status_code == 422

    def test_limit_over_100_returns_422(self, client):
        assert client.get("/reviews?limit=101").status_code == 422

    def test_negative_offset_returns_422(self, client):
        assert client.get("/reviews?offset=-1").status_code == 422

    # — approved_only filter ───────────────────────────────────────────────────

    def test_approved_only_true_excludes_unapproved(
        self, client, approved_review, unapproved_review
    ):
        data = client.get("/reviews?approved_only=true").json()
        assert data["total"] == 1
        assert data["items"][0]["is_approved"] is True

    def test_approved_only_false_returns_only_unapproved(
        self, client, approved_review, unapproved_review
    ):
        data = client.get("/reviews?approved_only=false").json()
        assert data["total"] == 1
        assert data["items"][0]["is_approved"] is False

    def test_no_approved_only_param_returns_all(
        self, client, approved_review, unapproved_review
    ):
        data = client.get("/reviews").json()
        assert data["total"] == 2

    # — product_id filter ──────────────────────────────────────────────────────

    def test_product_id_filter_returns_matching_reviews(self, client, five_reviews):
        data = client.get("/reviews?product_id=1").json()
        assert data["total"] == 3
        assert all(r["product_id"] == 1 for r in data["items"])

    def test_product_id_filter_with_no_match_returns_empty(self, client, five_reviews):
        data = client.get("/reviews?product_id=999").json()
        assert data["total"] == 0

    # — rating filters ─────────────────────────────────────────────────────────

    def test_min_rating_filter(self, client, five_reviews):
        data = client.get("/reviews?min_rating=4").json()
        assert all(r["rating"] >= 4 for r in data["items"])

    def test_max_rating_filter(self, client, five_reviews):
        data = client.get("/reviews?max_rating=2").json()
        assert all(r["rating"] <= 2 for r in data["items"])

    def test_min_rating_zero_returns_422(self, client):
        assert client.get("/reviews?min_rating=0").status_code == 422

    def test_max_rating_six_returns_422(self, client):
        assert client.get("/reviews?max_rating=6").status_code == 422

    # — sorting ────────────────────────────────────────────────────────────────

    def test_sort_rating_asc(self, client, five_reviews):
        data = client.get("/reviews?sort=rating_asc").json()
        ratings = [r["rating"] for r in data["items"]]
        assert ratings == sorted(ratings)

    def test_sort_rating_desc(self, client, five_reviews):
        data = client.get("/reviews?sort=rating_desc").json()
        ratings = [r["rating"] for r in data["items"]]
        assert ratings == sorted(ratings, reverse=True)

    def test_sort_created_at_asc(self, client, five_reviews):
        data = client.get("/reviews?sort=created_at_asc").json()
        dates = [r["created_at"] for r in data["items"]]
        assert dates == sorted(dates)

    def test_sort_created_at_desc(self, client, five_reviews):
        data = client.get("/reviews?sort=created_at_desc").json()
        dates = [r["created_at"] for r in data["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_invalid_sort_value_returns_422(self, client):
        assert client.get("/reviews?sort=invalid").status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# POST /reviews
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateReview:

    # — Successful creation ────────────────────────────────────────────────────

    def test_returns_201(self, client):
        resp = client.post("/reviews", json=VALID_PAYLOAD)
        assert resp.status_code == 201

    def test_response_contains_id(self, client):
        data = client.post("/reviews", json=VALID_PAYLOAD).json()
        assert "id" in data
        assert isinstance(data["id"], int)

    def test_response_mirrors_sent_fields(self, client):
        data = client.post("/reviews", json=VALID_PAYLOAD).json()
        assert data["name"] == VALID_PAYLOAD["name"]
        assert data["text"] == VALID_PAYLOAD["text"]
        assert data["rating"] == VALID_PAYLOAD["rating"]

    def test_new_review_is_approved_by_default(self, client):
        data = client.post("/reviews", json=VALID_PAYLOAD).json()
        assert data["is_approved"] is True

    def test_optional_product_id_and_user_id_accepted(self, client):
        payload = {**VALID_PAYLOAD, "product_id": 42, "user_id": 7}
        data = client.post("/reviews", json=payload).json()
        assert data["product_id"] == 42
        assert data["user_id"] == 7

    def test_review_appears_in_listing_afterwards(self, client):
        client.post("/reviews", json=VALID_PAYLOAD)
        total = client.get("/reviews").json()["total"]
        assert total == 1

    # — Pydantic validation failures (missing / bad fields) ───────────────────

    def test_empty_name_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "name": ""})
        assert resp.status_code == 422

    def test_whitespace_only_name_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "name": "   "})
        assert resp.status_code == 422

    def test_empty_text_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": ""})
        assert resp.status_code == 422

    def test_rating_zero_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "rating": 0})
        assert resp.status_code == 422

    def test_rating_six_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "rating": 6})
        assert resp.status_code == 422

    def test_missing_name_returns_422(self, client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "name"}
        assert client.post("/reviews", json=payload).status_code == 422

    def test_missing_text_returns_422(self, client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "text"}
        assert client.post("/reviews", json=payload).status_code == 422

    def test_missing_rating_returns_422(self, client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "rating"}
        assert client.post("/reviews", json=payload).status_code == 422

    # — validate_review_text failures (content moderation) ────────────────────

    def test_spam_url_in_text_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "Check https://spam.ru"})
        assert resp.status_code == 422

    def test_email_in_text_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "Email me at x@y.com"})
        assert resp.status_code == 422

    def test_profanity_in_text_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "fuck this shop"})
        assert resp.status_code == 422

    def test_repeat_spam_in_text_returns_422(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "aaaaaaaaaa"})
        assert resp.status_code == 422

    def test_moderation_error_detail_is_human_readable(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "fuck"})
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert len(detail) > 5


# ══════════════════════════════════════════════════════════════════════════════
# GET /reviews/{reviewId}
# ══════════════════════════════════════════════════════════════════════════════

class TestGetReviewById:

    def test_returns_200_for_existing_review(self, client, approved_review):
        resp = client.get(f"/reviews/{approved_review.id}")
        assert resp.status_code == 200

    def test_returned_data_matches_review(self, client, approved_review):
        data = client.get(f"/reviews/{approved_review.id}").json()
        assert data["id"] == approved_review.id
        assert data["name"] == approved_review.name
        assert data["rating"] == approved_review.rating
        assert data["is_approved"] == approved_review.is_approved

    def test_returns_404_for_nonexistent_id(self, client):
        resp = client.get("/reviews/99999")
        assert resp.status_code == 404

    def test_404_response_has_detail(self, client):
        data = client.get("/reviews/99999").json()
        assert "detail" in data


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /reviews/{reviewId}
# ══════════════════════════════════════════════════════════════════════════════

class TestPatchReview:

    def test_approve_unapproved_review(self, client, unapproved_review):
        resp = client.patch(
            f"/reviews/{unapproved_review.id}",
            json={"is_approved": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is True

    def test_disapprove_approved_review(self, client, approved_review):
        resp = client.patch(
            f"/reviews/{approved_review.id}",
            json={"is_approved": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is False

    def test_response_preserves_other_fields(self, client, approved_review):
        data = client.patch(
            f"/reviews/{approved_review.id}",
            json={"is_approved": False},
        ).json()
        assert data["id"] == approved_review.id
        assert data["name"] == approved_review.name
        assert data["rating"] == approved_review.rating

    def test_empty_body_returns_422(self, client, approved_review):
        resp = client.patch(f"/reviews/{approved_review.id}", json={})
        assert resp.status_code == 422

    def test_extra_field_returns_422(self, client, approved_review):
        resp = client.patch(
            f"/reviews/{approved_review.id}",
            json={"is_approved": True, "name": "hacker"},
        )
        assert resp.status_code == 422

    def test_nonexistent_review_returns_404(self, client):
        resp = client.patch("/reviews/99999", json={"is_approved": True})
        assert resp.status_code == 404

    def test_change_is_persisted(self, client, unapproved_review):
        client.patch(f"/reviews/{unapproved_review.id}", json={"is_approved": True})
        data = client.get(f"/reviews/{unapproved_review.id}").json()
        assert data["is_approved"] is True


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /reviews/{reviewId}
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteReview:

    def test_returns_204(self, client, approved_review):
        resp = client.delete(f"/reviews/{approved_review.id}")
        assert resp.status_code == 204

    def test_response_body_is_empty(self, client, approved_review):
        resp = client.delete(f"/reviews/{approved_review.id}")
        assert resp.content == b""

    def test_review_is_gone_after_deletion(self, client, approved_review):
        review_id = approved_review.id
        client.delete(f"/reviews/{review_id}")
        assert client.get(f"/reviews/{review_id}").status_code == 404

    def test_review_absent_from_listing_after_deletion(self, client, approved_review):
        review_id = approved_review.id
        client.delete(f"/reviews/{review_id}")
        ids = [r["id"] for r in client.get("/reviews").json()["items"]]
        assert review_id not in ids

    def test_nonexistent_review_returns_404(self, client):
        assert client.delete("/reviews/99999").status_code == 404

    def test_double_delete_second_returns_404(self, client, approved_review):
        url = f"/reviews/{approved_review.id}"
        client.delete(url)
        assert client.delete(url).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# GET /ratings/summary
# ══════════════════════════════════════════════════════════════════════════════

class TestRatingSummary:

    def test_no_reviews_returns_200(self, client):
        assert client.get("/ratings/summary").status_code == 200

    def test_no_reviews_has_null_average_and_zero_count(self, client):
        data = client.get("/ratings/summary").json()
        assert data["average"] is None
        assert data["count"] == 0

    def test_approved_reviews_are_counted_by_default(self, client, db):
        crud.create_review(db, make_review(product_id=None, rating=4), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=2), is_approved=True)
        data = client.get("/ratings/summary").json()
        assert data["count"] == 2
        assert data["average"] == 3.0

    def test_unapproved_reviews_excluded_by_default(self, client, db):
        crud.create_review(db, make_review(product_id=None, rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=1), is_approved=False)
        data = client.get("/ratings/summary").json()
        assert data["count"] == 1
        assert data["average"] == 5.0

    def test_approved_only_false_includes_unapproved(self, client, db):
        crud.create_review(db, make_review(product_id=None, rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=None, rating=1), is_approved=False)
        data = client.get("/ratings/summary?approved_only=false").json()
        assert data["count"] == 2

    def test_product_id_filter_returns_product_average(self, client, db):
        crud.create_review(db, make_review(product_id=10, rating=5), is_approved=True)
        crud.create_review(db, make_review(product_id=10, rating=3), is_approved=True)
        crud.create_review(db, make_review(product_id=20, rating=1), is_approved=True)
        data = client.get("/ratings/summary?product_id=10").json()
        assert data["count"] == 2
        assert data["average"] == 4.0
        assert data["product_id"] == 10

    def test_nonexistent_product_id_returns_null_average(self, client, approved_review):
        data = client.get("/ratings/summary?product_id=999").json()
        assert data["average"] is None
        assert data["count"] == 0

    def test_product_id_is_echoed_in_response(self, client, db):
        crud.create_review(db, make_review(product_id=7, rating=4), is_approved=True)
        data = client.get("/ratings/summary?product_id=7").json()
        assert data["product_id"] == 7


# ══════════════════════════════════════════════════════════════════════════════
# Edge cases: path parameters, combined filters, extra body fields
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    # — Path parameter type validation ─────────────────────────────────────────

    def test_non_integer_review_id_returns_422(self, client):
        # FastAPI validates path params: "abc" is not a valid int
        assert client.get("/reviews/abc").status_code == 422

    def test_non_integer_patch_id_returns_422(self, client):
        assert client.patch("/reviews/abc", json={"is_approved": True}).status_code == 422

    def test_non_integer_delete_id_returns_422(self, client):
        assert client.delete("/reviews/abc").status_code == 422

    # — Combined query filters ─────────────────────────────────────────────────

    def test_combined_product_id_and_approved_only_filter(self, client, five_reviews):
        # five_reviews: product_id=1 has ratings 5,4,3 all approved
        #               product_id=2 has ratings 2,1 NOT approved
        data = client.get("/reviews?product_id=1&approved_only=true").json()
        assert data["total"] == 3
        assert all(r["product_id"] == 1 for r in data["items"])
        assert all(r["is_approved"] for r in data["items"])

    def test_combined_product_id_and_min_rating_filter(self, client, five_reviews):
        # product_id=1, min_rating=4 → only ratings 5 and 4 → 2 results
        data = client.get("/reviews?product_id=1&min_rating=4").json()
        assert data["total"] == 2
        assert all(r["rating"] >= 4 for r in data["items"])

    def test_combined_approved_only_and_rating_range(self, client, five_reviews):
        # approved_only=true, min_rating=3, max_rating=5 → ratings 5,4,3 from product_id=1
        data = client.get("/reviews?approved_only=true&min_rating=3&max_rating=5").json()
        assert data["total"] == 3
        assert all(r["is_approved"] for r in data["items"])
        assert all(3 <= r["rating"] <= 5 for r in data["items"])

    def test_all_filters_combined(self, client, five_reviews):
        # product_id=1, approved=true, rating 4-5, limit=1, offset=0
        data = client.get(
            "/reviews?product_id=1&approved_only=true&min_rating=4&max_rating=5&limit=1"
        ).json()
        assert len(data["items"]) == 1
        r = data["items"][0]
        assert r["product_id"] == 1
        assert r["is_approved"] is True
        assert 4 <= r["rating"] <= 5

    # — Extra fields in POST body ──────────────────────────────────────────────

    def test_extra_fields_in_post_body_are_ignored(self, client):
        # ReviewCreate does not have extra="forbid", so extra fields are silently dropped
        payload = {**VALID_PAYLOAD, "unknown_field": "should be ignored", "hacked": True}
        resp = client.post("/reviews", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "unknown_field" not in data
        assert "hacked" not in data

    # — Rating boundary values pass validation ─────────────────────────────────

    def test_min_rating_1_is_valid_query_param(self, client, five_reviews):
        resp = client.get("/reviews?min_rating=1")
        assert resp.status_code == 200

    def test_max_rating_5_is_valid_query_param(self, client, five_reviews):
        resp = client.get("/reviews?max_rating=5")
        assert resp.status_code == 200

    def test_rating_1_in_post_is_accepted(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "rating": 1})
        assert resp.status_code == 201

    def test_rating_5_in_post_is_accepted(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "rating": 5})
        assert resp.status_code == 201
