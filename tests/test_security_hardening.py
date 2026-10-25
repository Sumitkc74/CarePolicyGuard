import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_owasp_security_headers_present():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "max-age=" in res.headers.get("Strict-Transport-Security", "")
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in res.headers.get("Permissions-Policy", "")

def test_da_vinci_pas_submit_approved():
    claim_payload = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-PAS-101"},
        "provider": {"reference": "Practitioner/NPI-1043256787"},
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [{"code": "33249", "display": "Insertion of ICD"}]
                }
            }
        ],
        "supportingInfo": [
            {
                "sequence": 1,
                "valueString": (
                    "History of remote myocardial infarction in 2021 (>3 years ago). "
                    "Diagnostic echocardiogram confirms severe LV systolic dysfunction with LVEF 26%. "
                    "NYHA Class III heart failure symptoms. Stable on optimal guideline-directed medical therapy "
                    "(carvedilol and lisinopril) for 6 months."
                )
            }
        ]
    }
    res = client.post("/api/v1/pas/submit", json=claim_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "ClaimResponse"
    assert data["use"] == "preauthorization"
    assert data["outcome"] == "complete"
    assert "Approved" in data["disposition"]
    assert data["preAuthRef"] is not None
    assert data["preAuthRef"].startswith("AUTH-CMS-")
    assert len(data["item"]) >= 1

def test_da_vinci_pas_submit_pended_deficiency():
    claim_payload = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-PAS-102"},
        "provider": {"reference": "Practitioner/NPI-1043256787"},
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [{"code": "33249", "display": "Insertion of ICD"}]
                }
            }
        ],
        "supportingInfo": [
            {
                "sequence": 1,
                "valueString": "Acute STEMI 10 days ago. LVEF 25%."
            }
        ]
    }
    res = client.post("/api/v1/pas/submit", json=claim_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "ClaimResponse"
    assert data["outcome"] == "pended"
    assert "Pended" in data["disposition"]
    assert data["preAuthRef"] is None

def test_fhir_audit_event_bundle_export():
    # 1. Trigger an adjudication to ensure a record exists
    client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-AUDIT-TEST",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Remote MI in 2020. LVEF 28%. NYHA Class III. On optimal medical therapy for 6 months."
    })

    # 2. Query the FHIR AuditEvent bundle
    res = client.get("/api/v1/audit/trail/fhir-audit-event")
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "Bundle"
    assert data["type"] == "collection"
    assert "entry" in data
    assert data["total"] >= 1
    first_entry = data["entry"][0]["resource"]
    assert first_entry["resourceType"] == "AuditEvent"
    assert first_entry["action"] == "E"
    assert "entity" in first_entry
    # Check that SHA-256 seal is present in entity details
    has_seal = any(
        any(d.get("type") == "sha256" for d in e.get("detail", []))
        for e in first_entry["entity"]
    )
    assert has_seal is True

