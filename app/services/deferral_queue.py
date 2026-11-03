from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.schemas.contracts import FinalAdjudication, AdjudicationDecision, DeterminationStatus
from app.core.security import compute_audit_hash


class InternalWorkflowState(str, Enum):
    """
    Internal-only clinical decision support workflow lifecycle states.
    Strictly isolated from external payer claims, EDI gateways, or simulated payer status loops.
    """
    PRE_CHECK = "PRE_CHECK"
    PENDING_EVIDENCE = "PENDING_EVIDENCE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FINAL_RECOMMENDATION = "FINAL_RECOMMENDATION"
    SIGNED_OFF = "SIGNED_OFF"


class InvalidWorkflowTransitionError(Exception):
    """Raised when an illegal workflow state transition is attempted."""
    pass


class DeferralQueueItem(BaseModel):
    case_id: str
    patient_id_masked: str
    policy_id: str
    policy_title: str
    provisional_decision: str
    missing_criteria: List[str]
    insufficient_criteria: List[str]
    action_required_questions: List[str]
    audit_hash: str
    created_at: str
    current_state: InternalWorkflowState = InternalWorkflowState.PRE_CHECK
    is_internal_system_state: bool = True
    notice: str = "Internal work queue only; no payer transmission has occurred."


class DeferralWorkQueue:
    """
    In-Memory & Persistent Deferral Work Queue.
    Tracks cases requiring clinical review, supplementary records, or clinician attestation.
    """

    _QUEUE: Dict[str, DeferralQueueItem] = {}

    @classmethod
    def add_case(
        cls,
        adjudication: FinalAdjudication,
        action_questions: Optional[List[str]] = None
    ) -> DeferralQueueItem:
        missing = [c.criterion_code for c in adjudication.criterion_assessments if c.status == DeterminationStatus.NOT_MET and not c.is_exclusion]
        insufficient = [c.criterion_code for c in adjudication.criterion_assessments if c.status == DeterminationStatus.INSUFFICIENT_EVIDENCE and not c.is_exclusion]
        questions = action_questions or adjudication.action_required_questions or []

        item = DeferralQueueItem(
            case_id=adjudication.case_id,
            patient_id_masked=adjudication.patient_id_masked,
            policy_id=adjudication.policy_id,
            policy_title=adjudication.policy_title,
            provisional_decision=adjudication.adjudication_decision.value,
            missing_criteria=missing,
            insufficient_criteria=insufficient,
            action_required_questions=questions,
            audit_hash=adjudication.audit_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            current_state=InternalWorkflowState.PENDING_EVIDENCE if insufficient or missing else InternalWorkflowState.HUMAN_REVIEW
        )
        cls._QUEUE[adjudication.case_id] = item
        return item

    @classmethod
    def list_queue(cls) -> List[DeferralQueueItem]:
        return list(cls._QUEUE.values())

    @classmethod
    def get_item(cls, case_id: str) -> Optional[DeferralQueueItem]:
        return cls._QUEUE.get(case_id)

    @classmethod
    def clear(cls) -> None:
        cls._QUEUE.clear()


class HumanOverrideService:
    """
    Human Override & Clinical Attestation Service.
    Enforces the core transparency invariant:
    A human override can change the recommendation, but it NEVER overwrites
    or mutates the system's original output, raw scores, or algorithmic assessments.
    """

    @classmethod
    def record_override(
        cls,
        original_adjudication: FinalAdjudication,
        override_decision: AdjudicationDecision,
        override_reason: str,
        clinician_id: str,
        clinician_role: str = "Attending Physician"
    ) -> FinalAdjudication:
        if not override_reason or len(override_reason.strip()) < 10:
            raise ValueError("Human override requires an explicit clinical reason of at least 10 characters.")

        timestamp_str = datetime.now(timezone.utc).isoformat()

        # Clone original adjudication without modifying its historical determinations
        adj_dict = original_adjudication.model_dump()

        override_payload = {
            "is_overridden": True,
            "override_decision": override_decision.value,
            "original_system_decision": original_adjudication.adjudication_decision.value,
            "override_reason": override_reason.strip(),
            "clinician_id": clinician_id,
            "clinician_role": clinician_role,
            "overridden_at": timestamp_str,
            "is_internal_system_override": True,
            "payer_transmission_status": "NONE_INTERNAL_ONLY"
        }

        # Update copy with override container while keeping original fields intact
        adj_dict["human_override"] = override_payload
        adj_dict["human_sign_off_status"] = "OVERRIDDEN"
        adj_dict["signed_off_by"] = clinician_id
        adj_dict["signed_off_at"] = timestamp_str

        # Re-compute cryptographic audit seal certifying the override event
        new_audit_hash = compute_audit_hash(
            patient_id_masked=original_adjudication.patient_id_masked,
            policy_id=original_adjudication.policy_id,
            decision=override_decision.value,
            calibrated_confidence=original_adjudication.calibrated_aggregate_confidence,
            criterion_assessments=[c.model_dump() for c in original_adjudication.criterion_assessments],
            evidence_spans=[s.model_dump() for c in original_adjudication.criterion_assessments for s in c.verified_spans],
            timestamp=datetime.now(timezone.utc)
        )
        adj_dict["audit_hash"] = new_audit_hash

        updated = FinalAdjudication(**adj_dict)
        return updated


class ResubmissionLifecycleManager:
    """
    Resubmission & Case Lifecycle Manager.
    Allowed transition paths:
    PRE_CHECK -> PENDING_EVIDENCE -> HUMAN_REVIEW -> FINAL_RECOMMENDATION -> SIGNED_OFF
    or PRE_CHECK -> HUMAN_REVIEW -> FINAL_RECOMMENDATION -> SIGNED_OFF
    """

    ALLOWED_TRANSITIONS = {
        InternalWorkflowState.PRE_CHECK: {
            InternalWorkflowState.PENDING_EVIDENCE,
            InternalWorkflowState.HUMAN_REVIEW
        },
        InternalWorkflowState.PENDING_EVIDENCE: {
            InternalWorkflowState.HUMAN_REVIEW
        },
        InternalWorkflowState.HUMAN_REVIEW: {
            InternalWorkflowState.FINAL_RECOMMENDATION,
            InternalWorkflowState.SIGNED_OFF
        },
        InternalWorkflowState.FINAL_RECOMMENDATION: {
            InternalWorkflowState.SIGNED_OFF
        },
        InternalWorkflowState.SIGNED_OFF: set()
    }

    _CASE_STATES: Dict[str, InternalWorkflowState] = {}

    @classmethod
    def get_state(cls, case_id: str) -> InternalWorkflowState:
        return cls._CASE_STATES.get(case_id, InternalWorkflowState.PRE_CHECK)

    @classmethod
    def transition(cls, case_id: str, target_state: InternalWorkflowState) -> InternalWorkflowState:
        current = cls.get_state(case_id)
        if target_state == current:
            return current

        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        if target_state not in allowed:
            raise InvalidWorkflowTransitionError(
                f"Illegal internal workflow transition for case {case_id}: cannot transition directly from {current.value} to {target_state.value}. "
                f"Allowed target states: {[s.value for s in allowed]}."
            )

        cls._CASE_STATES[case_id] = target_state
        return target_state

    @classmethod
    def clear(cls) -> None:
        cls._CASE_STATES.clear()

