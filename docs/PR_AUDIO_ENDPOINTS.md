# Pull Request: `feat/audio-endpoints` → `main`

## Título
`feat(stt): implement real-time WebSocket stream and HTTP upload audio endpoints with auth and 10MB validation`

## Resumen de Cambios
- **Rama origen:** `feat/audio-endpoints`
- **Rama destino:** `main`
- **Objetivo:** Implementar los servicios desacoplados de transcripción de audio en tiempo real por WebSockets y por subida de archivos adjuntos HTTP en FastAPI utilizando exclusivamente el modelo ligero `whisper-base` (~140 MB), aplicando autenticación obligatoria, validación Pydantic de payloads y límite estricto de `10 MB` por archivo/sesión.

## Detalle Técnico

### 1. Endpoint WebSocket de Transcripción Iterativa (`ws://.../api/v1/stt/stream`)
- Implementado en [`app/api/ws_stt.py`](../app/api/ws_stt.py) (`websocket_realtime_stt_stream`).
- **Autenticación previa al handshake:** Valida el token con `verify_ws_auth` (`Authorization: Bearer <token>`, `X-API-Key` o `?token=`) y rechaza conexiones no autorizadas con `1008 Policy Violation`.
- **Transcripción iterativa con `whisper-base`:** Recibe fragmentos binarios de audio en tiempo real, los valida con `STTStreamChunkPayload`, acumula ventanas temporales (`WS_CHUNK_DURATION_MS=2000`) hasta un máximo de `10 MB` y devuelve eventos estructurados `STTStreamEventResponse` (`partial_transcript` con contador de iteración incremental y `final_transcript` al recibir `{"action": "flush"}` o `{"action": "stop"}`).

### 2. Endpoint HTTP POST de Subida de Audio (`POST /api/v1/stt/upload`)
- Implementado en [`app/api/routes_voice.py`](../app/api/routes_voice.py) (`speech_to_text_upload`).
- Configurado con `UploadFile` de FastAPI para recibir archivos adjuntos `.mp3` y `.wav`.
- Almacena el archivo temporalmente en `/tmp/hakuyomi_audio` mediante el gestor de contexto `save_upload_temporarily`, ejecuta inferencia con `whisper-base`, registra los metadatos en PostgreSQL (`VoiceLog`) y elimina el archivo temporal en el bloque `finally`.

### 3. Seguridad, Desacople y Validaciones Estandarizadas
- **Capa de Seguridad ([`app/core/security.py`](../app/core/security.py)):** Dependencias reutilizables `verify_http_auth` y `verify_ws_auth` comparando tokens en tiempo constante (`secrets.compare_digest`).
- **Esquemas Pydantic ([`app/schemas/voice.py`](../app/schemas/voice.py)):**
  - `STTUploadPayload`: Valida nombre de archivo, extensión (`.mp3`, `.wav`), `Content-Type`, código de idioma ISO y límite estricto de `10 MB` (`10,485,760` bytes).
  - `STTStreamControlPayload` y `STTStreamChunkPayload`: Validan los mensajes de control JSON y los fragmentos binarios en el stream WebSocket.
  - `STTUploadResponse` y `STTStreamEventResponse`: Contratos tipados de salida.

## Checklist de Verificación
- [x] El proyecto mantiene exclusivamente `whisper-base` (~140 MB) y `piper-tts` (~150 MB), pesando `< 10 GB` en total.
- [x] El contenedor corre bajo el usuario sin privilegios `appuser` (`10001:10001`).
- [x] Todas las rutas (`/api/v1/stt/upload`, `/api/v1/tts`, `/api/v1/stt/stream`) requieren autenticación.
- [x] Límite de archivo de `10 MB` validado tanto por Pydantic como en lectura por *stream*.
- [x] Limpieza determinista de archivos temporales en `/tmp/hakuyomi_audio`.
