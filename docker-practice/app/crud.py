from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas


def get_reviews(
    db: Session,
    *,
    limit: int,
    offset: int,
    approved_only: Optional[bool],
    product_id: Optional[int],
    min_rating: Optional[int],
    max_rating: Optional[int],
    sort: str,
) -> Tuple[list[models.Review], int]:
    query = db.query(models.Review)

    if approved_only is not None:
        query = query.filter(models.Review.is_approved == approved_only)
    if product_id is not None:
        query = query.filter(models.Review.product_id == product_id)
    if min_rating is not None:
        query = query.filter(models.Review.rating >= min_rating)
    if max_rating is not None:
        query = query.filter(models.Review.rating <= max_rating)

    if sort == "created_at_desc":
        query = query.order_by(models.Review.created_at.desc())
    elif sort == "created_at_asc":
        query = query.order_by(models.Review.created_at.asc())
    elif sort == "rating_desc":
        query = query.order_by(models.Review.rating.desc())
    elif sort == "rating_asc":
        query = query.order_by(models.Review.rating.asc())

    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return items, total


def create_review(db: Session, review: schemas.ReviewCreate, *, is_approved: bool = True) -> models.Review:
    """is_approved по умолчанию True — после прохождения автоматических проверок в API."""
    db_review = models.Review(**review.model_dump(), is_approved=is_approved)
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


def get_review(db: Session, review_id: int) -> Optional[models.Review]:
    return db.get(models.Review, review_id)


def update_review(
    db: Session, db_review: models.Review, review_update: schemas.ReviewUpdate
) -> models.Review:
    update_data = review_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_review, field, value)

    db.commit()
    db.refresh(db_review)
    return db_review


def delete_review(db: Session, db_review: models.Review) -> None:
    db.delete(db_review)
    db.commit()


def get_rating_summary(
    db: Session, *, product_id: Optional[int], approved_only: bool
) -> tuple[Optional[float], int]:
    query = db.query(models.Review)

    if approved_only:
        query = query.filter(models.Review.is_approved.is_(True))

    if product_id is None:
        query = query.filter(models.Review.product_id.is_(None))
    else:
        query = query.filter(models.Review.product_id == product_id)

    count = query.count()
    if count == 0:
        return None, 0

    average = query.with_entities(func.avg(models.Review.rating)).scalar()
    return round(float(average), 2), count
