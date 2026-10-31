"""
Endpoint WebSocket (`ws://.../api/v1/stt/stream`) para transcripción iterativa de Voz a Texto (STT)
en tiempo real utilizando exclusivamente el modelo ligero `whisper-base` (~140MB).
Incluye autenticación de conexión, validación Pydantic de mensajes/fragmentos y límite de 10 MB.
"""

import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import verify_ws_auth
from app.models.voice_log import VoiceLog
from app.schemas.voice import (
    STTStreamChunkPayload,
    STTStreamControlPayload,
    STTStreamEventResponse,
)
from app.services.stt_service import transcribe_pcm16_bytes

router = APIRouter(prefix="/api/v1", tags=["WebSocket Real-Time STT"])


@router.websocket("/stt/stream")
async def websocket_realtime_stt_stream(websocket: WebSocket, lang: str = "es"):
    """
    Recibe fragmentos de audio en tiempo real por WebSocket (`ws://.../api/v1/stt/stream`)
    y devuelve la transcripción iterativa usando `whisper-base`.
    """
    if not await verify_ws_auth(websocket):
        return

    await websocket.accept()
    session_id = str(uuid.uuid4())
    audio_buffer = bytearray()
    sample_rate = 16000
    current_lang = lang
    iteration = 0
    bytes_since_last_partial = 0

    start_event = STTStreamEventResponse(
        type="session_started",
        session_id=session_id,
        iteration=0,
        language=current_lang,
        model=f"whisper-{settings.STT_MODEL_NAME}",
    )
    await websocket.send_json(start_event.model_dump())

    try:
        while True:
            message = await websocket.receive()

            # 1. Recepción de fragmentos binarios de audio en tiempo real
            if "bytes" in message and message["bytes"] is not None:
                chunk: bytes = message["bytes"]

                try:
                    STTStreamChunkPayload(chunk_size_bytes=len(chunk))
                except ValidationError as exc:
                    err_event = STTStreamEventResponse(
                        type="error",
                        session_id=session_id,
                        iteration=iteration,
                        language=current_lang,
                        detail=f"Fragmento inválido: {exc.errors()[0]['msg']}",
                    )
                    await websocket.send_json(err_event.model_dump())
                    continue

                if len(audio_buffer) + len(chunk) > settings.WS_MAX_BUFFER_BYTES:
                    err_event = STTStreamEventResponse(
                        type="error",
                        session_id=session_id,
                        iteration=iteration,
                        language=current_lang,
                        detail=(
                            f"Buffer de sesión excede el límite máximo permitido de "
                            f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                        ),
                    )
                    await websocket.send_json(err_event.model_dump())
                    audio_buffer.clear()
                    bytes_since_last_partial = 0
                    continue

                audio_buffer.extend(chunk)
                bytes_since_last_partial += len(chunk)

                # Umbral de ventana temporal para PCM 16-bit mono (sample_rate * 2 bytes/seg)
                window_threshold_bytes = int(
                    (settings.WS_CHUNK_DURATION_MS / 1000.0) * (sample_rate * 2)
                )

                if bytes_since_last_partial >= window_threshold_bytes:
                    bytes_since_last_partial = 0
                    iteration += 1
                    snapshot = bytes(audio_buffer)

                    partial_res = await asyncio.to_thread(
                        transcribe_pcm16_bytes,
                        snapshot,
                        sample_rate,
                        current_lang,
                        True,
                    )

                    partial_event = STTStreamEventResponse(
                        type="partial_transcript",
                        session_id=session_id,
                        iteration=iteration,
                        text=partial_res["text"],
                        is_final=False,
                        language=partial_res["language"],
                        duration_sec=partial_res["duration_sec"],
                        processing_time_ms=partial_res["processing_time_ms"],
                        model=partial_res["model"],
                    )
                    await websocket.send_json(partial_event.model_dump())

            # 2. Recepción de mensajes JSON de control validados con Pydantic
            elif "text" in message and message["text"]:
                try:
                    raw_data = json.loads(message["text"])
                    if not isinstance(raw_data, dict):
                        raw_data = {"action": str(raw_data).strip()}
                    control = STTStreamControlPayload(**raw_data)
                except (json.JSONDecodeError, ValidationError) as exc:
                    err_event = STTStreamEventResponse(
                        type="error",
                        session_id=session_id,
                        iteration=iteration,
                        language=current_lang,
                        detail="Payload de control inválido.",
                    )
                    await websocket.send_json(err_event.model_dump())
                    continue

                if control.action == "ping":
                    pong_event = STTStreamEventResponse(
                        type="pong",
                        session_id=session_id,
                        iteration=iteration,
                        language=current_lang,
                    )
                    await websocket.send_json(pong_event.model_dump())

                elif control.action == "config":
                    current_lang = control.language
                    sample_rate = control.sample_rate
                    cfg_event = STTStreamEventResponse(
                        type="config_updated",
                        session_id=session_id,
                        iteration=iteration,
                        language=current_lang,
                    )
                    await websocket.send_json(cfg_event.model_dump())

                elif control.action in {"flush", "stop"}:
                    if audio_buffer:
                        iteration += 1
                        final_bytes = bytes(audio_buffer)
                        audio_buffer.clear()
                        bytes_since_last_partial = 0

                        final_res = await asyncio.to_thread(
                            transcribe_pcm16_bytes,
                            final_bytes,
                            sample_rate,
                            current_lang,
                            False,
                        )

                        async with AsyncSessionLocal() as db:
                            db.add(
                                VoiceLog(
                                    operation_type="stt_stream",
                                    model_used=final_res["model"],
                                    text_content=final_res["text"],
                                    language=final_res["language"],
                                    audio_duration_sec=final_res["duration_sec"],
                                    processing_time_ms=final_res["processing_time_ms"],
                                )
                            )
                            await db.commit()

                        final_event = STTStreamEventResponse(
                            type="final_transcript",
                            session_id=session_id,
                            iteration=iteration,
                            text=final_res["text"],
                            is_final=True,
                            language=final_res["language"],
                            duration_sec=final_res["duration_sec"],
                            processing_time_ms=final_res["processing_time_ms"],
                            model=final_res["model"],
                        )
                        await websocket.send_json(final_event.model_dump())

                    if control.action == "stop":
                        break

    except WebSocketDisconnect:
        pass
    finally:
        audio_buffer.clear()
