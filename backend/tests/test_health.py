
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["application"] == "ReconIQ"
    assert data["message"] == "Welcome to ReconIQ"


def test_application_health():
    response = client.get("/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "UP",
        "service": "ReconIQ",
    }
