import json
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
    Persistent Deferral Work Queue backed by relational database (SQLite/PostgreSQL)
    via DeferralQueueRecord table with in-memory caching.
    Tracks cases requiring clinical review, supplementary records, or clinician attestation.
    Survives process restarts by synchronizing state from persistent storage.
    """

    _QUEUE: Dict[str, DeferralQueueItem] = {}

    @classmethod
    def add_case(
        cls,
        adjudication: FinalAdjudication,
        action_questions: Optional[List[str]] = None,
        db: Optional[Any] = None
    ) -> DeferralQueueItem:
        missing = [c.criterion_code for c in adjudication.criterion_assessments if c.status == DeterminationStatus.NOT_MET and not c.is_exclusion]
        insufficient = [c.criterion_code for c in adjudication.criterion_assessments if c.status == DeterminationStatus.INSUFFICIENT_EVIDENCE and not c.is_exclusion]
        questions = action_questions or adjudication.action_required_questions or []
        state = InternalWorkflowState.PENDING_EVIDENCE if insufficient or missing else InternalWorkflowState.HUMAN_REVIEW

        decision_str = adjudication.adjudication_decision.value if hasattr(adjudication.adjudication_decision, 'value') else str(adjudication.adjudication_decision)

        item = DeferralQueueItem(
            case_id=adjudication.case_id,
            patient_id_masked=adjudication.patient_id_masked,
            policy_id=adjudication.policy_id,
            policy_title=adjudication.policy_title,
            provisional_decision=decision_str,
            missing_criteria=missing,
            insufficient_criteria=insufficient,
            action_required_questions=questions,
            audit_hash=adjudication.audit_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            current_state=state
        )
        cls._QUEUE[adjudication.case_id] = item

        # Persist to database
        try:
            from app.db.session import SessionLocal
            from app.db.models import DeferralQueueRecord
            local_db = db or SessionLocal()
            close_db = db is None
            try:
                rec = local_db.query(DeferralQueueRecord).filter(DeferralQueueRecord.case_id == adjudication.case_id).first()
                if not rec:
                    rec = DeferralQueueRecord(
                        case_id=adjudication.case_id,
                        patient_id_masked=adjudication.patient_id_masked,
                        policy_id=adjudication.policy_id,
                        policy_title=adjudication.policy_title,
                        provisional_decision=decision_str,
                        missing_criteria_json=json.dumps(missing),
                        insufficient_criteria_json=json.dumps(insufficient),
                        action_required_questions_json=json.dumps(questions),
                        audit_hash=adjudication.audit_hash,
                        current_state=state.value
                    )
                    local_db.add(rec)
                else:
                    rec.patient_id_masked = adjudication.patient_id_masked
                    rec.policy_id = adjudication.policy_id
                    rec.policy_title = adjudication.policy_title
                    rec.provisional_decision = decision_str
                    rec.missing_criteria_json = json.dumps(missing)
                    rec.insufficient_criteria_json = json.dumps(insufficient)
                    rec.action_required_questions_json = json.dumps(questions)
                    rec.audit_hash = adjudication.audit_hash
                    rec.current_state = state.value
                local_db.commit()
            except Exception:
                local_db.rollback()
            finally:
                if close_db:
                    local_db.close()
        except Exception:
            pass

        return item

    @classmethod
    def list_queue(cls, db: Optional[Any] = None) -> List[DeferralQueueItem]:
        # Sync from DB to ensure survival across process restarts
        try:
            from app.db.session import SessionLocal
            from app.db.models import DeferralQueueRecord
            local_db = db or SessionLocal()
            close_db = db is None
            try:
                records = local_db.query(DeferralQueueRecord).all()
                for rec in records:
                    if rec.case_id not in cls._QUEUE:
                        cls._QUEUE[rec.case_id] = DeferralQueueItem(
                            case_id=rec.case_id,
                            patient_id_masked=rec.patient_id_masked,
                            policy_id=rec.policy_id,
                            policy_title=rec.policy_title,
                            provisional_decision=rec.provisional_decision,
                            missing_criteria=json.loads(rec.missing_criteria_json or "[]"),
                            insufficient_criteria=json.loads(rec.insufficient_criteria_json or "[]"),
                            action_required_questions=json.loads(rec.action_required_questions_json or "[]"),
                            audit_hash=rec.audit_hash,
                            created_at=rec.created_at.isoformat() if rec.created_at else datetime.now(timezone.utc).isoformat(),
                            current_state=InternalWorkflowState(rec.current_state) if rec.current_state in InternalWorkflowState._value2member_map_ else InternalWorkflowState.PRE_CHECK
                        )
            except Exception:
                pass
            finally:
                if close_db:
                    local_db.close()
        except Exception:
            pass
        return list(cls._QUEUE.values())

    @classmethod
    def get_item(cls, case_id: str, db: Optional[Any] = None) -> Optional[DeferralQueueItem]:
        if case_id in cls._QUEUE:
            return cls._QUEUE[case_id]
        try:
            from app.db.session import SessionLocal
            from app.db.models import DeferralQueueRecord
            local_db = db or SessionLocal()
            close_db = db is None
            try:
                rec = local_db.query(DeferralQueueRecord).filter(DeferralQueueRecord.case_id == case_id).first()
                if rec:
                    item = DeferralQueueItem(
                        case_id=rec.case_id,
                        patient_id_masked=rec.patient_id_masked,
                        policy_id=rec.policy_id,
                        policy_title=rec.policy_title,
                        provisional_decision=rec.provisional_decision,
                        missing_criteria=json.loads(rec.missing_criteria_json or "[]"),
                        insufficient_criteria=json.loads(rec.insufficient_criteria_json or "[]"),
                        action_required_questions=json.loads(rec.action_required_questions_json or "[]"),
                        audit_hash=rec.audit_hash,
                        created_at=rec.created_at.isoformat() if rec.created_at else datetime.now(timezone.utc).isoformat(),
                        current_state=InternalWorkflowState(rec.current_state) if rec.current_state in InternalWorkflowState._value2member_map_ else InternalWorkflowState.PRE_CHECK
                    )
                    cls._QUEUE[case_id] = item
                    return item
            except Exception:
                pass
            finally:
                if close_db:
                    local_db.close()
        except Exception:
            pass
        return None

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
            "original_system_output_json": original_adjudication.model_dump_json(),
            "override_reason": override_reason.strip(),
            "clinician_id": clinician_id,
            "clinician_role": clinician_role,
            "overridden_at": timestamp_str,
            "is_internal_system_override": True,
            "payer_transmission_status": "NONE_INTERNAL_ONLY"
        }

        # Update copy with override container while keeping original fields intact
        adj_dict["original_system_output_json"] = original_adjudication.model_dump_json()
        adj_dict["human_override"] = override_payload
        adj_dict["human_sign_off_status"] = "OVERRIDDEN"
        adj_dict["signed_off_by"] = clinician_id
        adj_dict["signed_off_at"] = timestamp_str
        adj_dict["determination_stage"] = "PROVISIONAL"
        adj_dict["is_releasable"] = False

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


class HumanSignOffService:
    """
    Mandatory Human Sign-Off Gate Service (Task 1).
    Enforces that a determination cannot transition from PROVISIONAL to FINAL
    or become releasable without an explicit, recorded human clinician sign-off.
    """

    @classmethod
    def sign_off(
        cls,
        adjudication: FinalAdjudication,
        signed_by: str,
        clinician_npi: Optional[str] = None,
        clinician_credentials: Optional[str] = None,
        notes: Optional[str] = None
    ) -> FinalAdjudication:
        if not signed_by or not signed_by.strip():
            raise ValueError("Clinical sign-off requires an identified reviewer / clinician name or ID.")

        timestamp_str = datetime.now(timezone.utc).isoformat()
        adj_dict = adjudication.model_dump()
        adj_dict["determination_stage"] = "FINAL"
        adj_dict["is_releasable"] = True
        adj_dict["human_sign_off_status"] = "SIGNED_OFF"
        adj_dict["signed_off_by"] = signed_by.strip()
        adj_dict["signed_off_at"] = timestamp_str

        attestation = f"[Clinician Sign-Off Gate Passed]: Reviewed and approved by {signed_by.strip()}"
        if clinician_credentials:
            attestation += f", {clinician_credentials.strip()}"
        if clinician_npi:
            attestation += f" (NPI: {clinician_npi.strip()})"
        if notes:
            attestation += f". Notes: {notes.strip()}"

        existing_notes = adj_dict.get("required_clinician_action_notes") or ""
        adj_dict["required_clinician_action_notes"] = (existing_notes + "\n" + attestation).strip()

        return FinalAdjudication(**adj_dict)


class ResubmissionLifecycleManager:
    """
    Resubmission & Case Lifecycle Manager backed by relational database.
    Survives process restarts.
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
    def get_state(cls, case_id: str, db: Optional[Any] = None) -> InternalWorkflowState:
        if case_id in cls._CASE_STATES:
            return cls._CASE_STATES[case_id]
        try:
            from app.db.session import SessionLocal
            from app.db.models import DeferralQueueRecord
            local_db = db or SessionLocal()
            close_db = db is None
            try:
                rec = local_db.query(DeferralQueueRecord).filter(DeferralQueueRecord.case_id == case_id).first()
                if rec and rec.current_state in InternalWorkflowState._value2member_map_:
                    st = InternalWorkflowState(rec.current_state)
                    cls._CASE_STATES[case_id] = st
                    return st
            except Exception:
                pass
            finally:
                if close_db:
                    local_db.close()
        except Exception:
            pass
        return InternalWorkflowState.PRE_CHECK

    @classmethod
    def transition(cls, case_id: str, target_state: InternalWorkflowState, db: Optional[Any] = None) -> InternalWorkflowState:
        current = cls.get_state(case_id, db=db)
        if target_state == current:
            return current

        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        if target_state not in allowed:
            raise InvalidWorkflowTransitionError(
                f"Illegal internal workflow transition for case {case_id}: cannot transition directly from {current.value} to {target_state.value}. "
                f"Allowed target states: {[s.value for s in allowed]}."
            )

        cls._CASE_STATES[case_id] = target_state
        try:
            from app.db.session import SessionLocal
            from app.db.models import DeferralQueueRecord
            local_db = db or SessionLocal()
            close_db = db is None
            try:
                rec = local_db.query(DeferralQueueRecord).filter(DeferralQueueRecord.case_id == case_id).first()
                if rec:
                    rec.current_state = target_state.value
                    local_db.commit()
            except Exception:
                local_db.rollback()
            finally:
                if close_db:
                    local_db.close()
        except Exception:
            pass
        return target_state

    @classmethod
    def clear(cls) -> None:
        cls._CASE_STATES.clear()

