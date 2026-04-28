import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Horoscope(Base):
    __tablename__ = "horoscopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Optional: horoscope can be for a family member
    family_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Horoscope content
    horoscope_date: Mapped[date] = mapped_column(Date, index=True)
    horoscope_text: Mapped[str] = mapped_column(Text)

    # AI metadata
    ai_model_used: Mapped[str] = mapped_column(String(50))  # gpt-4o-mini, gpt-4o
    prompt_used: Mapped[str] = mapped_column(Text)

    # User feedback
    feedback: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "like", "dislike", or None (no feedback yet)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Content safety check result
    safety_passed: Mapped[bool] = mapped_column(default=True)

    # Relationships
    user = relationship("User", back_populates="horoscopes")
    family_member = relationship("FamilyMember", back_populates="horoscopes")
