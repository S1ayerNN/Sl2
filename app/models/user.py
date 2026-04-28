import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Auth identifiers
    telegram_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    google_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True, nullable=True
    )

    # Basic profile (required at registration)
    name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(20))  # male, female, other
    zodiac_sign: Mapped[str] = mapped_column(String(20))  # auto-calculated

    # Extended profile (optional, progressive collection)
    birth_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    birth_place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Interests / preferences (JSON array)
    interests: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    # Example: {"love": true, "career": true, "health": false, "finance": true}

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(
        String(20), default="free"
    )  # free, premium
    subscription_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
            "name": 15,
            "birth_date": 15,
            "gender": 10,
            "birth_time": 15,
            "birth_place": 15,
            "email": 10,
            "interests": 20,
        }
        score = 0
        for field, weight in fields.items():
            value = getattr(self, field, None)
            if value is not None and value != "" and value != {}:
                score += weight
        return score
