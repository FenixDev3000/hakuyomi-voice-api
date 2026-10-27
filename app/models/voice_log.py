"""Modelo ORM para registrar metadatos de transcripción y síntesis de voz."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoiceLog(Base):
    __tablename__ = "voice_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    audio_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
