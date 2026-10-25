import pytest
from fastapi.testclient import TestClient
from main import app
from app.agents.criteria_evaluator import CriteriaEvaluationAgent, evaluate_patient_against_policy
from app.db.session import SessionLocal
from app.db.models import MedicarePolicy

client = TestClient(app)

def test_ncd20_7_criteria_evaluation_approved():
    narrative = (
        "Diagnostic carotid duplex and CTA confirm 85% severe right internal carotid artery stenosis. "
        "Patient experienced a transient ischemic attack (TIA) with left facial droop and arm weakness 2 months ago. "
        "High risk for open CEA due to prior radical neck radiation and hostile neck anatomy. "
        "Order: Percutaneous transluminal angioplasty with FDA-approved carotid stent and distal embolic protection device (EPD) filter deployment."
    )
    result = evaluate_patient_against_policy(narrative, "NCD-20.7")
    assert result["determination"] == "APPROVED"
    assert result["confidence_score"] >= 0.90
    assert len(result["missing_criteria"]) == 0

def test_ncd20_7_criteria_evaluation_warning_missing_epd():
    narrative = (
        "Carotid duplex shows 80% stenosis. Patient had TIA 1 month ago. "
        "High risk for CEA due to hostile neck."
        # Missing embolic protection device (EPD)
    )
    result = evaluate_patient_against_policy(narrative, "NCD-20.7")
    assert result["determination"] == "WARNING"
    assert any("Embolic Protection Device" in c for c in result["missing_criteria"])

def test_dtr_questionnaire_endpoint_ncd20_4():
    res = client.get("/api/v1/dtr/questionnaire/NCD-20.4")
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "Questionnaire"
    assert data["policy_id"] == "NCD-20.4"
    assert len(data["item"]) >= 4
    link_ids = [item["linkId"] for item in data["item"]]
    assert "crit_lvef" in link_ids
    assert "crit_nyha" in link_ids

def test_dtr_questionnaire_endpoint_ncd20_7():
    res = client.get("/api/v1/dtr/questionnaire/NCD-20.7")
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "Questionnaire"
    assert data["policy_id"] == "NCD-20.7"
    link_ids = [item["linkId"] for item in data["item"]]
    assert "crit_carotid_stenosis" in link_ids
    assert "crit_epd_deployment" in link_ids

def test_dtr_populate_operation_completed():
    payload = {
        "policy_id": "NCD-20.4",
        "patient_id": "PT-CARDIOLOGY-101",
        "clinical_narrative": (
            "History of remote myocardial infarction in 2021 (>3 years ago). "
            "TTE on 01/10/2024 reveals severe LV systolic dysfunction with LVEF 26%. "
            "NYHA Class III heart failure. Maintained on guideline-directed medical therapy "
            "(carvedilol and lisinopril) for 6 months."
        )
    }
    res = client.post("/api/v1/dtr/populate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "QuestionnaireResponse"
    assert data["status"] == "completed"
    assert data["completeness_percent"] >= 80.0
    answered_links = [item["linkId"] for item in data["items"] if item["answered"]]
    assert "crit_lvef" in answered_links
    assert "crit_nyha" in answered_links

def test_dtr_populate_operation_in_progress():
    payload = {
        "policy_id": "NCD-20.7",
        "patient_id": "PT-NEURO-205",
        "clinical_narrative": "Carotid duplex shows 85% stenosis. Patient is asymptomatic."
        # Missing CEA risk factors and EPD
    }
    res = client.post("/api/v1/dtr/populate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "in-progress"
    assert data["completeness_percent"] < 100.0

def test_crd_hook_carotid_selection():
    payload = {
        "hook": "order-sign",
        "hookInstance": "550e8400-e29b-41d4-a716-446655440099",
        "context": {
            "userId": "Practitioner/1043256787",
            "patientId": "PT-NEURO-205",
            "draftOrders": {
                "resourceType": "DeviceRequest",
                "codeCodeableConcept": {
                    "coding": [{"code": "37215", "display": "Transcatheter placement of intravascular stent, cervical carotid artery"}]
                }
            }
        },
        "prefetch": {
            "clinicalNotes": (
                "Carotid duplex confirms 85% internal carotid artery stenosis. TIA 2 months ago. "
                "High risk for CEA due to hostile neck anatomy. FDA-approved carotid stent and embolic protection device (EPD) filter planned."
            )
        }
    }
    res = client.post("/api/v1/cds-services/medicare-crd-coverage-check", json=payload)
    assert res.status_code == 200
    cards = res.json()["cards"]
    assert len(cards) >= 1
    assert cards[0]["indicator"] == "info"
    assert "NCD-20.7" in cards[0]["summary"]

