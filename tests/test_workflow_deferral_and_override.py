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
    """
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

    # Record clinical sign-off
    signoff_res = client.post(f"/api/v1/determination/{case_id}/sign-off", json={
        "signed_by": "Dr. Sarah Jenkins, MD, FACC",
        "clinician_npi": "1487293810",
        "clinician_credentials": "MD, FACC",
        "attestation_notes": "Clinical findings verified against source documentation under CMS-0057-F."
    })
    assert signoff_res.status_code == 200
    signoff_data = signoff_res.json()
    assert signoff_data["determination_stage"] == "FINAL"
    assert signoff_data["is_releasable"] is True
    assert signoff_data["signed_off_by"] == "Dr. Sarah Jenkins, MD, FACC"

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


