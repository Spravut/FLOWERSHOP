from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text as sa_text,
)

from app.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        Index("ix_reviews_product_id", "product_id"),
        Index("ix_reviews_is_approved", "is_approved"),
        Index("ix_reviews_rating", "rating"),
        Index("ix_reviews_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    name = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)
    is_approved = Column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
