"""
Servicio ligero de Reconocimiento de Voz (STT) basado exclusivamente en `whisper-base` (~140MB).
Soporta archivos adjuntos REST y ventanas de audio en tiempo real por WebSockets.
"""

import time
import wave
from pathlib import Path
from faster_whisper import WhisperModel

from app.core.config import settings
from app.services.temp_storage import allocate_temp_path, remove_temp_file

_whisper_instance: WhisperModel | None = None


def get_whisper_model() -> WhisperModel:
    """Carga perezosa (Singleton) del modelo ligero whisper-base en CPU (int8)."""
    global _whisper_model_loaded
    global _whisper_instance
    if _whisper_instance is None:
        whisper_cache = settings.MODEL_CACHE_DIR / "whisper"
        whisper_cache.mkdir(parents=True, exist_ok=True)
        _whisper_instance = WhisperModel(
            settings.STT_MODEL_NAME,
            device=settings.STT_DEVICE,
            compute_type=settings.STT_COMPUTE_TYPE,
            download_root=str(whisper_cache),
        )
    return _whisper_instance


def transcribe_audio_file(
    audio_path: Path,
    language: str | None = None,
    beam_size: int = 5,
) -> dict:
    """Transcribe un archivo de audio usando exclusivamente whisper-base."""
    start = time.perf_counter()
    model = get_whisper_model()
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=beam_size,
        vad_filter=True,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    return {
        "text": text,
        "language": info.language or (language or "es"),
        "duration_sec": round(float(info.duration or 0.0), 2),
        "processing_time_ms": elapsed_ms,
        "model": f"whisper-{settings.STT_MODEL_NAME}",
    }


def transcribe_pcm16_bytes(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    language: str | None = "es",
    is_partial: bool = True,
) -> dict:
    """
    Envuelve bytes PCM 16-bit mono en un contenedor WAV temporal dentro de /tmp/hakuyomi_audio,
    ejecuta inferencia con whisper-base y elimina el archivo inmediatamente.
    """
    temp_wav = allocate_temp_path(suffix=".wav", prefix="ws_chunk_")
    try:
        with wave.open(str(temp_wav), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM = 2 bytes
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        return transcribe_audio_file(
            temp_wav,
            language=language,
            beam_size=1 if is_partial else 5,
        )
    finally:
        remove_temp_file(temp_wav)
