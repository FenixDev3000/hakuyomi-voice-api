# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime

# Evitar archivos .pyc, habilitar logs inmediatos y deshabilitar caché de pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STT_MODEL_NAME=base \
    TTS_ENGINE=piper-tts \
    PIPER_VOICE_MODEL=es_MX-ald-medium \
    MODEL_CACHE_DIR=/app/models \
    TEMP_AUDIO_DIR=/tmp/hakuyomi_audio \
    HOME=/app

WORKDIR /app

# 1. Instalar únicamente ffmpeg ligero para decodificación de audio y limpiar listas apt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Crear grupo y usuario sin privilegios (no-root) con UID/GID 10001
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /app -s /usr/sbin/nologin -M appuser && \
    mkdir -p /app/models/whisper /app/models/piper /tmp/hakuyomi_audio && \
    chown -R appuser:appgroup /app /tmp/hakuyomi_audio

# 3. Instalar dependencias estrictas de Python sin paquetes CUDA/GPU pesados
COPY --chown=appuser:appgroup requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir requests==2.32.3

# 4. Copiar código de la aplicación y script de modelos con propietario no-root
COPY --chown=appuser:appgroup scripts/ ./scripts/
COPY --chown=appuser:appgroup app/ ./app/
RUN chown -R appuser:appgroup /app /tmp/hakuyomi_audio

# 5. Cambiar al usuario no-root ANTES de descargar modelos y ejecutar el servidor
USER appuser:appgroup

# Pre-descargar exclusivamente whisper-base (~140MB) y piper-tts (~65MB) como appuser
RUN python scripts/download_models.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
