import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.db.models import User, AdjudicationLog
from app.core.security import get_password_hash, create_access_token

client = TestClient(app)

@pytest.fixture
def test_users_and_cases():
    db = SessionLocal()
    try:
        # Create Clinician 1
        c1 = db.query(User).filter(User.username == "test_clinician_1").first()
        if not c1:
            c1 = User(
                username="test_clinician_1",
                email="clinician1@test.hospital.org",
                hashed_password=get_password_hash("TestPass123!"),
                role="Clinician",
                is_active=True
            )
            db.add(c1)
            db.commit()
            db.refresh(c1)

        # Create Clinician 2
        c2 = db.query(User).filter(User.username == "test_clinician_2").first()
        if not c2:
            c2 = User(
                username="test_clinician_2",
                email="clinician2@test.hospital.org",
                hashed_password=get_password_hash("TestPass123!"),
                role="Clinician",
                is_active=True
            )
            db.add(c2)
            db.commit()
            db.refresh(c2)

        # Create Auditor
        auditor = db.query(User).filter(User.username == "test_auditor_user").first()
        if not auditor:
            auditor = User(
                username="test_auditor_user",
                email="auditor@test.cms.gov",
                hashed_password=get_password_hash("TestPass123!"),
                role="Auditor",
                is_active=True
            )
            db.add(auditor)
            db.commit()
            db.refresh(auditor)

        # Case handled by Clinician 1
        case_c1 = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == "CASE-TEST-CLINICIAN-1").first()
        if not case_c1:
            case_c1 = AdjudicationLog(
                case_id="CASE-TEST-CLINICIAN-1",
                patient_id_masked="PT-***1111",
                policy_id="NCD-20.4",
                decision="APPROVED",
                calibrated_confidence=0.95,
                raw_confidence=0.95,
                criterion_evaluations_json="[]",
                evidence_spans_json="[]",
                adversarial_audits_json="[]",
                audit_hash="a" * 64,
                sanitized_ehr_preview="Clinician 1 clinical case notes",
                user_id=c1.id,
                signed_by="test_clinician_1",
                submission_status="SUBMITTED_TO_PAYER"
            )
            db.add(case_c1)

        # Case handled by Clinician 2
        case_c2 = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == "CASE-TEST-CLINICIAN-2").first()
        if not case_c2:
            case_c2 = AdjudicationLog(
                case_id="CASE-TEST-CLINICIAN-2",
                patient_id_masked="PT-***2222",
                policy_id="NCD-20.33",
                decision="DENIED",
                calibrated_confidence=0.88,
                raw_confidence=0.88,
                criterion_evaluations_json="[]",
                evidence_spans_json="[]",
                adversarial_audits_json="[]",
                audit_hash="b" * 64,
                sanitized_ehr_preview="Clinician 2 clinical case notes",
                user_id=c2.id,
                signed_by="test_clinician_2",
                submission_status="SUBMITTED_TO_PAYER"
            )
            db.add(case_c2)

        db.commit()
        return {
            "c1_id": c1.id,
            "c2_id": c2.id,
            "c1_case": "CASE-TEST-CLINICIAN-1",
            "c2_case": "CASE-TEST-CLINICIAN-2"
        }
    finally:
        db.close()

def test_clinician_only_sees_their_own_cases(test_users_and_cases):
    # Clinician 1 Token
    c1_token = create_access_token(
        {"sub": "test_clinician_1", "role": "Clinician", "uid": test_users_and_cases["c1_id"]},
        expires_delta=timedelta(minutes=15)
    )
    headers_c1 = {"Authorization": f"Bearer {c1_token}"}

    res_c1 = client.get("/api/v1/audit-logs", headers=headers_c1)
    assert res_c1.status_code == 200
    logs_c1 = res_c1.json()
    case_ids = [l["case_id"] for l in logs_c1]

    # Must contain Clinician 1's case, must NOT contain Clinician 2's case
    assert test_users_and_cases["c1_case"] in case_ids
    assert test_users_and_cases["c2_case"] not in case_ids

def test_auditor_sees_all_system_cases(test_users_and_cases):
    # Auditor Token
    auditor_token = create_access_token(
        {"sub": "test_auditor_user", "role": "Auditor"},
        expires_delta=timedelta(minutes=15)
    )
    headers_auditor = {"Authorization": f"Bearer {auditor_token}"}

    res_auditor = client.get("/api/v1/audit-logs", headers=headers_auditor)
    assert res_auditor.status_code == 200
    logs_auditor = res_auditor.json()
    case_ids = [l["case_id"] for l in logs_auditor]

    # Auditor must see both cases
    assert test_users_and_cases["c1_case"] in case_ids
    assert test_users_and_cases["c2_case"] in case_ids

def test_clinician_cannot_inspect_other_clinician_case(test_users_and_cases):
    # Clinician 1 attempts to inspect Clinician 2's case
    c1_token = create_access_token(
        {"sub": "test_clinician_1", "role": "Clinician", "uid": test_users_and_cases["c1_id"]},
        expires_delta=timedelta(minutes=15)
    )
    headers_c1 = {"Authorization": f"Bearer {c1_token}"}

    # Inspect own case -> Success (200)
    own_res = client.get(f"/api/v1/audit-logs/{test_users_and_cases['c1_case']}", headers=headers_c1)
    assert own_res.status_code == 200

    # Inspect other clinician's case -> Forbidden (403)
    other_res = client.get(f"/api/v1/audit-logs/{test_users_and_cases['c2_case']}", headers=headers_c1)
    assert other_res.status_code == 403
    assert "HIPAA Minimum Necessary" in other_res.json()["detail"]

