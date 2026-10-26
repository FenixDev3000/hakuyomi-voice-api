"""
Endpoint WebSocket (/ws/stt) para transcripción de Voz a Texto (STT) en tiempo real
mediante el modelo ligero `whisper-base` (~140MB).
"""

import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.voice_log import VoiceLog
from app.services.stt_service import transcribe_pcm16_bytes

router = APIRouter(tags=["WebSocket Real-Time STT"])

# Umbral de ventana para PCM 16-bit 16kHz mono (32,000 bytes = 1 segundo)
BYTES_PER_SECOND_PCM16 = 16000 * 2


@router.websocket("/ws/stt")
async def websocket_realtime_stt(websocket: WebSocket, lang: str = "es"):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    audio_buffer = bytearray()
    window_threshold_bytes = int(
        (settings.WS_CHUNK_DURATION_MS / 1000.0) * BYTES_PER_SECOND_PCM16
    )
    bytes_since_last_partial = 0

    await websocket.send_json(
        {
            "type": "session_started",
            "session_id": session_id,
            "model": f"whisper-{settings.STT_MODEL_NAME}",
            "language": lang,
        }
    )

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                chunk: bytes = message["bytes"]
                if len(audio_buffer) + len(chunk) > settings.WS_MAX_BUFFER_BYTES:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "session_id": session_id,
                            "detail": "Buffer máximo de sesión WebSocket excedido.",
                        }
                    )
                    audio_buffer.clear()
                    bytes_since_last_partial = 0
                    continue

                audio_buffer.extend(chunk)
                bytes_since_last_partial += len(chunk)

                # Emitir transcripción parcial al completar cada ventana temporal
                if bytes_since_last_partial >= window_threshold_bytes:
                    bytes_since_last_partial = 0
                    snapshot = bytes(audio_buffer)
                    partial_res = await asyncio.to_thread(
                        transcribe_pcm16_bytes,
                        snapshot,
                        16000,
                        lang,
                        True,
                    )
                    await websocket.send_json(
                        {
                            "type": "partial_transcript",
                            "session_id": session_id,
                            "text": partial_res["text"],
                            "is_final": False,
                            "model": partial_res["model"],
                        }
                    )

            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    payload = {"action": message["text"].strip()}

                action = payload.get("action")
                if action in {"flush", "stop"}:
                    if audio_buffer:
                        final_bytes = bytes(audio_buffer)
                        audio_buffer.clear()
                        bytes_since_last_partial = 0

                        final_res = await asyncio.to_thread(
                            transcribe_pcm16_bytes,
                            final_bytes,
                            16000,
                            lang,
                            False,
                        )
                        async with AsyncSessionLocal() as db:
                            db.add(
                                VoiceLog(
                                    operation_type="stt_ws",
                                    model_used=final_res["model"],
                                    text_content=final_res["text"],
                                    language=final_res["language"],
                                    audio_duration_sec=final_res["duration_sec"],
                                    processing_time_ms=final_res["processing_time_ms"],
                                )
                            )
                            await db.commit()

                        await websocket.send_json(
                            {
                                "type": "final_transcript",
                                "session_id": session_id,
                                "text": final_res["text"],
                                "duration_sec": final_res["duration_sec"],
                                "processing_time_ms": final_res["processing_time_ms"],
                                "is_final": True,
                                "model": final_res["model"],
                            }
                        )
                    if action == "stop":
                        break

    except WebSocketDisconnect:
        pass
    finally:
        # Liberación garantizada del buffer de sesión en memoria
        audio_buffer.clear()
