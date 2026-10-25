import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_teer_mitraclip_policy_adjudication():
    # 1. Qualifying TEER Case
    qualifying_note = """
    77-year-old male with severe dyspnea on minimal exertion (NYHA Class III) due to degenerative mitral valve disease.
    Comprehensive transthoracic and transesophageal echocardiography confirms Grade 4+ severe mitral regurgitation with posterior leaflet flail.
    Evaluated by the Multidisciplinary Heart Team including Dr. Chen (Cardiothoracic Surgery) and Dr. Adams (Interventional Cardiology).
    Calculated STS operative mortality score is 9.4%, establishing prohibitive surgical risk for conventional open sternotomy.
    Heart Team consensus recommendation is for percutaneous transcatheter edge-to-edge repair (TEER / MitraClip).
    """

    resp = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-VALVE-01",
        "policy_id": "NCD-20.33",
        "ehr_narrative": qualifying_note,
        "cpt_codes": ["33418"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["adjudication_decision"] == "APPROVED"
    assert data["calibrated_aggregate_confidence"] >= 0.85
    assert not data["abstention_status"]

    # 2. Non-qualifying: Mild MR fails criteria
    mild_note = """
    62-year-old male presenting for routine cardiac checkup.
    Recent echocardiogram documents mild mitral regurgitation (Grade 1+) with normal leaflet motion.
    Patient is asymptomatic. Considering valve intervention.
    """

    resp2 = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-VALVE-02",
        "policy_id": "NCD-20.33",
        "ehr_narrative": mild_note,
        "cpt_codes": ["33418"]
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["adjudication_decision"] == "DENIED" or data2["abstention_status"]

