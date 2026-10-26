"""
Rutas HTTP REST desacopladas para STT (`/api/v1/stt/upload`) y TTS (`/api/v1/tts`).
Todas las rutas aplican autenticación obligatoria, validación Pydantic y límite de 10 MB.
"""

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_http_auth
from app.models.voice_log import VoiceLog
from app.schemas.voice import STTUploadResponse, TTSRequest
from app.services.stt_service import transcribe_audio_file
from app.services.temp_storage import remove_temp_file, save_upload_temporarily
from app.services.tts_service import synthesize_text_to_wav

router = APIRouter(
    prefix="/api/v1",
    tags=["Voice API"],
    dependencies=[Depends(verify_http_auth)],
)


@router.post("/stt/upload", response_model=STTUploadResponse)
async def speech_to_text_upload(
    file: UploadFile = File(
        ...,
        description="Archivo de audio adjunto en formato .mp3 o .wav (máximo 10 MB)",
    ),
    language: str = Form(
        default="es",
        description="Código ISO de idioma para la transcripción (ej. es, en)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint HTTP POST `/api/v1/stt/upload`:
    - Requiere autenticación (`Authorization: Bearer <token>` o `X-API-Key`).
    - Valida mediante Pydantic (`STTUploadPayload`) extensión (`.mp3`, `.wav`), MIME type
      y límite máximo de tamaño (`10 MB`).
    - Procesa temporalmente el audio en `/tmp/hakuyomi_audio` con `whisper-base` (~140MB)
      y garantiza su eliminación inmediata al finalizar.
    """
    async with save_upload_temporarily(file, language=language) as (
        temp_audio_path,
        validated_payload,
        file_size_bytes,
    ):
        result = await asyncio.to_thread(
            transcribe_audio_file,
            temp_audio_path,
            validated_payload.language,
        )

    log_entry = VoiceLog(
        operation_type="stt_upload",
        model_used=result["model"],
        text_content=result["text"],
        language=result["language"],
        audio_duration_sec=result["duration_sec"],
        processing_time_ms=result["processing_time_ms"],
    )
    db.add(log_entry)
    await db.commit()

    return STTUploadResponse(
        text=result["text"],
        filename=validated_payload.filename,
        file_size_bytes=file_size_bytes,
        language=result["language"],
        duration_sec=result["duration_sec"],
        processing_time_ms=result["processing_time_ms"],
        model=result["model"],
    )


@router.post("/tts")
async def text_to_speech_synthesize(
    payload: TTSRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Sintetiza texto a voz utilizando `piper-tts` / VITS (~150MB) en un archivo temporal
    y programa su eliminación inmediata tras enviar el `FileResponse`.
    """
    try:
        wav_path, elapsed_ms = await asyncio.to_thread(
            synthesize_text_to_wav,
            payload.text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en síntesis TTS: {exc}") from exc

    log_entry = VoiceLog(
        operation_type="tts_rest",
        model_used=f"{settings.TTS_ENGINE}:{settings.PIPER_VOICE_MODEL}",
        text_content=payload.text,
        language="es",
        audio_duration_sec=None,
        processing_time_ms=elapsed_ms,
    )
    db.add(log_entry)
    await db.commit()

    background_tasks.add_task(remove_temp_file, wav_path)
    return FileResponse(
        path=str(wav_path),
        media_type="audio/wav",
        filename="hakuyomi_tts.wav",
    )
