import uuid
from datetime import date, datetime, time, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# Predefined interest categories - users can ONLY select from this list
class InterestCategory(str, PyEnum):
    LOVE = "love"
    CAREER = "career"
    HEALTH = "health"
    FINANCE = "finance"
    FAMILY = "family"
    EDUCATION = "education"
    TRAVEL = "travel"
    CREATIVITY = "creativity"


# Predefined gender options
class Gender(str, PyEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


# Family member relationship types
class FamilyRelation(str, PyEnum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    PARTNER = "partner"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # External auth provider IDs only (NO passwords, NO auth tokens stored)
    # These are opaque identifiers from providers, not sensitive on their own
    telegram_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    google_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True, nullable=True
    )

    # PII fields - stored ENCRYPTED (encrypt before write, decrypt after read)
    # Use app.core.crypto.encrypt_pii() / decrypt_pii()
    name_encrypted: Mapped[str] = mapped_column(String(500))  # Encrypted name
    email_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    birth_place_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Hashed email for lookups (one-way hash, cannot be reversed)
    email_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )

    # Non-PII fields (stored as-is, needed for zodiac calculations)
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    gender: Mapped[str] = mapped_column(String(20))  # Gender enum value
    zodiac_sign: Mapped[str] = mapped_column(String(20))  # Auto-calculated
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Interests - ONLY predefined categories from InterestCategory enum
    # Stored as array of enum string values
    interests: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(30)), nullable=True, default=list
    )

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(
        String(20), default="free"
    )  # "free" or "premium"
    subscription_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Ad tracking for free users
    last_ad_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ad_view_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # Profile completeness tracking
    profile_completeness: Mapped[int] = mapped_column(default=0)  # 0-100%

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    horoscopes = relationship("Horoscope", back_populates="user", lazy="selectin")
    family_members = relationship(
        "FamilyMember", back_populates="owner", lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def is_premium(self) -> bool:
        """Check if user has active premium subscription."""
        if self.subscription_tier != "premium":
            return False
        if self.subscription_expires is None:
            return False
        return self.subscription_expires > datetime.now(timezone.utc)

    def calculate_completeness(self) -> int:
        """Calculate profile completeness percentage."""
        fields = {
            "name_encrypted": 15,
            "birth_date": 15,
            "gender": 10,
            "birth_time": 15,
            "birth_place_encrypted": 15,
            "email_encrypted": 10,
            "interests": 20,
        }
        score = 0
        for field, weight in fields.items():
            value = getattr(self, field, None)
            if value is not None and value != "" and value != []:
                score += weight
        return score


class FamilyMember(Base):
    """Family member profile for generating separate horoscopes.

    Free users: 0 family members (only self)
    Premium users: up to 5 family members
    """
    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # PII - encrypted
    name_encrypted: Mapped[str] = mapped_column(String(500))

    # Non-PII
    relation: Mapped[str] = mapped_column(String(20))  # FamilyRelation enum
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    gender: Mapped[str] = mapped_column(String(20))
    zodiac_sign: Mapped[str] = mapped_column(String(20))

    # Interests
    interests: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(30)), nullable=True, default=list
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    owner = relationship("User", back_populates="family_members")
    horoscopes = relationship("Horoscope", back_populates="family_member", lazy="selectin")
