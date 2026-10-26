"""
Servicio ligero de Texto a Voz (TTS) basado exclusivamente en `piper-tts` / VITS (~150MB).
Genera archivos WAV en el almacenamiento temporal acotado (/tmp/hakuyomi_audio).
"""

import time
import wave
from pathlib import Path
from piper.voice import PiperVoice

from app.core.config import settings
from app.services.temp_storage import allocate_temp_path, remove_temp_file

_piper_voice_instance: PiperVoice | None = None


def get_piper_voice() -> PiperVoice:
    """Carga perezosa (Singleton) del modelo ligero Piper/VITS en ONNX."""
    global _piper_voice_instance
    if _piper_voice_instance is None:
        piper_dir = settings.MODEL_CACHE_DIR / "piper"
        model_path = piper_dir / f"{settings.PIPER_VOICE_MODEL}.onnx"
        config_path = piper_dir / f"{settings.PIPER_VOICE_MODEL}.onnx.json"
        if not model_path.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo ligero Piper/VITS en {model_path}. "
                "Ejecute `python scripts/download_models.py`."
            )
        _piper_voice_instance = PiperVoice.load(
            str(model_path),
            config_path=str(config_path) if config_path.exists() else None,
            use_cuda=False,
        )
    return _piper_voice_instance


def synthesize_text_to_wav(text: str) -> tuple[Path, float]:
    """
    Sintetiza texto a un archivo WAV temporal usando piper-tts (VITS).
    Retorna la ruta del archivo temporal y el tiempo de procesamiento en ms.
    """
    start = time.perf_counter()
    output_path = allocate_temp_path(suffix=".wav", prefix="tts_out_")

    try:
        voice = get_piper_voice()
        with wave.open(str(output_path), "wb") as wav_file:
            voice.synthesize(text, wav_file)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return output_path, elapsed_ms
    except Exception:
        remove_temp_file(output_path)
        raise
