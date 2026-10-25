import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_container_healthcheck_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "CarePolicyGuard"
    assert "version" in data
    assert "tau_threshold" in data
    assert data["tau_threshold"] == 0.85

