"""Esquemas Pydantic para peticiones y respuestas de STT y TTS."""

from pydantic import BaseModel, Field


class STTResponse(BaseModel):
    text: str
    language: str
    duration_sec: float
    processing_time_ms: float
    model: str = "whisper-base"


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Texto a sintetizar")
    voice: str | None = Field(
        default=None,
        description="Modelo de voz ligero Piper/VITS (por defecto es_MX-ald-medium)",
    )


class WSTranscriptEvent(BaseModel):
    type: str
    session_id: str
    text: str = ""
    is_final: bool = False
    model: str = "whisper-base"
