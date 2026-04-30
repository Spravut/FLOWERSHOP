"""
Shared pytest fixtures for the reviews-microservice test suite.

Architecture:
  - Every test function gets a fresh in-memory SQLite database (tables created
    from scratch, dropped on teardown) so tests are fully isolated.
  - The FastAPI TestClient is wired to the same SQLAlchemy session as the
    ``db`` fixture via dependency override, so data written in fixtures is
    visible to the API – no real Postgres connection is needed.
  - seed_demo_data() is patched out during TestClient startup to avoid any
    attempt to reach the real Postgres instance.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud
from app.database import Base, get_db
from app.main import app
from tests.helpers import make_review

TEST_DATABASE_URL = "sqlite:///:memory:"


# ── Database ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def engine():
    """Fresh in-memory SQLite engine with all tables created."""
    eng = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Single SQLAlchemy session for one test function."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()


# ── HTTP client ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(db):
    """
    FastAPI TestClient whose get_db dependency returns the test ``db`` session.
    seed_demo_data is patched so startup doesn't try to reach real Postgres.
    """
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.seed_demo_data"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


# ── Pre-built review fixtures ──────────────────────────────────────────────────

@pytest.fixture()
def approved_review(db):
    """One approved review (product_id=1, rating=5) in the test DB."""
    return crud.create_review(
        db,
        make_review(product_id=1, user_id=10, name="Anna", rating=5),
        is_approved=True,
    )


@pytest.fixture()
def unapproved_review(db):
    """One unapproved review (product_id=1, rating=3) in the test DB."""
    return crud.create_review(
        db,
        make_review(product_id=1, user_id=11, name="Pending User", rating=3),
        is_approved=False,
    )


@pytest.fixture()
def five_reviews(db):
    """
    5 reviews with varied product_id, rating, approval status – useful for
    filter and pagination tests.

    Breakdown:
      r0: product_id=1, rating=5, approved
      r1: product_id=1, rating=4, approved
      r2: product_id=1, rating=3, approved
      r3: product_id=2, rating=2, NOT approved
      r4: product_id=2, rating=1, NOT approved
    """
    specs = [
        dict(product_id=1, rating=5, is_approved=True),
        dict(product_id=1, rating=4, is_approved=True),
        dict(product_id=1, rating=3, is_approved=True),
        dict(product_id=2, rating=2, is_approved=False),
        dict(product_id=2, rating=1, is_approved=False),
    ]
    reviews = []
    for i, spec in enumerate(specs):
        approved = spec.pop("is_approved")
        r = crud.create_review(
            db,
            make_review(name=f"User{i}", **spec),
            is_approved=approved,
        )
        reviews.append(r)
    return reviews
