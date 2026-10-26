"""
Gestión del almacenamiento temporal de archivos de audio adjuntos y generados.
Garantiza aislamiento en /tmp/hakuyomi_audio, validación Pydantic del payload,
límite estricto de tamaño por archivo (10 MB) y purga automática determinista + TTL.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.voice import STTUploadPayload

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
async def save_upload_temporarily(
    upload_file: UploadFile,
    language: str | None = "es",
) -> AsyncGenerator[tuple[Path, STTUploadPayload, int], None]:
    """
    Valida el archivo adjunto con Pydantic (`STTUploadPayload`: extensiones .mp3/.wav y
    límite de 10 MB), lo almacena temporalmente en `/tmp/hakuyomi_audio` y garantiza
    su eliminación inmediata en el bloque `finally`.
    """
    try:
        payload = STTUploadPayload(
            filename=upload_file.filename or "",
            content_type=upload_file.content_type or "audio/wav",
            file_size_bytes=upload_file.size if upload_file.size and upload_file.size > 0 else None,
            language=language or "es",
        )
    except ValidationError as exc:
        errors = "; ".join(err["msg"] for err in exc.errors())
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "file_size_bytes" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=errors) from exc

    ext = Path(payload.filename).suffix.lower()
    temp_path = allocate_temp_path(suffix=ext, prefix="stt_upload_")
    max_bytes = settings.max_upload_size_bytes
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
                        detail=(
                            f"El archivo adjunto excede el límite estandarizado de "
                            f"{settings.MAX_UPLOAD_SIZE_MB} MB ({max_bytes} bytes)."
                        ),
                    )
                buffer.write(chunk)

        if total_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo de audio adjunto está vacío.",
            )

        # Revalidar con el tamaño real escrito en disco
        validated = STTUploadPayload(
            filename=payload.filename,
            content_type=payload.content_type,
            file_size_bytes=total_written,
            language=payload.language,
        )

        yield temp_path, validated, total_written
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
