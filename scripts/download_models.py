"""
Script de aprovisionamiento controlado de modelos ligeros para hakuyomi-voice-api.
Garantiza que SOLO se descarguen:
1. whisper-base (~140 MB) para STT.
2. piper-tts / VITS (~60-150 MB) para TTS.
Bloquea cualquier intento de descargar modelos pesados (small, medium, large).
"""

import os
import sys
import urllib.request
from pathlib import Path

ALLOWED_WHISPER_MODELS = {"tiny", "base"}
STRICT_WHISPER_MODEL = os.getenv("STT_MODEL_NAME", "base")
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/app/models"))
PIPER_VOICE = os.getenv("PIPER_VOICE_MODEL", "es_MX-ald-medium")

# URL oficial de HuggingFace para voces ligeras Piper (arquitectura VITS en ONNX)
PIPER_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_MX/ald/medium"
)


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


def download_piper_model(piper_dir: Path) -> None:
    onnx_file = piper_dir / f"{PIPER_VOICE}.onnx"
    json_file = piper_dir / f"{PIPER_VOICE}.onnx.json"

    if not onnx_file.exists():
        url_onnx = f"{PIPER_BASE_URL}/{PIPER_VOICE}.onnx"
        print(f"[INFO] Descargando modelo TTS ligero Piper/VITS: {url_onnx}")
        urllib.request.urlretrieve(url_onnx, onnx_file)

    if not json_file.exists():
        url_json = f"{PIPER_BASE_URL}/{PIPER_VOICE}.onnx.json"
        print(f"[INFO] Descargando configuración de modelo TTS: {url_json}")
        urllib.request.urlretrieve(url_json, json_file)


def download_whisper_base(whisper_dir: Path) -> None:
    from faster_whisper import WhisperModel

    print(f"[INFO] Descargando modelo STT ligero: whisper-{STRICT_WHISPER_MODEL} (~140MB)")
    WhisperModel(
        STRICT_WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
        download_root=str(whisper_dir),
    )
    print("[INFO] Modelo whisper-base verificado correctamente.")


if __name__ == "__main__":
    w_dir, p_dir = validate_and_prepare_dirs()
    download_whisper_base(w_dir)
    download_piper_model(p_dir)
    print("[OK] Modelos ligeros listos. Huella total de modelos < 300 MB.")
