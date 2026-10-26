"""Rutas REST para STT (archivos de audio adjuntos) y TTS (síntesis ligera con Piper/VITS)."""

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.voice_log import VoiceLog
from app.schemas.voice import STTResponse, TTSRequest
from app.services.stt_service import transcribe_audio_file
from app.services.temp_storage import remove_temp_file, save_upload_temporarily
from app.services.tts_service import synthesize_text_to_wav

router = APIRouter(prefix="/api/v1", tags=["Voice API"])


@router.post("/stt", response_model=STTResponse)
async def speech_to_text_upload(
    file: UploadFile = File(..., description="Archivo de audio adjunto (.wav, .mp3, .ogg, .webm)"),
    language: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Almacena temporalmente el archivo de audio adjunto en `/tmp/hakuyomi_audio`,
    ejecuta transcripción con `whisper-base` (~140MB) y elimina el archivo en `finally`.
    """
    async with save_upload_temporarily(file) as temp_audio_path:
        result = await asyncio.to_thread(
            transcribe_audio_file,
            temp_audio_path,
            language,
        )

    log_entry = VoiceLog(
        operation_type="stt_rest",
        model_used=result["model"],
        text_content=result["text"],
        language=result["language"],
        audio_duration_sec=result["duration_sec"],
        processing_time_ms=result["processing_time_ms"],
    )
    db.add(log_entry)
    await db.commit()

    return STTResponse(**result)


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
