"""
Script de aprovisionamiento controlado de modelos ligeros para hakuyomi-voice-api.
Garantiza que SOLO se descarguen modelos ligeros (< 10 GB total):
1. whisper-base (~140 MB) para STT.
2. Voces de Piper-TTS / VITS:
   - es_MX-cori-high (femenina, ~63 MB)
   - es_MX-claude-high (masculina, ~63 MB)
   - es_MX-ald-medium (masculina, ~63 MB)
Elimina explícitamente cualquier rastro de las voces obsoletas 'Camila' y 'Lucas'.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ALLOWED_WHISPER_MODELS = {"tiny", "base"}
STRICT_WHISPER_MODEL = os.getenv("STT_MODEL_NAME", "base")
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/app/models"))

# Mapa oficial de voces Piper/VITS soportadas en el backend
PIPER_VOICE_SOURCES: dict[str, dict[str, str]] = {
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
}

# Voces que se pre-descargan al construir/aprovisionar el contenedor
PRELOAD_PIPER_VOICES = ("es_MX-cori-high", "es_MX-claude-high", "es_MX-ald-medium")

# Voces obsoletas eliminadas por política
REMOVED_VOICES = ("es_LAT-camila-medium", "es_LAT-lucas-medium", "camila", "lucas")


def validate_and_prepare_dirs() -> tuple[Path, Path]:
    if STRICT_WHISPER_MODEL not in ALLOWED_WHISPER_MODELS:
        print(
            f"[ERROR] Modelo STT '{STRICT_WHISPER_MODEL}' rechazado por política de tamaño (<10GB). "
            f"Use exclusivamente 'base' (~140MB).",
            file=sys.stderr,
        )
        sys.exit(1)

    whisper_dir = MODEL_CACHE_DIR / "whisper"
    piper_dir = MODEL_CACHE_DIR / "piper"
    whisper_dir.mkdir(parents=True, exist_ok=True)
    piper_dir.mkdir(parents=True, exist_ok=True)
    return whisper_dir, piper_dir


def remove_obsolete_voices(piper_dir: Path) -> None:
    """Elimina cualquier archivo de modelo asociado a las voces removidas Camila y Lucas."""
    for item in piper_dir.iterdir():
        lower_name = item.name.lower()
        if any(obs.lower() in lower_name for obs in REMOVED_VOICES):
            print(f"[CLEANUP] Eliminando modelo de voz obsoleto: {item.name}")
            item.unlink(missing_ok=True)


def normalize_piper_json(json_file: Path) -> None:
    """Asegura compatibilidad de phoneme_type con StrEnum en Python 3.11+."""
    if not json_file.exists():
        return
    data = json.loads(json_file.read_text(encoding="utf-8"))
    if data.get("phoneme_type") in (None, "PhonemeType.ESPEAK", "ESPEAK"):
        data["phoneme_type"] = "espeak"
        json_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def download_piper_voice(piper_dir: Path, voice_id: str) -> None:
    if voice_id not in PIPER_VOICE_SOURCES:
        raise ValueError(f"Identificador de voz Piper no soportado: {voice_id}")

    urls = PIPER_VOICE_SOURCES[voice_id]
    onnx_file = piper_dir / f"{voice_id}.onnx"
    json_file = piper_dir / f"{voice_id}.onnx.json"

    if not onnx_file.exists():
        print(f"[INFO] Descargando modelo TTS Piper/VITS '{voice_id}': {urls['onnx']}")
        urllib.request.urlretrieve(urls["onnx"], onnx_file)

    if not json_file.exists():
        print(f"[INFO] Descargando configuración TTS '{voice_id}': {urls['json']}")
        urllib.request.urlretrieve(urls["json"], json_file)

    normalize_piper_json(json_file)
    print(f"[OK] Modelo de voz '{voice_id}' listo en {onnx_file}")


def download_whisper_base(whisper_dir: Path) -> None:
    from faster_whisper import WhisperModel

    print(f"[INFO] Verificando modelo STT ligero: whisper-{STRICT_WHISPER_MODEL} (~140MB)")
    WhisperModel(
        STRICT_WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
        download_root=str(whisper_dir),
    )
    print("[INFO] Modelo whisper-base verificado correctamente.")


if __name__ == "__main__":
    w_dir, p_dir = validate_and_prepare_dirs()
    remove_obsolete_voices(p_dir)
    download_whisper_base(w_dir)
    for v_id in PRELOAD_PIPER_VOICES:
        download_piper_voice(p_dir, v_id)
    print("[OK] Todos los modelos ligeros están listos (< 10 GB).")
