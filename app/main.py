"""Punto de entrada principal FastAPI para hakuyomi-voice-api."""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_voice import router as voice_router
from app.api.ws_stt import router as ws_stt_router
from app.core.config import settings
from app.core.database import init_db
from app.services.temp_storage import ensure_temp_dir, periodic_temp_cleanup_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_temp_dir()
    await init_db()
    cleanup_task = asyncio.create_task(periodic_temp_cleanup_worker(interval_seconds=60))
    try:
        yield
    finally:
        cleanup_task.cancel()


app = FastAPI(
    title="Hakuyomi Voice API",
    description=(
        "API ligera (<10GB) de Reconocimiento (whisper-base) y Síntesis de Voz (piper-tts/VITS) "
        "con soporte de streaming por WebSockets y PostgreSQL."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_HABILITADAS else None,
    redoc_url="/redoc" if settings.DOCS_HABILITADAS else None,
    openapi_url="/openapi.json" if settings.DOCS_HABILITADAS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)

app.include_router(voice_router)
app.include_router(ws_stt_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "stt_model": f"whisper-{settings.STT_MODEL_NAME}",
        "tts_engine": settings.TTS_ENGINE,
        "tts_voice": settings.PIPER_VOICE_MODEL,
        "temp_audio_dir": str(settings.TEMP_AUDIO_DIR),
    }
