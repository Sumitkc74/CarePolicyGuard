import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_batch_adjudication_endpoint():
    batch_payload = {
        "batch_name": "Cardiology Clinic Morning Roster",
        "items": [
            {
                "patient_id": "PT-CARD-001",
                "policy_id": "NCD-20.4",
                "requested_procedure_code": "33249",
                "clinical_narrative": "68-year-old male with ischemic cardiomyopathy. Prior MI in 2021 (>3 years ago). Echo on 01/10/2024 shows severe systolic dysfunction with LVEF 28%. NYHA Class II symptoms with mild dyspnea on exertion. On guideline-directed medical therapy for >6 months with Carvedilol 25mg BID, Lisinopril 20mg daily, and Spironolactone 25mg daily. No cardiogenic shock, no terminal illness."
            },
            {
                "patient_id": "PT-CARD-002",
                "policy_id": "NCD-20.4",
                "requested_procedure_code": "33249",
                "clinical_narrative": "55-year-old female post acute STEMI 12 days ago. Underwent emergency stenting. Echo demonstrates LVEF 30%. NYHA Class II. Currently in hospital recovering from acute event."
            },
            {
                "patient_id": "PT-SLEEP-003",
                "policy_id": "LCD-L33829",
                "requested_procedure_code": "E0601",
                "clinical_narrative": "52-year-old male with chronic severe snoring and witnessed apneas. Prior in-person face-to-face evaluation by Dr. Stevens documented severe daytime somnolence (Epworth 16/24). Diagnostic polysomnography performed showing severe OSA with AHI 36.4 events/hr. Recommending auto-CPAP trial."
            }
        ]
    }

    response = client.post("/api/v1/adjudicate/batch", json=batch_payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_patients"] == 3
    assert data["batch_name"] == "Cardiology Clinic Morning Roster"
    assert len(data["results"]) == 3

    # Patient 1: Post-MI >40d, LVEF 28%, >90d GDMT -> APPROVED
    res1 = data["results"][0]
    assert res1["decision"] == "APPROVED"
    assert res1["calibrated_confidence"] >= 0.85
    assert not res1["abstention_status"]

    # Patient 2: Acute STEMI 12 days ago (<40d exclusion) -> DENIED
    res2 = data["results"][1]
    assert res2["decision"] == "DENIED"

    # Patient 3: OSA AHI 36.4, face-to-face -> APPROVED
    res3 = data["results"][2]
    assert res3["decision"] == "APPROVED"

    # Summary counts
    assert data["approved_count"] == 2
    assert data["denied_count"] == 1
    assert data["deferred_count"] == 0
    assert data["processing_time_ms"] > 0
