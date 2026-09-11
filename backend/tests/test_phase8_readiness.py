from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_cors_origins_are_exact_configured_values():
    configured = Settings(
        _env_file=None,
        frontend_origin="http://ignored.example",
        frontend_origins="https://job-hunter.example, https://preview.example/",
    )
    assert configured.cors_origins == ["https://job-hunter.example", "https://preview.example"]


def test_health_is_public_and_minimal():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
