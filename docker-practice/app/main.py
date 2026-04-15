from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import SessionLocal, get_db
from app.review_validation import validate_review_text

app = FastAPI(
    title="Fleur de Reve - Reviews and Ratings",
    description="Отзывы с автопроверкой (ссылки, спам, ненормативная лексика) и сводкой рейтинга.",
    version="1.1.0",
)

LOG_DIR = Path(__file__).resolve().parent / "logs"
AUDIT_LOG_FILE = LOG_DIR / "audit.log"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _append_json_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _json_or_text(body_bytes: bytes) -> Any:
    if not body_bytes:
        return None
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except Exception:
        try:
            return body_bytes.decode("utf-8", errors="replace")
        except Exception:
            return "<unreadable>"


@app.middleware("http")
async def audit_non_get_requests(request: Request, call_next):
    method = request.method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    body_bytes = await request.body()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request._receive = receive

    response = await call_next(request)

    audit_event: dict[str, Any] = {
        "ts": _utc_iso(),
        "service": "fastapi-microservice",
        "method": method,
        "path": request.url.path,
        "query": str(request.url.query) if request.url.query else "",
        "ip": _client_ip(request),
        "status_code": getattr(response, "status_code", None),
        "body": _json_or_text(body_bytes),
    }

    asyncio.create_task(asyncio.to_thread(_append_json_line, AUDIT_LOG_FILE, audit_event))
    return response


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        if db.query(models.Review).count() > 0:
            return

        db.add_all(
            [
                models.Review(
                    product_id=42,
                    user_id=5,
                    name="Anna",
                    text="Great bouquet and fast delivery.",
                    rating=5,
                    is_approved=True,
                ),
                models.Review(
                    product_id=None,
                    user_id=None,
                    name="Petr",
                    text="Shop support helped quickly.",
                    rating=4,
                    is_approved=True,
                ),
                models.Review(
                    product_id=42,
                    user_id=None,
                    name="Maria",
                    text="Fresh roses, nice packaging.",
                    rating=5,
                    is_approved=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    seed_demo_data()


@app.get("/")
def root():
    return {
        "message": "Fleur de Reve - Reviews and Ratings API",
        "status": "running with PostgreSQL",
        "docs": "/docs",
    }


@app.get("/reviews", response_model=schemas.ReviewList)
def read_reviews(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    approved_only: Optional[bool] = None,
    product_id: Optional[int] = None,
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    sort: Literal["created_at_desc", "created_at_asc", "rating_desc", "rating_asc"] = Query(
        "created_at_desc"
    ),
    db: Session = Depends(get_db),
):
    items, total = crud.get_reviews(
        db,
        limit=limit,
        offset=offset,
        approved_only=approved_only,
        product_id=product_id,
        min_rating=min_rating,
        max_rating=max_rating,
        sort=sort,
    )
    return schemas.ReviewList(items=items, total=total)


@app.post("/reviews", response_model=schemas.ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(review: schemas.ReviewCreate, db: Session = Depends(get_db)):
    error_msg = validate_review_text(name=review.name, text=review.text)
    if error_msg:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg)
    return crud.create_review(db, review, is_approved=True)


@app.get("/reviews/{reviewId}", response_model=schemas.ReviewResponse)
def read_review(reviewId: int, db: Session = Depends(get_db)):
    db_review = crud.get_review(db, reviewId)
    if db_review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return db_review


@app.patch("/reviews/{reviewId}", response_model=schemas.ReviewResponse)
def patch_review(
    reviewId: int, review_update: schemas.ReviewUpdate, db: Session = Depends(get_db)
):
    if not review_update.model_dump(exclude_unset=True):
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    db_review = crud.get_review(db, reviewId)
    if db_review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return crud.update_review(db, db_review, review_update)


@app.delete("/reviews/{reviewId}", status_code=status.HTTP_204_NO_CONTENT)
def remove_review(reviewId: int, db: Session = Depends(get_db)):
    db_review = crud.get_review(db, reviewId)
    if db_review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    crud.delete_review(db, db_review)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/ratings/summary", response_model=schemas.RatingSummary)
def rating_summary(
    product_id: Optional[int] = None,
    approved_only: bool = True,
    db: Session = Depends(get_db),
):
    average, count = crud.get_rating_summary(
        db, product_id=product_id, approved_only=approved_only
    )
    return schemas.RatingSummary(average=average, count=count, product_id=product_id)
