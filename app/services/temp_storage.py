"""
Gestión del almacenamiento temporal de archivos de audio adjuntos y generados.
Garantiza aislamiento en /tmp/hakuyomi_audio, límite estricto de tamaño por archivo
y purga automática determinista + recolector por TTL.
"""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".flac", ".m4a"}
CHUNK_READ_SIZE = 64 * 1024  # 64 KB


def ensure_temp_dir() -> Path:
    """Asegura que el directorio temporal exista con permisos del usuario no-root."""
    settings.TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    return settings.TEMP_AUDIO_DIR


def remove_temp_file(file_path: str | Path) -> None:
    """Elimina de forma segura un archivo temporal del sistema de archivos."""
    try:
        path_obj = Path(file_path)
        if path_obj.exists() and path_obj.is_file():
            path_obj.unlink(missing_ok=True)
    except OSError:
        pass


def allocate_temp_path(suffix: str = ".wav", prefix: str = "audio_") -> Path:
    """Reserva una ruta única dentro de TEMP_AUDIO_DIR."""
    base_dir = ensure_temp_dir()
    clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return base_dir / f"{prefix}{uuid.uuid4().hex}{clean_suffix}"


@asynccontextmanager
async def save_upload_temporarily(upload_file: UploadFile) -> AsyncGenerator[Path, None]:
    """
    Guarda un archivo de audio adjunto validando su extensión y tamaño máximo,
    y garantiza su eliminación inmediata al salir del bloque mediante `finally`.
    """
    filename = upload_file.filename or "audio.wav"
    ext = Path(filename).suffix.lower() or ".wav"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de archivo '{ext}' no soportado. Permitidos: {sorted(ALLOWED_EXTENSIONS)}",
        )

    temp_path = allocate_temp_path(suffix=ext, prefix="stt_upload_")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_written = 0

    try:
        with temp_path.open("wb") as buffer:
            while True:
                chunk = await upload_file.read(CHUNK_READ_SIZE)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"El archivo adjunto excede el límite de {settings.MAX_UPLOAD_SIZE_MB} MB.",
                    )
                buffer.write(chunk)

        if total_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de audio adjunto está vacío.",
            )

        yield temp_path
    finally:
        await upload_file.close()
        remove_temp_file(temp_path)


def cleanup_expired_temp_files() -> int:
    """Purga archivos temporales huérfanos cuya antigüedad supere TEMP_FILE_TTL_SECONDS."""
    base_dir = ensure_temp_dir()
    now = time.time()
    ttl = settings.TEMP_FILE_TTL_SECONDS
    removed_count = 0

    for item in base_dir.iterdir():
        if not item.is_file():
            continue
        try:
            age = now - item.stat().st_mtime
            if age > ttl:
                item.unlink(missing_ok=True)
                removed_count += 1
        except OSError:
            continue
    return removed_count


async def periodic_temp_cleanup_worker(interval_seconds: int = 60) -> None:
    """Tarea en segundo plano que limpia archivos expirados periódicamente."""
    while True:
        try:
            cleanup_expired_temp_files()
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)
