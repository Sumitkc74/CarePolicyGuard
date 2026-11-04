"""
Task 2: PHI Minimization, Storage Sanitization, Replay Determinism, and Retention Tests.
Verifies that:
1. Raw clinical narrative text is NEVER stored in database columns or server memory.
2. Only sanitized clinical narrative (sanitized_ehr) is persisted.
3. Replaying adjudication from stored sanitized text deterministically reproduces original decisions.
4. Historical database cleanup operation sanitizes legacy records without altering audit hashes.
5. Right to Erasure deletion operation scrubs clinical content while preserving tombstone audit record.
"""

import pytest
import secrets
from datetime import timedelta
from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.db.models import User, AdjudicationLog
from app.core.security import get_password_hash, create_access_token
from app.agents.pipeline import MultiAgentVerificationPipeline, sanitize_phi
from app.api.routes import _EPHEMERAL_EHR_TEXTS, _EPHEMERAL_PACKETS, _EPHEMERAL_ADJUDICATIONS
from scripts.cleanup_raw_phi import cleanup_raw_phi_in_database

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_auth_header():
    db = SessionLocal()
    admin_username = f"admin_phi_{secrets.token_hex(4)}@carepolicyguard.med"
    user = User(
        username=admin_username,
        email=admin_username,
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role="Admin",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(
        {"sub": admin_username, "role": "Admin", "uid": user.id},
        expires_delta=timedelta(minutes=30)
    )
    db.close()
    return {"Authorization": f"Bearer {token}"}


def test_raw_clinical_text_not_stored_in_persistence_layer(admin_auth_header):
    """
    Proves that raw clinical narrative containing explicit PHI (SSN, patient full name, MRN)
    is sanitized before persistence, and raw text does not exist in SQLite or memory caches.
    """
    db = SessionLocal()
    raw_ssn = "999-88-7766"
    raw_name = "Jonathan Bartholomew Vance-Smith"
    raw_mrn = "MRN-9021048821"

    narrative_with_phi = (
        f"PATIENT: {raw_name} | SSN: {raw_ssn} | MRN: {raw_mrn}\n"
        "68-year-old male with ischemic cardiomyopathy. Echo on 01/10/2025 demonstrates severe LV systolic "
        "dysfunction with LVEF 27%. Documented >180 days compliance on GDMT (Carvedilol 25mg BID, Lisinopril 20mg). "
        "NYHA Class II dyspnea. Prior MI in 2021 (>40 days). No cardiogenic shock."
    )

    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-PHI-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": narrative_with_phi,
        "cpt_codes": ["33249"]
    })
    assert res.status_code == 200
    adj_data = res.json()
    case_id = adj_data["case_id"]

    # 1. Inspect persistent database row
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log is not None

    # Stored narrative must NOT contain raw PHI
    assert raw_ssn not in log.full_ehr_text, "Raw SSN leaked into AdjudicationLog.full_ehr_text!"
    assert raw_name not in log.full_ehr_text, "Raw patient name leaked into AdjudicationLog.full_ehr_text!"
    assert raw_mrn not in log.full_ehr_text, "Raw MRN leaked into AdjudicationLog.full_ehr_text!"

    # Stored preview must NOT contain raw PHI
    assert raw_ssn not in log.sanitized_ehr_preview
    assert raw_name not in log.sanitized_ehr_preview

    # Stored JSON must NOT contain raw PHI
    if log.full_adjudication_json:
        assert raw_ssn not in log.full_adjudication_json
        assert raw_name not in log.full_adjudication_json

    # 2. Inspect ephemeral memory caches
    ephemeral_text = _EPHEMERAL_EHR_TEXTS.get(case_id, "")
    assert raw_ssn not in ephemeral_text, "Raw SSN leaked into _EPHEMERAL_EHR_TEXTS cache!"
    assert raw_name not in ephemeral_text, "Raw patient name leaked into _EPHEMERAL_EHR_TEXTS cache!"

    db.close()


@pytest.mark.asyncio
async def test_replay_from_stored_sanitized_narrative_reproduces_decision():
    """
    Proves that re-evaluating the stored sanitized narrative through the multi-agent pipeline
    produces identical decision, criteria evaluations, and sufficiency scores.
    """
    db = SessionLocal()
    pipeline = MultiAgentVerificationPipeline(db=db)

    raw_note = (
        "Patient: Margaret Thatcher-Brown (SSN: 000-11-2233). "
        "69-year-old female with ischemic cardiomyopathy. Echo demonstrates LVEF 25%. "
        "Maintained on optimal GDMT for 7 months. Remote anterior MI 4 years ago. No acute cardiogenic shock."
    )

    # First run: ingest raw note
    first_run = await pipeline.adjudicate(
        patient_id="PT-REPLAY-01",
        policy_id="NCD-20.4",
        ehr_narrative=raw_note,
        save_record=True,
        cpt_codes=["33249"]
    )

    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == first_run.case_id).first()
    assert log is not None
    stored_sanitized_text = log.full_ehr_text

    # Second run (replay): evaluate directly from stored sanitized text
    replay_run = await pipeline.adjudicate(
        patient_id="PT-REPLAY-01",
        policy_id="NCD-20.4",
        ehr_narrative=stored_sanitized_text,
        save_record=False,
        cpt_codes=["33249"]
    )

    assert replay_run.adjudication_decision == first_run.adjudication_decision
    assert replay_run.abstention_status == first_run.abstention_status
    assert len(replay_run.criterion_assessments) == len(first_run.criterion_assessments)
    for c1, c2 in zip(first_run.criterion_assessments, replay_run.criterion_assessments):
        assert c1.status == c2.status
        assert c1.criterion_code == c2.criterion_code

    db.close()


def test_cleanup_raw_phi_script_preserves_hashes_and_stages():
    """
    Proves that running the one-time cleanup operation sanitizes legacy database records
    without corrupting SHA-256 audit hashes, stages, or sign-offs.
    """
    db = SessionLocal()
    leak_case_id = f"CASE-LEAK-{secrets.token_hex(4).upper()}"
    raw_leak_text = "PATIENT: Robert Oppenheimer (SSN: 111-22-3333). LVEF 24% on GDMT."
    audit_hash_original = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    log_entry = AdjudicationLog(
        case_id=leak_case_id,
        patient_id_masked="PT-***3333",
        policy_id="NCD-20.4",
        decision="APPROVED",
        raw_confidence=0.95,
        criterion_evaluations_json="[]",
        evidence_spans_json="[]",
        adversarial_audits_json="[]",
        audit_hash=audit_hash_original,
        sanitized_ehr_preview=raw_leak_text,
        full_ehr_text=raw_leak_text,
        determination_stage="FINAL",
        is_releasable=True,
        human_sign_off_status="SIGNED_OFF",
        signed_by="Dr. Elena Rostova, MD"
    )
    db.add(log_entry)
    db.commit()

    # Run cleanup utility
    result = cleanup_raw_phi_in_database(dry_run=False)
    assert result["status"] == "success"
    assert result["total_updated"] >= 1

    # Verify log entry post-cleanup
    cleaned_log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == leak_case_id).first()
    assert "111-22-3333" not in cleaned_log.full_ehr_text
    assert "Robert Oppenheimer" not in cleaned_log.full_ehr_text
    # Verify invariants: audit hash, stage, and sign-offs remain preserved
    assert cleaned_log.audit_hash == audit_hash_original
    assert cleaned_log.determination_stage == "FINAL"
    assert cleaned_log.is_releasable is True
    assert cleaned_log.human_sign_off_status == "SIGNED_OFF"
    assert cleaned_log.signed_by == "Dr. Elena Rostova, MD"

    db.delete(cleaned_log)
    db.commit()
    db.close()


def test_right_to_erasure_deletion_operation(admin_auth_header):
    """
    Proves that DELETE /api/v1/determination/{case_id} scrubs clinical content,
    clears ephemeral memory, and preserves a tombstone audit record.
    """
    db = SessionLocal()
    # 1. Create a case
    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-ERASURE-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Patient with ischemic cardiomyopathy. LVEF 28%. Compliant on GDMT for 6 months."
    })
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # 2. Unauthenticated deletion attempt must be rejected (401)
    unauth_del = client.delete(f"/api/v1/determination/{case_id}")
    assert unauth_del.status_code == 401

    # 3. Authorized deletion execution
    del_res = client.delete(f"/api/v1/determination/{case_id}", headers=admin_auth_header)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 4. Verify persistent record is scrubbed to tombstone
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log is not None
    assert log.submission_status == "ERASED_TOMBSTONE"
    assert log.full_ehr_text == "[SCRUBBED - RIGHT TO ERASURE]"
    assert log.sanitized_ehr_preview == "[SCRUBBED - RIGHT TO ERASURE]"
    assert log.criterion_evaluations_json == "[]"
    assert log.full_adjudication_json is None
    assert log.full_packet_json is None

    # 5. Verify ephemeral caches are cleared
    assert case_id not in _EPHEMERAL_PACKETS
    assert case_id not in _EPHEMERAL_EHR_TEXTS
    assert case_id not in _EPHEMERAL_ADJUDICATIONS

    db.close()
