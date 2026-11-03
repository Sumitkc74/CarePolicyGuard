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

