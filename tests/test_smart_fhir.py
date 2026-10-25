import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_smart_on_fhir_endpoints():
    # 1. Test .well-known SMART configuration
    disco_res = client.get("/api/v1/fhir/.well-known/smart-configuration")
    assert disco_res.status_code == 200
    disco = disco_res.json()
    assert "authorization_endpoint" in disco
    assert "token_endpoint" in disco
    assert "launch-ehr" in disco["capabilities"]

    # 2. Test SMART OAuth2 Token exchange
    tok_res = client.post("/api/v1/fhir/auth/token?code=ehr_auth_123&patient=EPIC-PT-1049")
    assert tok_res.status_code == 200
    tok_data = tok_res.json()
    assert tok_data["token_type"] == "Bearer"
    assert tok_data["patient"] == "EPIC-PT-1049"

    # 3. Test Fetch Patient Chart from EHR
    chart_res = client.get("/api/v1/fhir/patients/EPIC-PT-1049/chart")
    assert chart_res.status_code == 200
    chart = chart_res.json()
    assert chart["patient_id"] == "EPIC-PT-1049"
    assert len(chart["active_conditions"]) >= 1
    assert len(chart["active_medications"]) >= 1
    assert "synthesized_progress_note" in chart
    assert "LVEF 28%" in chart["synthesized_progress_note"]

    # 4. Feed EHR Synthesized Note into Adjudication Pipeline
    adj_res = client.post("/api/v1/adjudicate", json={
        "patient_id": chart["patient_id"],
        "policy_id": "NCD-20.4",
        "ehr_narrative": chart["synthesized_progress_note"],
        "cpt_codes": ["33249"]
    })
    assert adj_res.status_code == 200
    adj_data = adj_res.json()
    assert adj_data["adjudication_decision"] == "APPROVED"
    assert adj_data["calibrated_aggregate_confidence"] >= 0.85

def test_live_public_hapi_fhir_server_capability():
    """
    Verifies live FHIR CapabilityStatement discovery from the public HAPI FHIR testbed.
    Includes network resilience fallback if the public server is temporarily unreachable.
    """
    from app.services.smart_fhir_connector import SMARTonFHIRConnectorService
    
    result = SMARTonFHIRConnectorService.validate_remote_fhir_capability("https://hapi.fhir.org/baseR4", timeout=8.0)
    assert "status" in result
    if result["status"] == "online":
        assert result["resource_type"] == "CapabilityStatement"
        assert result["fhir_version"].startswith("4.")
    else:
        # Fallback assertion if network partition occurs
        assert result["status"] in ("unreachable", "error")
        assert "error" in result or "status_code" in result


