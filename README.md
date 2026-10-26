# Hakuyomi Voice API (`hakuyomi-voice-api`)

Servicio backend ligero de Reconocimiento de Voz (STT) y Síntesis de Voz (TTS) construido con **FastAPI** y **PostgreSQL 15**, diseñado para ejecutarse en un contenedor Docker limpio, **sin privilegios `root`** y con una huella total **estrictamente menor a 10 GB** (~1.05 GB en total).

## Características Principales

- **Presupuesto Estricto `< 10 GB`**:
  - **Voz a Texto (STT):** Exclusivamente `whisper-base` (~140 MB) sobre `faster-whisper` (CPU `int8`, sin librerías CUDA pesadas).
  - **Texto a Voz (TTS):** Exclusivamente `piper-tts` / arquitectura **VITS** en ONNX (~65–150 MB).
- **STT en Tiempo Real por WebSockets (`WS /ws/stt`)**: Transcripción incremental por ventanas de audio y consolidación al cierre.
- **Almacenamiento Temporal Seguro (`/tmp/hakuyomi_audio`)**: Montado en `tmpfs` (máx. 256 MB) con triple mecanismo de limpieza (`try...finally`, `BackgroundTasks` y recolector TTL).
- **Contenedor No-Root**: Ejecución bajo el usuario `appuser` (`UID 10001` / `GID 10001`), `no-new-privileges:true` y `cap_drop: ALL`.

## Inicio Rápido

1. Copiar las variables de entorno:
   ```bash
   cp .env.example .env
   ```
2. Construir y levantar los contenedores:
   ```bash
   docker compose up -d --build
   ```
3. Verificar estado del servicio:
   ```bash
   curl http://localhost:8000/health
   ```

Consulta la arquitectura detallada y los diagramas de flujo en [`docs/DISENO.md`](docs/DISENO.md).
