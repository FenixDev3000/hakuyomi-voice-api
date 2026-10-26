"""Esquemas Pydantic estandarizados para validación de payloads en STT (Upload/Stream) y TTS."""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

ALLOWED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".opus",
    ".m4a",
    ".flac",
    ".webm",
    ".aac",
    ".wma",
    ".mp4",
    ".mpeg",
    ".mpga",
}

ALLOWED_AUDIO_MIME_PREFIXES = ("audio/", "video/")
ALLOWED_EXACT_MIMES = {
    "application/ogg",
    "application/x-ogg",
    "application/octet-stream",
}


class STTUploadPayload(BaseModel):
    """Validación Pydantic del payload y metadatos de subida en POST /api/v1/stt/upload."""

    filename: str = Field(..., min_length=1, max_length=255, description="Nombre del archivo adjunto")
    content_type: str = Field(
        default="audio/wav",
        description="MIME type del archivo de audio (.mp3, .wav, .ogg, .m4a, .flac, .webm, etc.)",
    )
    file_size_bytes: int | None = Field(
        default=None,
        gt=0,
        le=settings.max_upload_size_bytes,
        description="Tamaño del archivo en bytes (máximo 10 MB)",
    )
    language: str | None = Field(
        default="es",
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="Código ISO de idioma (ej. es, en)",
    )

    @field_validator("filename")
    @classmethod
    def validate_audio_extension(cls, value: str) -> str:
        ext = Path(value).suffix.lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise ValueError(
                f"Extensión '{ext}' no permitida. Formatos soportados: "
                f"{', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
            )
        return value

    @field_validator("content_type")
    @classmethod
    def validate_audio_mime(cls, value: str) -> str:
        mime = (value or "application/octet-stream").split(";")[0].strip().lower()
        if not (
            mime.startswith(ALLOWED_AUDIO_MIME_PREFIXES) or mime in ALLOWED_EXACT_MIMES
        ):
            raise ValueError(
                f"Content-Type '{mime}' no soportado para archivos de audio."
            )
        return mime


class STTUploadResponse(BaseModel):
    """Respuesta estandarizada del endpoint POST /api/v1/stt/upload."""

    text: str
    filename: str
    file_size_bytes: int
    language: str
    duration_sec: float
    processing_time_ms: float
    model: str = "whisper-base"


class STTStreamControlPayload(BaseModel):
    """Validación Pydantic de mensajes JSON de control en ws://.../api/v1/stt/stream."""

    action: Literal["config", "flush", "ping", "stop"] = Field(
        ..., description="Acción de control del stream WebSocket"
    )
    language: str = Field(
        default="es",
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="Idioma para la transcripción iterativa",
    )
    sample_rate: int = Field(
        default=16000,
        ge=8000,
        le=48000,
        description="Frecuencia de muestreo del stream PCM en Hz",
    )


class STTStreamChunkPayload(BaseModel):
    """Validación Pydantic de cada fragmento binario recibido por WebSocket."""

    chunk_size_bytes: int = Field(
        ...,
        gt=0,
        le=settings.max_upload_size_bytes,
        description="Tamaño del fragmento de audio en bytes (máx. 10 MB)",
    )


class STTStreamEventResponse(BaseModel):
    """Evento de transcripción iterativa emitido por ws://.../api/v1/stt/stream."""

    type: Literal[
        "session_started",
        "config_updated",
        "partial_transcript",
        "final_transcript",
        "pong",
        "error",
    ]
    session_id: str
    iteration: int = 0
    text: str = ""
    is_final: bool = False
    language: str = "es"
    duration_sec: float = 0.0
    processing_time_ms: float = 0.0
    model: str = "whisper-base"
    detail: str | None = None


class TTSRequest(BaseModel):
    """Payload validado para síntesis de voz (POST /api/v1/tts)."""

    text: str = Field(..., min_length=1, max_length=2000, description="Texto a sintetizar")
    voice: str | None = Field(
        default=None,
        description="Modelo de voz ligero Piper/VITS (por defecto es_MX-ald-medium)",
    )
