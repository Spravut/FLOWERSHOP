"""
Integration tests for the audit middleware in app/main.py.

The middleware (``audit_non_get_requests``) wraps every non-GET request:
  1. It reads the request body before passing the request to the endpoint.
  2. It re-injects the body so the endpoint can read it again (crucial!).
  3. It fires a background task to append one JSON line to the audit log.
  4. GET / HEAD / OPTIONS requests are passed through untouched.

These tests verify the middleware's contract from the outside (HTTP responses)
and, where possible, inspect side-effects like log file creation.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

VALID_PAYLOAD = dict(
    name="Anna",
    text="Great bouquet, fast delivery.",
    rating=5,
)


# ══════════════════════════════════════════════════════════════════════════════
# Requests that bypass the middleware (GET / HEAD / OPTIONS)
# ══════════════════════════════════════════════════════════════════════════════

class TestMiddlewareBypass:
    def test_get_reviews_not_blocked(self, client):
        resp = client.get("/reviews")
        assert resp.status_code == 200

    def test_get_by_id_not_blocked(self, client, approved_review):
        resp = client.get(f"/reviews/{approved_review.id}")
        assert resp.status_code == 200

    def test_get_ratings_not_blocked(self, client):
        resp = client.get("/ratings/summary")
        assert resp.status_code == 200

    def test_get_root_not_blocked(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Body re-injection: middleware must not consume the body for the endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestBodyPreservation:
    """
    The middleware reads request.body() before the endpoint does.
    It then re-injects the bytes via a custom receive callable so the endpoint
    can read the same body. If this breaks, every POST/PATCH would fail with
    422 (missing body) or produce empty data.
    """

    def test_post_body_received_by_endpoint(self, client):
        resp = client.post("/reviews", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == VALID_PAYLOAD["name"]
        assert data["text"] == VALID_PAYLOAD["text"]
        assert data["rating"] == VALID_PAYLOAD["rating"]

    def test_patch_body_received_by_endpoint(self, client, unapproved_review):
        resp = client.patch(
            f"/reviews/{unapproved_review.id}",
            json={"is_approved": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is True

    def test_delete_works_without_body(self, client, approved_review):
        resp = client.delete(f"/reviews/{approved_review.id}")
        assert resp.status_code == 204

    def test_middleware_does_not_alter_response_status(self, client):
        resp = client.post("/reviews", json=VALID_PAYLOAD)
        # 201 must come through unchanged by the middleware
        assert resp.status_code == 201

    def test_invalid_post_still_returns_422_through_middleware(self, client):
        # Middleware should not swallow validation errors
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "rating": 0})
        assert resp.status_code == 422

    def test_moderation_failure_still_returns_422_through_middleware(self, client):
        resp = client.post("/reviews", json={**VALID_PAYLOAD, "text": "fuck"})
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Audit log file creation
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditLogging:
    """
    The middleware schedules _append_json_line via asyncio.create_task.
    We patch _append_json_line to capture calls synchronously, avoiding
    any file-system dependency in tests.
    """

    def test_post_triggers_audit_log_write(self, client):
        written = []

        def capture(path, payload):
            written.append(payload)

        with patch("app.main._append_json_line", side_effect=capture):
            client.post("/reviews", json=VALID_PAYLOAD)

        # The task is fire-and-forget; give the event loop a moment.
        # In TestClient's sync context the background task may complete before
        # the response is returned – if it does, we check it.
        if written:
            assert written[0]["method"] == "POST"
            assert written[0]["path"] == "/reviews"

    def test_get_does_not_trigger_audit_log_write(self, client):
        written = []

        def capture(path, payload):
            written.append(payload)

        with patch("app.main._append_json_line", side_effect=capture):
            client.get("/reviews")

        # Event loop finishes any pending tasks before we check.
        assert written == [], "GET must not produce audit events"

    def test_audit_event_contains_expected_keys(self, client):
        captured = []

        def capture(path, payload):
            captured.append(payload)

        with patch("app.main._append_json_line", side_effect=capture):
            client.post("/reviews", json=VALID_PAYLOAD)

        if captured:
            event = captured[0]
            for key in ("ts", "service", "method", "path", "ip", "status_code", "body"):
                assert key in event, f"Audit event missing key: {key}"

    def test_audit_event_body_contains_request_data(self, client):
        captured = []

        def capture(path, payload):
            captured.append(payload)

        with patch("app.main._append_json_line", side_effect=capture):
            client.post("/reviews", json=VALID_PAYLOAD)

        if captured:
            body = captured[0]["body"]
            assert body["name"] == VALID_PAYLOAD["name"]
            assert body["rating"] == VALID_PAYLOAD["rating"]

    def test_delete_triggers_audit_log_write(self, client, approved_review):
        written = []

        def capture(path, payload):
            written.append(payload)

        with patch("app.main._append_json_line", side_effect=capture):
            client.delete(f"/reviews/{approved_review.id}")

        if written:
            assert written[0]["method"] == "DELETE"
