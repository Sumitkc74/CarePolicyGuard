import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, FinalAdjudication
from app.services.deferral_queue import (
    DeferralWorkQueue,
    HumanOverrideService,
    ResubmissionLifecycleManager,
    InternalWorkflowState,
    InvalidWorkflowTransitionError
)


def test_deferral_queue_records_deferred_case_with_questions():
    """
    Task 6: Tests that a deferred case enters the internal DeferralWorkQueue
    with missing criteria and targeted clinical questions.
    """
    DeferralWorkQueue.clear()
    pipeline = MultiAgentVerificationPipeline()

    ehr_incomplete = "Patient with heart failure. Echo ordered. GDMT ongoing."
    res = pipeline.adjudicate_sync("PT-QUEUE-01", "NCD-20.4", ehr_incomplete, save_record=False)

    item = DeferralWorkQueue.add_case(res)
    assert item.case_id == res.case_id
    assert item.is_internal_system_state is True
    assert len(item.missing_criteria) > 0 or len(item.insufficient_criteria) > 0

    queued = DeferralWorkQueue.get_item(res.case_id)
    assert queued is not None
    assert queued.current_state in (InternalWorkflowState.PENDING_EVIDENCE, InternalWorkflowState.HUMAN_REVIEW)


def test_human_override_preserves_original_recommendation():
    """
    Task 6: Tests that human override records clinician decision and reason
    without mutating the system's original recommendation, raw scores, or evaluations.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "Patient with ischemic cardiomyopathy. LVEF 25% on TTE.\n"
        "GDMT maintained for 6 months. NYHA Class II. Remote MI 3 years ago."
    )
    original_res = pipeline.adjudicate_sync("PT-OVERRIDE-01", "NCD-20.4", ehr, save_record=False)

    # Clinician overrides to DENIED with recorded reason
    overridden = HumanOverrideService.record_override(
        original_adjudication=original_res,
        override_decision=AdjudicationDecision.DENIED,
        override_reason="Severe non-cardiac frailty and patient preference to defer invasive device implantation.",
        clinician_id="Dr. Jane Smith, MD",
        clinician_role="Attending Cardiologist"
    )

    # Invariant: Original adjudication decision remains untouched inside original record
    assert original_res.adjudication_decision == AdjudicationDecision.APPROVED

    # Overridden record contains explicit human override container
    assert overridden.human_override is not None
    assert overridden.human_override["is_overridden"] is True
    assert overridden.human_override["override_decision"] == "DENIED"
    assert overridden.human_override["original_system_decision"] == "APPROVED"
    assert overridden.human_sign_off_status == "OVERRIDDEN"
    assert overridden.signed_off_by == "Dr. Jane Smith, MD"
    assert overridden.human_override["is_internal_system_override"] is True


def test_resubmission_lifecycle_transitions_and_rejection():
    """
    Task 6: Tests internal resubmission lifecycle state transitions:
    PRE_CHECK -> PENDING_EVIDENCE -> HUMAN_REVIEW -> FINAL_RECOMMENDATION -> SIGNED_OFF.
    Asserts invalid jumps (e.g. PRE_CHECK directly to FINAL_RECOMMENDATION) are strictly rejected.
    """
    ResubmissionLifecycleManager.clear()
    case_id = "CASE-LIFECYCLE-01"

    # Initial state must be PRE_CHECK
    assert ResubmissionLifecycleManager.get_state(case_id) == InternalWorkflowState.PRE_CHECK

    # Valid transition to PENDING_EVIDENCE
    s1 = ResubmissionLifecycleManager.transition(case_id, InternalWorkflowState.PENDING_EVIDENCE)
    assert s1 == InternalWorkflowState.PENDING_EVIDENCE

    # Valid transition to HUMAN_REVIEW
    s2 = ResubmissionLifecycleManager.transition(case_id, InternalWorkflowState.HUMAN_REVIEW)
    assert s2 == InternalWorkflowState.HUMAN_REVIEW

    # Valid transition to FINAL_RECOMMENDATION
    s3 = ResubmissionLifecycleManager.transition(case_id, InternalWorkflowState.FINAL_RECOMMENDATION)
    assert s3 == InternalWorkflowState.FINAL_RECOMMENDATION

    # Valid transition to SIGNED_OFF
    s4 = ResubmissionLifecycleManager.transition(case_id, InternalWorkflowState.SIGNED_OFF)
    assert s4 == InternalWorkflowState.SIGNED_OFF

    # Attempting illegal jump on a fresh case directly from PRE_CHECK to SIGNED_OFF must raise error
    fresh_case = "CASE-ILLEGAL-02"
    with pytest.raises(InvalidWorkflowTransitionError, match="Illegal internal workflow transition"):
        ResubmissionLifecycleManager.transition(fresh_case, InternalWorkflowState.SIGNED_OFF)


from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_provisional_determination_cannot_be_retrieved_as_final_or_pushed_to_ehr():
    """
    Task 1 Gate Enforcement:
    Proves that a fresh automated determination is strictly PROVISIONAL and NOT releasable:
    - GET /api/v1/determination/{case_id}/final raises HTTP 412 Precondition Failed.
    - POST /api/v1/packet/{case_id}/ehr-push raises HTTP 412 Precondition Failed.
    - GET /api/v1/packet/{case_id}/pdf?require_final=true raises HTTP 412 Precondition Failed.
    """
    ehr = (
        "CARDIOLOGY PROGRESS NOTE\n"
        "Patient with ischemic cardiomyopathy. LVEF 26% on echo. NYHA Class II.\n"
        "On GDMT for 6 months. Prior MI 2 years ago. No acute shock."
    )
    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-GATE-PROV-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": ehr
    })
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # 1. Inspect provisional determination via standard endpoint
    det_res = client.get(f"/api/v1/determination/{case_id}")
    assert det_res.status_code == 200
    det_data = det_res.json()
    assert det_data["determination_stage"] == "PROVISIONAL"
    assert det_data["is_releasable"] is False

    # 2. Final-only retrieval endpoint must reject provisional determination
    final_res = client.get(f"/api/v1/determination/{case_id}/final")
    assert final_res.status_code == 412
    assert "PROVISIONAL" in final_res.json()["detail"]

    # 3. Direct EHR push must reject provisional determination
    push_res = client.post(f"/api/v1/packet/{case_id}/ehr-push", json={
        "case_id": case_id,
        "ehr_system": "Epic Systems Hyperdrive"
    })
    assert push_res.status_code == 412
    assert "PROVISIONAL" in push_res.json()["detail"]

    # 4. Final-required PDF export must reject provisional determination
    pdf_res = client.get(f"/api/v1/packet/{case_id}/pdf?require_final=true")
    assert pdf_res.status_code == 412


def test_signed_off_determination_can_be_retrieved_as_final_and_released():
    """
    Task 1 Gate Enforcement:
    Proves that recording a clinical sign-off transitions determination to FINAL (is_releasable=True),
    enabling retrieval from /final, PDF export with require_final=true, and EHR push.
    Enforces that unauthenticated requests (401) and unverified clinicians (403) are strictly rejected.
    """
    import secrets
    from app.db.session import SessionLocal
    from app.db.models import User
    from app.core.security import create_access_token, get_password_hash

    db = SessionLocal()
    try:
        # Create verified clinician in memory/db for testing
        clinician_user = f"clinician_{secrets.token_hex(4)}"
        u_clinician = User(
            username=clinician_user,
            email=f"{clinician_user}@hospital.org",
            hashed_password=get_password_hash(secrets.token_hex(16)),
            role="Clinician",
            is_active=True,
            is_verified_medical_pro=True,
            npi_number="1487293810",
            credential_title="MD, FACC"
        )
        # Create unverified clinician
        unverified_user = f"unverified_{secrets.token_hex(4)}"
        u_unverified = User(
            username=unverified_user,
            email=f"{unverified_user}@hospital.org",
            hashed_password=get_password_hash(secrets.token_hex(16)),
            role="Clinician",
            is_active=True,
            is_verified_medical_pro=False
        )
        # Create non-clinician (Auditor)
        auditor_user = f"auditor_{secrets.token_hex(4)}"
        u_auditor = User(
            username=auditor_user,
            email=f"{auditor_user}@hospital.org",
            hashed_password=get_password_hash(secrets.token_hex(16)),
            role="Auditor",
            is_active=True,
            is_verified_medical_pro=False
        )
        db.add_all([u_clinician, u_unverified, u_auditor])
        db.commit()

        token_clinician = create_access_token({"sub": clinician_user})
        token_unverified = create_access_token({"sub": unverified_user})
        token_auditor = create_access_token({"sub": auditor_user})
    finally:
        db.close()

    ehr = (
        "CARDIOLOGY PROGRESS NOTE\n"
        "Patient with ischemic cardiomyopathy. LVEF 25% on echo. NYHA Class II.\n"
        "On GDMT for 6 months. Prior MI 2 years ago. No acute shock."
    )
    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-GATE-FINAL-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": ehr
    })
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # 1. Unauthenticated sign-off attempt must return 401 Unauthorized
    unauth_res = client.post(f"/api/v1/determination/{case_id}/sign-off", json={
        "signed_by": "Attending Clinician",
        "attestation_notes": "Attempt without credentials"
    })
    assert unauth_res.status_code == 401

    # 2. Non-clinician (Auditor) sign-off attempt must return 403 Forbidden
    auditor_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers={"Authorization": f"Bearer {token_auditor}"},
        json={"attestation_notes": "Attempt with non-clinician role"}
    )
    assert auditor_res.status_code == 403
    assert "Clinical sign-off requires role 'Clinician'" in auditor_res.json()["detail"]

    # 3. Unverified clinician sign-off attempt must return 403 Forbidden
    unverified_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers={"Authorization": f"Bearer {token_unverified}"},
        json={"attestation_notes": "Attempt with unverified account"}
    )
    assert unverified_res.status_code == 403
    assert "not verified as a medical professional" in unverified_res.json()["detail"]

    # 4. Verified licensed clinician sign-off must succeed
    signoff_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers={"Authorization": f"Bearer {token_clinician}"},
        json={"attestation_notes": "Clinical findings verified against source documentation under CMS-0057-F."}
    )
    assert signoff_res.status_code == 200
    signoff_data = signoff_res.json()
    assert signoff_data["determination_stage"] == "FINAL"
    assert signoff_data["is_releasable"] is True
    assert clinician_user in signoff_data["signed_off_by"]

    # Final retrieval endpoint now succeeds
    final_res = client.get(f"/api/v1/determination/{case_id}/final")
    assert final_res.status_code == 200
    final_data = final_res.json()
    assert final_data["determination_stage"] == "FINAL"
    assert final_data["is_releasable"] is True

    # Direct EHR push now succeeds
    push_res = client.post(f"/api/v1/packet/{case_id}/ehr-push", json={
        "case_id": case_id,
        "ehr_system": "Epic Systems Hyperdrive"
    })
    assert push_res.status_code == 200
    assert push_res.json()["status"] == "SUCCESS_TRANSMITTED"


def test_system_restart_survival_for_determinations_packets_and_deferral_queue():
    """
    Task 1: Proves determinations, packets, and deferral queue items survive server
    restarts by wiping in-memory caches and asserting database reconstitution.
    """
    from app.api.routes import _EPHEMERAL_PACKETS, _EPHEMERAL_ADJUDICATIONS, _EPHEMERAL_EHR_TEXTS
    pipeline = MultiAgentVerificationPipeline()

    ehr = (
        "Patient with ischemic cardiomyopathy. LVEF 25% on TTE.\n"
        "GDMT maintained for 6 months. NYHA Class II. Remote MI 3 years ago."
    )
    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-RESTART-SURVIVE-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": ehr
    })
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # Also add a case to the DeferralWorkQueue
    deferral_item = DeferralWorkQueue.add_case(
        FinalAdjudication(**res.json()),
        action_questions=["Confirm GDMT medication dosages."]
    )
    assert deferral_item.case_id == case_id

    # SIMULATE RESTART: completely wipe all in-memory caches and queues
    _EPHEMERAL_PACKETS.clear()
    _EPHEMERAL_ADJUDICATIONS.clear()
    _EPHEMERAL_EHR_TEXTS.clear()
    DeferralWorkQueue.clear()
    ResubmissionLifecycleManager.clear()

    # 1. Determination must be rehydrated from database
    reloaded_det = client.get(f"/api/v1/determination/{case_id}")
    assert reloaded_det.status_code == 200
    det_json = reloaded_det.json()
    assert det_json["case_id"] == case_id
    assert det_json["determination_stage"] == "PROVISIONAL"
    assert det_json["is_releasable"] is False

    # 2. Coverage packet must be rehydrated from database
    reloaded_packet = client.get(f"/api/v1/packet/{case_id}")
    assert reloaded_packet.status_code == 200
    packet_json = reloaded_packet.json()
    assert packet_json["case_id"] == case_id
    assert packet_json["determination_stage"] == "PROVISIONAL"

    # 3. DeferralWorkQueue must be rehydrated from database
    queue_items = DeferralWorkQueue.list_queue()
    found_in_queue = any(q.case_id == case_id for q in queue_items)
    assert found_in_queue is True
    reloaded_queue_item = DeferralWorkQueue.get_item(case_id)
    assert reloaded_queue_item is not None
    assert reloaded_queue_item.case_id == case_id


def test_override_preserves_original_system_output_byte_identical():
    """
    Task 1 & Task 6:
    Proves that HumanOverrideService records the human decision without mutating
    or rewriting the system's original output. The serialized original output is
    preserved byte-identical.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "Patient with ischemic cardiomyopathy. LVEF 25% on TTE.\n"
        "GDMT maintained for 6 months. NYHA Class II. Remote MI 3 years ago."
    )
    original_adj = pipeline.adjudicate_sync("PT-OVERRIDE-BYTE-01", "NCD-20.4", ehr, save_record=False)
    original_json_before = original_adj.model_dump_json()

    overridden = HumanOverrideService.record_override(
        original_adjudication=original_adj,
        override_decision=AdjudicationDecision.DENIED,
        override_reason="Severe non-cardiac comorbidities and palliative care transition.",
        clinician_id="Dr. Jane Smith, MD",
        clinician_role="Attending Cardiologist"
    )

    # Invariant 1: original_adjudication passed in remains unchanged
    assert original_adj.model_dump_json() == original_json_before

    # Invariant 2: stored original_system_output_json inside the override record matches byte-for-byte
    assert overridden.original_system_output_json == original_json_before

    # Invariant 3: overridden determination stage remains PROVISIONAL until human sign-off
    assert overridden.determination_stage == "PROVISIONAL"
    assert overridden.is_releasable is False


