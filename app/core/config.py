"""Configuración centralizada de hakuyomi-voice-api."""

from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "hakuyomi-voice-api"
    APP_ENV: str = "production"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "info"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # PostgreSQL
    DATABASE_URL: str = (
        "postgresql+asyncpg://hakuyomi_user:changeme_secure_password_2026"
        "@db:5432/hakuyomi_voice_db"
    )

    # Modelos ligeros exclusivos (< 10 GB total)
    STT_MODEL_NAME: str = "base"
    STT_DEVICE: str = "cpu"
    STT_COMPUTE_TYPE: str = "int8"
    TTS_ENGINE: str = "piper-tts"
    PIPER_VOICE_MODEL: str = "es_MX-ald-medium"
    PIPER_SAMPLE_RATE: int = 22050
    MODEL_CACHE_DIR: Path = Path("/app/models")

    # Almacenamiento temporal de audio adjunto y WebSockets
    TEMP_AUDIO_DIR: Path = Path("/tmp/hakuyomi_audio")
    MAX_UPLOAD_SIZE_MB: int = 25
    TEMP_FILE_TTL_SECONDS: int = 300
    WS_MAX_BUFFER_BYTES: int = 10 * 1024 * 1024  # 10 MB
    WS_CHUNK_DURATION_MS: int = 2000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("STT_MODEL_NAME")
    @classmethod
    def enforce_lightweight_whisper(cls, value: str) -> str:
        allowed = {"tiny", "base"}
        if value not in allowed:
            raise ValueError(
                f"El modelo STT '{value}' excede el presupuesto ligero. "
                "Solo se permite 'base' (~140MB) o 'tiny'."
            )
        return value

    @field_validator("TTS_ENGINE")
    @classmethod
    def enforce_lightweight_tts(cls, value: str) -> str:
        allowed = {"piper-tts", "vits"}
        if value not in allowed:
            raise ValueError(
                f"El motor TTS '{value}' no está permitido. "
                "Use exclusivamente 'piper-tts' o 'vits' (~150MB)."
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
