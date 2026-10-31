"""
Módulo de seguridad y autenticación desacoplado para rutas HTTP y conexiones WebSocket.
Soporta autenticación mediante cabecera `Authorization: Bearer <token>` o `X-API-Key`.
"""

import secrets
from fastapi import Depends, HTTPException, Security, WebSocket, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _is_valid_token(candidate: str | None) -> bool:
    if not candidate:
        return False
    # Comparar en bytes: compare_digest con str no ASCII lanza TypeError (500 en vez de 401)
    return secrets.compare_digest(
        candidate.strip().encode("utf-8"), settings.API_AUTH_TOKEN.encode("utf-8")
    )


async def verify_http_auth(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
) -> str:
    """
    Dependencia de autenticación para endpoints HTTP (REST).
    Verifica el token en `Authorization: Bearer` o en `X-API-Key`.
    """
    token = bearer.credentials if bearer else api_key
    if not _is_valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado: Token de autenticación inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token  # type: ignore[return-value]


async def verify_ws_auth(websocket: WebSocket) -> bool:
    """
    Validador de autenticación para conexiones WebSocket (`/api/v1/stt/stream`).
    Acepta token por cabecera `Authorization: Bearer <token>`, `X-API-Key` o query `?token=`.
    Si falla, cierra el socket con código estándar 1008 (Policy Violation).
    """
    auth_header = websocket.headers.get("authorization", "")
    token: str | None = None

    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    elif "x-api-key" in websocket.headers:
        token = websocket.headers.get("x-api-key")
    else:
        token = websocket.query_params.get("token")

    if not _is_valid_token(token):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="No autorizado: Token de autenticación inválido o ausente.",
        )
        return False
    return True
