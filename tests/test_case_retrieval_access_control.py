"""
Task 1: Determination and Case Record Retrieval Access Control Tests.
Verifies that:
1. Unauthenticated requests are rejected with HTTP 401 Unauthorized.
2. Unrelated authenticated users are denied with HTTP 404 (Anti-Enumeration Oracle Defense).
3. Case owners, signing clinicians, auditors, and admins are authorized (HTTP 200).
4. Human Sign-Off Gate is enforced (PROVISIONAL determinations return HTTP 412 on /final).
"""

import pytest
import secrets
from datetime import timedelta
from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.db.models import User, AdjudicationLog
from app.core.security import get_password_hash, create_access_token
from app.agents.pipeline import MultiAgentVerificationPipeline

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_access_control_users_and_cases():
    db = SessionLocal()
    pipeline = MultiAgentVerificationPipeline(db=db)

    # 1. Create test users in memory / DB with dynamically generated credentials
    owner_username = f"clinician_owner_{secrets.token_hex(4)}"
    signer_username = f"clinician_signer_{secrets.token_hex(4)}"
    stranger_username = f"clinician_stranger_{secrets.token_hex(4)}"
    auditor_username = f"auditor_{secrets.token_hex(4)}"
    admin_username = f"admin_{secrets.token_hex(4)}"

    user_owner = User(
        username=owner_username,
        email=f"{owner_username}@hospital.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Clinician",
        is_active=True,
        is_verified_medical_pro=True,
        npi_number="1234567890",
        credential_title="MD"
    )
    user_signer = User(
        username=signer_username,
        email=f"{signer_username}@hospital.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Clinician",
        is_active=True,
        is_verified_medical_pro=True,
        npi_number="1987654321",
        credential_title="MD"
    )
    user_stranger = User(
        username=stranger_username,
        email=f"{stranger_username}@hospital.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Clinician",
        is_active=True,
        is_verified_medical_pro=True,
        npi_number="1555555555",
        credential_title="DO"
    )
    user_auditor = User(
        username=auditor_username,
        email=f"{auditor_username}@medicare.cms.gov",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Auditor",
        is_active=True
    )
    user_admin = User(
        username=admin_username,
        email=f"{admin_username}@hospital.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Admin",
        is_active=True
    )

    db.add_all([user_owner, user_signer, user_stranger, user_auditor, user_admin])
    db.commit()
    db.refresh(user_owner)
    db.refresh(user_signer)
    db.refresh(user_stranger)
    db.refresh(user_auditor)
    db.refresh(user_admin)

    # 2. Adjudicate a case submitted by owner
    ehr_text = (
        "CARDIOLOGY PROGRESS NOTE\n"
        "68-year-old male with ischemic cardiomyopathy. LVEF 27% on 2D Echo.\n"
        "NYHA Class II dyspnea. Stable on guideline-directed medical therapy for >6 months.\n"
        "Prior MI 2 years ago. No cardiogenic shock."
    )
    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-ACCESS-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": ehr_text,
        "cpt_codes": ["33249"]
    })
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # Bind owner's user_id to the created record
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    log.user_id = user_owner.id
    db.commit()

    # 3. Create tokens in memory
    token_owner = create_access_token({"sub": user_owner.username, "role": user_owner.role, "uid": user_owner.id}, timedelta(minutes=30))
    token_signer = create_access_token({"sub": user_signer.username, "role": user_signer.role, "uid": user_signer.id}, timedelta(minutes=30))
    token_stranger = create_access_token({"sub": user_stranger.username, "role": user_stranger.role, "uid": user_stranger.id}, timedelta(minutes=30))
    token_auditor = create_access_token({"sub": user_auditor.username, "role": user_auditor.role, "uid": user_auditor.id}, timedelta(minutes=30))
    token_admin = create_access_token({"sub": user_admin.username, "role": user_admin.role, "uid": user_admin.id}, timedelta(minutes=30))

    data = {
        "case_id": case_id,
        "owner_id": user_owner.id,
        "signer_username": user_signer.username,
        "token_owner": token_owner,
        "token_signer": token_signer,
        "token_stranger": token_stranger,
        "token_auditor": token_auditor,
        "token_admin": token_admin,
    }
    db.close()
    return data


def test_unauthenticated_retrieval_rejected(setup_access_control_users_and_cases):
    """Proves unauthenticated requests are strictly rejected with HTTP 401."""
    case_id = setup_access_control_users_and_cases["case_id"]

    endpoints = [
        f"/api/v1/determination/{case_id}",
        f"/api/v1/determination/{case_id}/final",
        f"/api/v1/packet/{case_id}",
        f"/api/v1/packet/{case_id}/pdf",
        f"/api/v1/packet/{case_id}/fhir",
        f"/api/v1/audit/trail",
        f"/api/v1/audit/trail/export",
        f"/api/v1/audit-logs",
        f"/api/v1/audit-logs/{case_id}",
        f"/api/v1/deferral/queue",
        f"/api/v1/deferral/queue/{case_id}",
    ]

    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 401, f"Endpoint {ep} allowed unauthenticated access with status {res.status_code}"


def test_anti_enumeration_oracle_defense_for_unauthorized_user(setup_access_control_users_and_cases):
    """
    Proves anti-enumeration oracle defense: an unrelated authenticated clinician receives
    HTTP 404 with identical detail message to a non-existent case, preventing case enumeration.
    """
    case_id = setup_access_control_users_and_cases["case_id"]
    token_stranger = setup_access_control_users_and_cases["token_stranger"]
    headers = {"Authorization": f"Bearer {token_stranger}"}

    # 1. Existing case that stranger does not own or have rights to
    res_existing = client.get(f"/api/v1/determination/{case_id}", headers=headers)
    assert res_existing.status_code == 404
    assert res_existing.json()["detail"] == f"Case adjudication record '{case_id}' not found."

    # 2. Non-existent random case ID
    fake_case_id = f"CASE-NONEXISTENT-{secrets.token_hex(6).upper()}"
    res_fake = client.get(f"/api/v1/determination/{fake_case_id}", headers=headers)
    assert res_fake.status_code == 404
    assert res_fake.json()["detail"] == f"Case adjudication record '{fake_case_id}' not found."

    # Packet endpoint anti-enumeration check
    res_pkt_existing = client.get(f"/api/v1/packet/{case_id}", headers=headers)
    assert res_pkt_existing.status_code == 404
    assert res_pkt_existing.json()["detail"] == f"Case adjudication record '{case_id}' not found."


def test_authorized_roles_can_retrieve_case_record(setup_access_control_users_and_cases):
    """
    Proves authorized entities can retrieve determination and packet:
    - Case owner (200)
    - Auditor (200)
    - Admin (200)
    """
    case_id = setup_access_control_users_and_cases["case_id"]
    token_owner = setup_access_control_users_and_cases["token_owner"]
    token_auditor = setup_access_control_users_and_cases["token_auditor"]
    token_admin = setup_access_control_users_and_cases["token_admin"]

    for token, role_label in [
        (token_owner, "Case Owner"),
        (token_auditor, "Auditor"),
        (token_admin, "Admin")
    ]:
        headers = {"Authorization": f"Bearer {token}"}
        res_det = client.get(f"/api/v1/determination/{case_id}", headers=headers)
        assert res_det.status_code == 200, f"{role_label} failed to retrieve determination"
        assert res_det.json()["case_id"] == case_id

        res_pkt = client.get(f"/api/v1/packet/{case_id}", headers=headers)
        assert res_pkt.status_code == 200, f"{role_label} failed to retrieve packet"
        assert res_pkt.json()["case_id"] == case_id


def test_provisional_determination_rejected_by_final_endpoint(setup_access_control_users_and_cases):
    """
    Proves that even an authorized user (owner or auditor) is rejected with HTTP 412
    when attempting to retrieve a provisional determination via /final.
    """
    case_id = setup_access_control_users_and_cases["case_id"]
    token_owner = setup_access_control_users_and_cases["token_owner"]
    headers = {"Authorization": f"Bearer {token_owner}"}

    final_res = client.get(f"/api/v1/determination/{case_id}/final", headers=headers)
    assert final_res.status_code == 412
    assert "PROVISIONAL" in final_res.json()["detail"]


def test_signing_clinician_gains_retrieval_rights(setup_access_control_users_and_cases):
    """
    Proves that once a clinician signs off on a determination, they become an authorized
    signer and gain retrieval rights to the final released determination.
    """
    case_id = setup_access_control_users_and_cases["case_id"]
    token_signer = setup_access_control_users_and_cases["token_signer"]
    headers_signer = {"Authorization": f"Bearer {token_signer}"}

    # 1. Sign off the case
    signoff_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=headers_signer,
        json={"attestation_notes": "Clinical indications verified by attending physician."}
    )
    assert signoff_res.status_code == 200
    assert signoff_res.json()["determination_stage"] == "FINAL"

    # 2. Signer can now retrieve determination and final determination
    det_res = client.get(f"/api/v1/determination/{case_id}", headers=headers_signer)
    assert det_res.status_code == 200

    final_res = client.get(f"/api/v1/determination/{case_id}/final", headers=headers_signer)
    assert final_res.status_code == 200
    assert final_res.json()["determination_stage"] == "FINAL"
    assert final_res.json()["is_releasable"] is True
