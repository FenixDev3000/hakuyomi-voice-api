import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="session")
def client():
    # Sin `with`: no ejecuta el lifespan, así que no necesita la base de datos.
    return TestClient(app)


@pytest.fixture(scope="session")
def auth():
    return {"Authorization": f"Bearer {settings.API_AUTH_TOKEN}"}
