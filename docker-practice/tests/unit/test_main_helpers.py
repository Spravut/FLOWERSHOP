"""
Unit tests for private helper functions in app/main.py.

These functions are small, pure (or nearly pure) utilities that the application
uses internally. Testing them directly gives precise feedback when any one of
them breaks, rather than relying on a chain of integration tests to surface
the failure.

Functions under test:
  _utc_iso()           – returns current UTC time as an ISO-8601 string
  _client_ip(request)  – extracts the real client IP from a request
  _append_json_line()  – appends one JSON object per line to a file
  _json_or_text()      – safely parses bytes as JSON or falls back to text
  seed_demo_data()     – inserts demo reviews if the DB is empty
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app import crud, models
from app.main import (
    _append_json_line,
    _client_ip,
    _json_or_text,
    _utc_iso,
    seed_demo_data,
)
from tests.helpers import make_review


# ══════════════════════════════════════════════════════════════════════════════
# _utc_iso
# ══════════════════════════════════════════════════════════════════════════════

class TestUtcIso:
    def test_returns_string(self):
        assert isinstance(_utc_iso(), str)

    def test_contains_utc_offset(self):
        # isoformat with timezone.utc produces "+00:00"
        assert "+00:00" in _utc_iso()

    def test_is_parseable_as_iso_datetime(self):
        result = _utc_iso()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_has_seconds_precision(self):
        result = _utc_iso()
        # timespec="seconds" means no microseconds portion
        parsed = datetime.fromisoformat(result)
        assert parsed.microsecond == 0

    def test_is_recent(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        result = datetime.fromisoformat(_utc_iso())
        after = datetime.now(timezone.utc).replace(microsecond=0)
        assert before <= result <= after


# ══════════════════════════════════════════════════════════════════════════════
# _client_ip
# ══════════════════════════════════════════════════════════════════════════════

def _mock_request(forwarded: str | None = None, client_host: str | None = None):
    """Build a minimal mock Request with controllable headers and client."""
    req = MagicMock()
    req.headers.get.return_value = forwarded
    if client_host is not None:
        req.client = MagicMock()
        req.client.host = client_host
    else:
        req.client = None
    return req


class TestClientIp:
    def test_single_ip_in_x_forwarded_for(self):
        req = _mock_request(forwarded="1.2.3.4")
        assert _client_ip(req) == "1.2.3.4"

    def test_first_ip_taken_from_comma_list(self):
        # Proxy chains add multiple IPs; rightmost = proxy, leftmost = client
        req = _mock_request(forwarded="1.2.3.4, 5.6.7.8, 9.10.11.12")
        assert _client_ip(req) == "1.2.3.4"

    def test_whitespace_stripped_from_forwarded_ip(self):
        req = _mock_request(forwarded="  1.2.3.4  , 5.6.7.8")
        assert _client_ip(req) == "1.2.3.4"

    def test_falls_back_to_client_host(self):
        req = _mock_request(forwarded=None, client_host="192.168.0.100")
        assert _client_ip(req) == "192.168.0.100"

    def test_returns_unknown_when_no_info(self):
        req = _mock_request(forwarded=None, client_host=None)
        assert _client_ip(req) == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# _append_json_line
# ══════════════════════════════════════════════════════════════════════════════

class TestAppendJsonLine:
    def test_creates_file(self, tmp_path):
        f = tmp_path / "audit.log"
        _append_json_line(f, {"event": "test"})
        assert f.exists()

    def test_written_content_is_valid_json(self, tmp_path):
        f = tmp_path / "audit.log"
        payload = {"method": "POST", "path": "/reviews", "status_code": 201}
        _append_json_line(f, payload)
        line = f.read_text(encoding="utf-8").strip()
        assert json.loads(line) == payload

    def test_creates_parent_directory_if_missing(self, tmp_path):
        f = tmp_path / "deep" / "nested" / "audit.log"
        _append_json_line(f, {"x": 1})
        assert f.exists()

    def test_each_call_appends_a_new_line(self, tmp_path):
        f = tmp_path / "audit.log"
        _append_json_line(f, {"n": 1})
        _append_json_line(f, {"n": 2})
        _append_json_line(f, {"n": 3})
        lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3
        assert json.loads(lines[0]) == {"n": 1}
        assert json.loads(lines[2]) == {"n": 3}

    def test_unicode_preserved_without_escaping(self, tmp_path):
        f = tmp_path / "audit.log"
        _append_json_line(f, {"text": "Привет мир 🌸"})
        content = f.read_text(encoding="utf-8")
        # ensure_ascii=False means Cyrillic is stored as-is, not as \uXXXX
        assert "Привет мир" in content
        parsed = json.loads(content.strip())
        assert parsed["text"] == "Привет мир 🌸"

    def test_second_call_does_not_overwrite(self, tmp_path):
        f = tmp_path / "audit.log"
        _append_json_line(f, {"first": True})
        _append_json_line(f, {"second": True})
        content = f.read_text(encoding="utf-8")
        assert "first" in content
        assert "second" in content


# ══════════════════════════════════════════════════════════════════════════════
# _json_or_text
# ══════════════════════════════════════════════════════════════════════════════

class TestJsonOrText:
    def test_empty_bytes_returns_none(self):
        assert _json_or_text(b"") is None

    def test_valid_json_object_parsed(self):
        result = _json_or_text(b'{"name": "Alice", "rating": 5}')
        assert result == {"name": "Alice", "rating": 5}

    def test_valid_json_array_parsed(self):
        result = _json_or_text(b"[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_valid_json_number_parsed(self):
        assert _json_or_text(b"42") == 42

    def test_valid_json_string_literal_parsed(self):
        assert _json_or_text(b'"hello"') == "hello"

    def test_invalid_json_falls_back_to_text(self):
        result = _json_or_text(b"not valid json at all")
        assert isinstance(result, str)
        assert result == "not valid json at all"

    def test_partial_json_falls_back_to_text(self):
        result = _json_or_text(b"{malformed")
        assert isinstance(result, str)

    def test_unicode_text_preserved(self):
        russian = "Хороший магазин, советую!"
        result = _json_or_text(russian.encode("utf-8"))
        assert result == russian

    def test_json_with_unicode_values_parsed(self):
        payload = json.dumps({"name": "Анна"}, ensure_ascii=False).encode("utf-8")
        result = _json_or_text(payload)
        assert result == {"name": "Анна"}


# ══════════════════════════════════════════════════════════════════════════════
# seed_demo_data
# ══════════════════════════════════════════════════════════════════════════════

class TestSeedDemoData:
    def test_inserts_three_reviews_into_empty_db(self, engine, db):
        # Patch SessionLocal so seed_demo_data uses our test engine.
        TestSession = sessionmaker(bind=engine)
        with patch("app.main.SessionLocal", TestSession):
            seed_demo_data()
        db.expire_all()
        reviews = db.query(models.Review).all()
        assert len(reviews) == 3

    def test_seeded_reviews_have_expected_names(self, engine, db):
        TestSession = sessionmaker(bind=engine)
        with patch("app.main.SessionLocal", TestSession):
            seed_demo_data()
        db.expire_all()
        names = {r.name for r in db.query(models.Review).all()}
        assert names == {"Anna", "Petr", "Maria"}

    def test_skips_seeding_if_reviews_already_exist(self, engine, db):
        # Pre-insert one review so the DB is not empty.
        crud.create_review(db, make_review(name="Existing"), is_approved=True)
        TestSession = sessionmaker(bind=engine)
        with patch("app.main.SessionLocal", TestSession):
            seed_demo_data()
        db.expire_all()
        # Still only 1 review – seeding was skipped.
        assert db.query(models.Review).count() == 1

    def test_calling_twice_does_not_duplicate_data(self, engine, db):
        TestSession = sessionmaker(bind=engine)
        with patch("app.main.SessionLocal", TestSession):
            seed_demo_data()
            seed_demo_data()
        db.expire_all()
        assert db.query(models.Review).count() == 3
