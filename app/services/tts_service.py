"""
Servicio ligero de Texto a Voz (TTS) basado exclusivamente en `piper-tts` / VITS.
Soporta selección dinámica de voces en el Banco de Voces:
- es_MX-cori-high (femenina)
- es_MX-claude-high (masculina)
- es_MX-ald-medium (masculina)
- es_ES-davefx-medium (masculina)
- es_ES-sharvard-medium (femenina)
Las voces 'Camila' y 'Lucas' han sido removidas.
"""

import json
import time
import urllib.request
import wave
from pathlib import Path
from piper.config import PhonemeType
from piper.voice import PiperVoice

from app.core.config import settings
from app.services.temp_storage import allocate_temp_path, remove_temp_file

# Registro oficial de identificadores de voz soportados y sus orígenes en HuggingFace
SUPPORTED_PIPER_VOICES: dict[str, dict[str, str]] = {
    "es_MX-cori-high": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_AR/daniela/high/es_AR-daniela-high.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_AR/daniela/high/es_AR-daniela-high.onnx.json",
    },
    "es_MX-claude-high": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/claude/high/es_MX-claude-high.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/claude/high/es_MX-claude-high.onnx.json",
    },
    "es_MX-ald-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/ald/medium/es_MX-ald-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/ald/medium/es_MX-ald-medium.onnx.json",
    },
    "es_ES-davefx-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json",
    },
    "es_ES-sharvard-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json",
    },
}

_piper_voices_cache: dict[str, PiperVoice] = {}


def _normalize_piper_config(config_path: Path) -> None:
    """
    Corrige incompatibilidad de StrEnum en Python 3.11+ donde `piper-tts` evalúa
    `str(PhonemeType.ESPEAK)` como `'PhonemeType.ESPEAK'` en lugar de `'espeak'`.
    """
    if not config_path.exists():
        return
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        raw_pt = data.get("phoneme_type")
        if raw_pt in (None, "PhonemeType.ESPEAK", "ESPEAK"):
            data["phoneme_type"] = PhonemeType.ESPEAK.value
            config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        elif raw_pt in ("PhonemeType.TEXT", "TEXT"):
            data["phoneme_type"] = PhonemeType.TEXT.value
            config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception:
        pass


def _ensure_voice_files_exist(voice_id: str) -> tuple[Path, Path]:
    """Verifica que el archivo .onnx y .onnx.json de la voz solicitada existan en disco."""
    if voice_id not in SUPPORTED_PIPER_VOICES:
        raise ValueError(
            f"La voz '{voice_id}' no está disponible. Voces soportadas: "
            f"{sorted(SUPPORTED_PIPER_VOICES.keys())}"
        )

    piper_dir = settings.MODEL_CACHE_DIR / "piper"
    piper_dir.mkdir(parents=True, exist_ok=True)
    model_path = piper_dir / f"{voice_id}.onnx"
    config_path = piper_dir / f"{voice_id}.onnx.json"

    urls = SUPPORTED_PIPER_VOICES[voice_id]
    if not model_path.exists():
        urllib.request.urlretrieve(urls["onnx"], model_path)
    if not config_path.exists():
        urllib.request.urlretrieve(urls["json"], config_path)

    _normalize_piper_config(config_path)
    return model_path, config_path


def get_piper_voice(voice_id: str | None = None) -> tuple[PiperVoice, str]:
    """Obtiene la instancia PiperVoice correspondiente al identificador de voz solicitado."""
    resolved_id = (voice_id or settings.PIPER_VOICE_MODEL).strip()
    if resolved_id not in SUPPORTED_PIPER_VOICES:
        raise ValueError(
            f"Identificador de voz '{resolved_id}' no válido o removido. "
            f"Permitidos: {sorted(SUPPORTED_PIPER_VOICES.keys())}"
        )

    if resolved_id not in _piper_voices_cache:
        model_path, config_path = _ensure_voice_files_exist(resolved_id)
        _piper_voices_cache[resolved_id] = PiperVoice.load(
            str(model_path),
            config_path=str(config_path),
            use_cuda=False,
        )

    return _piper_voices_cache[resolved_id], resolved_id


def synthesize_text_to_wav(
    text: str,
    voice_id: str | None = None,
) -> tuple[Path, float, str]:
    """
    Sintetiza texto a un archivo WAV temporal usando la voz seleccionada en piper-tts (VITS).
    Retorna (ruta_wav, tiempo_procesamiento_ms, voice_id_usado).
    """
    start = time.perf_counter()
    output_path = allocate_temp_path(suffix=".wav", prefix="tts_out_")

    try:
        voice, resolved_id = get_piper_voice(voice_id)
        with wave.open(str(output_path), "wb") as wav_file:
            voice.synthesize(text, wav_file)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return output_path, elapsed_ms, resolved_id
    except Exception:
        remove_temp_file(output_path)
        raise
