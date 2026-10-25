import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.rate_limiter import limiter
from app.db.session import engine

client = TestClient(app)

def test_rate_limiter_throttling_and_bypass():
    limiter.reset_all()

    # Make 20 rapid requests (threshold is 20 in routes.py)
    for _ in range(20):
        res = client.post("/api/v1/auth/login", json={
            "username": "clinician@hospital.org",
            "password": "WrongPassword123"
        })
        assert res.status_code == 401

    # 21st request should be throttled with HTTP 429 Too Many Requests
    throttled_res = client.post("/api/v1/auth/login", json={
        "username": "clinician@hospital.org",
        "password": "WrongPassword123"
    })
    assert throttled_res.status_code == 429
    assert "Rate limit exceeded" in throttled_res.json()["detail"]
    assert "Retry-After" in throttled_res.headers

    # With bypass header, request should succeed past rate limiter
    bypass_res = client.post(
        "/api/v1/auth/login",
        json={"username": "clinician@hospital.org", "password": "WrongPassword123"},
        headers={"X-Test-Bypass-Rate-Limit": "true"}
    )
    assert bypass_res.status_code == 401

    # Reset limiter for subsequent tests
    limiter.reset_all()

def test_hl7_da_vinci_crd_discovery():
    res = client.get("/cds-services")
    assert res.status_code == 200
    data = res.json()
    assert "services" in data
    service_ids = [s["id"] for s in data["services"]]
    assert "medicare-crd-coverage-check" in service_ids

def test_hl7_da_vinci_crd_hook_order_signing_approved():
    payload = {
        "hook": "order-sign",
        "hookInstance": "550e8400-e29b-41d4-a716-446655440000",
        "context": {
            "userId": "Practitioner/1043256787",
            "patientId": "PT-CARDIOLOGY-101",
            "draftOrders": {
                "resourceType": "DeviceRequest",
                "codeCodeableConcept": {
                    "coding": [{"code": "33249", "display": "Insertion of ICD"}]
                }
            }
        },
        "prefetch": {
            "clinicalNotes": "History of anterior myocardial infarction in 2021 (>3 years ago). Echo on 01/10/2024: severe systolic dysfunction, LVEF 26%. NYHA Class III heart failure on optimal medical therapy."
        }
    }
    res = client.post("/api/v1/cds-services/medicare-crd-coverage-check", json=payload)
    assert res.status_code == 200
    cards = res.json()["cards"]
    assert len(cards) >= 1
    assert cards[0]["indicator"] == "info"
    assert "Approved" in cards[0]["summary"]
    assert len(cards[0]["links"]) >= 1

def test_hl7_da_vinci_crd_hook_order_signing_documentation_warning():
    payload = {
        "hook": "order-sign",
        "hookInstance": "550e8400-e29b-41d4-a716-446655440001",
        "context": {
            "userId": "Practitioner/1043256787",
            "patientId": "PT-CARDIOLOGY-102",
            "draftOrders": {}
        },
        "prefetch": {
            "clinicalNotes": "Acute anterior STEMI 10 days ago. LVEF 25%."
        }
    }
    res = client.post("/api/v1/cds-services/medicare-crd-coverage-check", json=payload)
    assert res.status_code == 200
    cards = res.json()["cards"]
    assert len(cards) >= 1
    assert cards[0]["indicator"] == "warning"
    assert "Documentation" in cards[0]["summary"]

def test_prometheus_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "carepolicyguard_adjudications_total" in res.text
    assert "carepolicyguard_active_device_sessions" in res.text
    assert res.headers["content-type"].startswith("text/plain")

def test_json_metrics_endpoint():
    res = client.get("/api/v1/metrics/json")
    assert res.status_code == 200
    data = res.json()
    assert "adjudications" in data
    assert "security" in data
    assert data["security"]["mfa_mandated"] is True
    assert "clinical_rules" in data

def test_database_engine_configuration():
    # Verify pool configuration is initialized
    assert engine is not None
    assert hasattr(engine, "pool")
