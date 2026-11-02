"""
API Hardening & Limits Unit Tests.
Verifies:
1. Rejection of empty/whitespace EHR notes with 400 Bad Request.
2. Rejection of oversized payloads (> 500 KB) with 413 Payload Too Large.
3. Rejection of unexpected JSON schema types with 422 Unprocessable Entity.
4. Rejection of malformed policy IDs (400) and unknown policies (404).
5. Health checks (/health and /api/v1/health).
6. Operator metrics endpoint (/api/v1/metrics/operator) zero-PHI guarantees.
"""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_api_rejects_empty_and_whitespace_notes():
    """
    Submitting empty string or whitespace-only clinical notes must return 400 Bad Request.
    """
    resp_empty = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": ""
    })
    assert resp_empty.status_code == 400
    assert "cannot be empty" in resp_empty.json()["detail"]

    resp_ws = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "   \n\t   "
    })
    assert resp_ws.status_code == 400
    assert "cannot be empty" in resp_ws.json()["detail"]


def test_api_rejects_oversized_payloads():
    """
    Submitting narrative exceeding 500 KB must return 413 Payload Too Large.
    """
    oversized_text = "Clinical note content. " * 25000  # ~575 KB
    assert len(oversized_text.encode("utf-8")) > 500 * 1024

    resp = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-OVERSIZED",
        "policy_id": "NCD-20.4",
        "ehr_narrative": oversized_text
    })
    assert resp.status_code == 413
    assert "exceeds maximum allowed payload limit" in resp.json()["detail"]


def test_api_rejects_unexpected_types():
    """
    Passing invalid types (e.g. integer for string, string for dictionary) must return 422.
    """
    # options must be Dict[str, Any], passing string should fail schema validation
    resp = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Patient has LVEF 28% with NYHA Class II symptoms.",
        "options": "invalid-non-dict-type"
    })
    assert resp.status_code == 422

    # cpt_codes must be list of strings, passing integer should fail schema validation
    resp_cpt = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Patient has LVEF 28% with NYHA Class II symptoms.",
        "cpt_codes": 99213
    })
    assert resp_cpt.status_code == 422


def test_api_rejects_malformed_and_unknown_policy_ids():
    """
    Policy IDs with invalid characters return 400; non-existent policy IDs return 404.
    """
    valid_note = "Valid clinical narrative with LVEF 28% and NYHA Class II symptoms."

    # Malformed policy ID (spaces and special characters)
    resp_malformed = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NCD 20.4; DROP TABLE policies;",
        "ehr_narrative": valid_note
    })
    assert resp_malformed.status_code == 400
    assert "Malformed policy ID" in resp_malformed.json()["detail"]

    # Unknown policy ID
    resp_unknown = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-TEST-01",
        "policy_id": "NON-EXISTENT-POLICY-999",
        "ehr_narrative": valid_note
    })
    assert resp_unknown.status_code == 404
    assert "not found" in resp_unknown.json()["detail"].lower()


def test_health_endpoints():
    """
    Test both root and API v1 health endpoints.
    """
    resp_root = client.get("/health")
    assert resp_root.status_code == 200
    assert resp_root.json()["status"] == "healthy"

    resp_v1 = client.get("/api/v1/health")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["status"] == "healthy"


def test_operator_metrics_endpoint_zero_phi():
    """
    Test /api/v1/metrics/operator returns expected schema and zero PHI.
    """
    resp = client.get("/api/v1/metrics/operator")
    assert resp.status_code == 200
    data = resp.json()["operator_telemetry"]

    assert "total_evaluations" in data
    assert "decisions" in data
    assert "rates" in data
    assert "latency_ms" in data
    assert data["phi_safe"] is True

    # Assert no sensitive keys
    body_str = resp.text.lower()
    for sensitive in ["patient_name", "mrn", "ssn", "date_of_birth", "ehr_narrative"]:
        assert sensitive not in body_str

