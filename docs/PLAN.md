# PLAN · hakuyomi-voice-api

Tipo: **API (FastAPI + PostgreSQL) con IA local** (Whisper-base STT, Piper TTS). Sin Alembic por ahora: las tablas se crean al arrancar (`init_db`).

## Estado de alineación con el estándar HAKUYOMI (rama `chore/estandar-hakuyomi`)
- Compose compatible con `docker-compose` 1.29.2; sin puertos en la base; `restart: always`; logs con rotación; volumen con nombre explícito; imagen con versión fija.
- `/docs`, `/redoc`, `/openapi.json` apagados salvo `DOCS_HABILITADAS=1`.
- CORS con métodos y cabeceras acotados.

## Pendiente (decisión de Miyo)
- Puerto definitivo y `VOICE_BIND` para la VM (hoy `8000`, valor por defecto).
- Autenticación: hoy es un token estático compartido sin roles. Si la web es pública, el token no debe viajar en el bundle.
- Rate limit y límite de intentos (no implementados).
- Migraciones con Alembic y pruebas automáticas (`pytest`).
