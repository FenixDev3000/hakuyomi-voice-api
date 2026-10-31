"""Pruebas de seguridad mínimas: sin token, token inválido, entrada inválida, CORS y errores."""

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.services.temp_storage import ensure_temp_dir

ENDPOINTS_PROTEGIDOS = [
    ("get", "/api/v1/voices"),
    ("post", "/api/v1/stt/upload"),
    ("post", "/api/v1/tts"),
]


def test_health_es_publico(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("metodo,ruta", ENDPOINTS_PROTEGIDOS)
def test_sin_token_401(client, metodo, ruta):
    assert getattr(client, metodo)(ruta).status_code == 401


@pytest.mark.parametrize("metodo,ruta", ENDPOINTS_PROTEGIDOS)
def test_token_invalido_401(client, metodo, ruta):
    r = getattr(client, metodo)(ruta, headers={"Authorization": "Bearer token-incorrecto"})
    assert r.status_code == 401


def test_token_no_ascii_es_401_no_500(client):
    r = client.get("/api/v1/voices", headers={"X-API-Key": "tökén-ñ".encode("utf-8")})
    assert r.status_code == 401


def test_token_valido_bearer_y_api_key(client, auth):
    assert client.get("/api/v1/voices", headers=auth).status_code == 200
    assert client.get("/api/v1/voices", headers={"X-API-Key": settings.API_AUTH_TOKEN}).status_code == 200


@pytest.mark.skipif(settings.DOCS_HABILITADAS, reason="/docs activo solo en local")
@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json"])
def test_docs_apagados_por_defecto(client, ruta):
    assert client.get(ruta).status_code == 404


def test_cors_origen_ajeno_sin_cabecera(client):
    r = client.get("/health", headers={"Origin": "http://evil.com"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_origen_permitido(client):
    origen = settings.cors_origin_list[0]
    r = client.get("/health", headers={"Origin": origen})
    assert r.headers.get("access-control-allow-origin") == origen


# --- Entradas inválidas -------------------------------------------------------

def test_tts_texto_vacio_422(client, auth):
    assert client.post("/api/v1/tts", json={"text": ""}, headers=auth).status_code == 422


def test_tts_texto_demasiado_largo_422(client, auth):
    r = client.post("/api/v1/tts", json={"text": "a" * 2001}, headers=auth)
    assert r.status_code == 422


def test_tts_voz_no_permitida_422(client, auth):
    r = client.post("/api/v1/tts", json={"text": "hola", "voice": "../../etc/passwd"}, headers=auth)
    assert r.status_code == 422


def test_upload_extension_no_permitida_422(client, auth):
    r = client.post(
        "/api/v1/stt/upload",
        files={"file": ("malo.exe", b"MZ0000", "application/octet-stream")},
        headers=auth,
    )
    assert r.status_code == 422


def test_upload_vacio_400(client, auth):
    r = client.post(
        "/api/v1/stt/upload",
        files={"file": ("vacio.wav", b"", "audio/wav")},
        headers=auth,
    )
    assert r.status_code in (400, 422)


def test_upload_mayor_al_limite_413_y_sin_residuos(client, auth):
    carpeta = ensure_temp_dir()
    antes = set(carpeta.iterdir())
    grande = b"0" * (settings.max_upload_size_bytes + 1)
    r = client.post(
        "/api/v1/stt/upload",
        files={"file": ("grande.wav", grande, "audio/wav")},
        headers=auth,
    )
    assert r.status_code == 413
    assert set(carpeta.iterdir()) == antes


def test_upload_idioma_invalido_422(client, auth):
    r = client.post(
        "/api/v1/stt/upload",
        files={"file": ("a.wav", b"RIFF0000", "audio/wav")},
        data={"language": "es; DROP TABLE"},
        headers=auth,
    )
    assert r.status_code == 422


# --- WebSocket ------------------------------------------------------------------

def test_ws_sin_token_se_cierra(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/stream"):
            pass
    assert exc.value.code == 1008


def test_ws_token_invalido_se_cierra(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/stream?token=incorrecto"):
            pass
    assert exc.value.code == 1008


def test_ws_ping_y_control_invalido_sin_detalle_interno(client):
    with client.websocket_connect(f"/api/v1/stt/stream?token={settings.API_AUTH_TOKEN}") as ws:
        assert ws.receive_json()["type"] == "session_started"
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["type"] == "pong"
        ws.send_json({"action": "hackear"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["detail"] == "Payload de control inválido."
        ws.send_json({"action": "stop"})
