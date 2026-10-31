import hashlib
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.agents.llm_extractor import CandidateExtraction, StructuredExtractorAgent, ExtractorTools
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.services.hybrid_retriever import HybridPolicyRetriever
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus, CriterionAssessment, ClinicalEvidenceSpan

class PipelineStage(str, Enum):
    INIT = "STAGE_0_INITIALIZATION"
    POLICY_RETRIEVAL = "STAGE_1_HYBRID_POLICY_RETRIEVAL"
    EXTRACTOR_PROPOSAL = "STAGE_2_STRUCTURED_EXTRACTOR_PROPOSAL"
    CRITIC_CROSS_EXAMINATION = "STAGE_3_CRITIC_ADVERSARIAL_CROSS_EXAM"
    DETERMINISTIC_SLICE_CHECK = "STAGE_4_DETERMINISTIC_SLICE_VERIFICATION"
    CALIBRATED_ABSTENTION_GATE = "STAGE_5_CALIBRATED_ABSTENTION_GATE"
    FINALIZED = "STAGE_6_ADJUDICATION_FINALIZED"

class StateTransitionRecord(BaseModel):
    step: int
    stage: PipelineStage
    timestamp: str
    elapsed_ms: float
    status: str
    details: Dict[str, Any]

class CriticVerdict(BaseModel):
    criterion_code: str
    agrees_with_extractor: bool
    critic_status: str
    negation_detected: bool
    contradiction_flagged: bool
    critic_notes: str

class ClinicalAdjudicationStateMachine:
    """
    Explicit, auditable state machine orchestrating clinical coverage verification.
    Zero third-party framework magic (No LangGraph, No CrewAI).
    Delegates directly to existing verified agents:
    - HybridPolicyRetriever (BM25 + Semantic)
    - StructuredExtractorAgent (Pydantic candidates)
    - AdversarialVerificationAgent (NegEx, contradiction, character slice)
    - CalibratedAbstentionGate (tau=0.85 calibrated gate)
    """

    def __init__(self, db: Optional[Any] = None, tau: float = 0.85):
        self.db = db
        self.tau = tau
        self.hybrid_retriever = HybridPolicyRetriever(db=db)
        self.extractor = StructuredExtractorAgent()
        self.adversarial_verifier = AdversarialVerificationAgent()
        self.abstention_gate = CalibratedAbstentionGate(tau=tau)
        self.transitions: List[StateTransitionRecord] = []
        self._step_counter = 0
        self._start_perf = 0.0

    def _record_transition(self, stage: PipelineStage, status: str, details: Dict[str, Any]):
        self._step_counter += 1
        elapsed = (time.perf_counter() - self._start_perf) * 1000.0 if self._start_perf > 0 else 0.0
        record = StateTransitionRecord(
            step=self._step_counter,
            stage=stage,
            timestamp=datetime.now(timezone.utc).isoformat(),
            elapsed_ms=round(elapsed, 2),
            status=status,
            details=details
        )
        self.transitions.append(record)

    def execute_state_machine(
        self,
        patient_id: str,
        policy_id: str,
        policy_title: str,
        criteria_list: List[Dict[str, Any]],
        raw_ehr_text: str
    ) -> Dict[str, Any]:
        """
        Executes explicit state machine:
        Stage 1: Hybrid Policy Retrieval verification
        Stage 2: Structured Extractor proposal (with self-consistency sampling)
        Stage 3: Critic adversarial cross-examination (disagreement = deferral signal)
        Stage 4: Programmatic character-slice verification
        Stage 5: Calibrated abstention gate (tau=0.85)
        """
        self._start_perf = time.perf_counter()
        self.transitions = []
        self._step_counter = 0

        # Stage 0: Init
        self._record_transition(
            PipelineStage.INIT,
            "SUCCESS",
            {"patient_id": patient_id, "policy_id": policy_id, "note_length": len(raw_ehr_text)}
        )

        # Stage 1: Hybrid Policy Retrieval
        matched_policies = []
        if self.hybrid_retriever:
            matched_policies = self.hybrid_retriever.retrieve_hybrid(raw_ehr_text, top_k=3)

        self._record_transition(
            PipelineStage.POLICY_RETRIEVAL,
            "SUCCESS",
            {
                "policy_id": policy_id,
                "policy_title": policy_title,
                "criteria_count": len(criteria_list),
                "hybrid_retrieval_matches": matched_policies
            }
        )

        # Stage 2: Extractor Proposal
        proposals: List[CandidateExtraction] = []
        for crit in criteria_list:
            candidate = self.extractor.propose_candidates(raw_ehr_text, crit)
            proposals.append(candidate)

        self._record_transition(
            PipelineStage.EXTRACTOR_PROPOSAL,
            "SUCCESS",
            {"candidates_proposed": [p.model_dump() for p in proposals]}
        )

        # Stage 3: Critic Adversarial Cross-Examination (Delegating to AdversarialVerificationAgent)
        critic_verdicts: List[CriticVerdict] = []
        disagreements = []
        adversarial_audits = []
        criteria_assessments_for_gate = []

        for candidate, crit in zip(proposals, criteria_list):
            det_status = (
                DeterminationStatus.MET if candidate.status_proposed == "MET"
                else (DeterminationStatus.NOT_MET if candidate.status_proposed == "NOT_MET"
                      else DeterminationStatus.INSUFFICIENT_EVIDENCE)
            )
            # Create CriterionAssessment for AdversarialVerificationAgent
            assessment_obj = CriterionAssessment(
                criterion_id=crit.get("id", crit.get("criterion_code", "CRIT-01")),
                criterion_code=candidate.criterion_code,
                name=crit.get("name", ""),
                description=crit.get("description", ""),
                is_exclusion=crit.get("is_exclusion", False),
                required_temporal_window=crit.get("required_temporal_window", "Not specified"),
                status=det_status,
                clinical_rationale=candidate.rationale,
                raw_confidence=candidate.sampling_agreement_rate,
                verified_spans=[
                    ClinicalEvidenceSpan(
                        source_text=candidate.exact_quote,
                        start_char=candidate.char_offset_start,
                        end_char=candidate.char_offset_end,
                        clinical_section="Clinical Progress Note",
                        confidence=candidate.sampling_agreement_rate
                    )
                ] if candidate.exact_quote and candidate.exact_quote != "No explicit evidence span found" else []
            )

            criteria_assessments_for_gate.append(assessment_obj)
            # Delegate to existing AdversarialVerificationAgent
            audit_result = self.adversarial_verifier.audit_assessment(assessment_obj, crit, raw_ehr_text)
            adversarial_audits.append(audit_result)

            has_discordance = bool(getattr(audit_result, "discordance_flag", False))
            has_hallucination = bool(getattr(audit_result, "hallucination_flag", False))
            has_omission = bool(getattr(audit_result, "unverified_omission_flag", False))

            agrees = not (has_discordance or has_hallucination)
            if not agrees:
                disagreements.append(candidate.criterion_code)

            critic_verdicts.append(CriticVerdict(
                criterion_code=candidate.criterion_code,
                agrees_with_extractor=agrees,
                critic_status=candidate.status_proposed if agrees else "DISPUTED",
                negation_detected=has_omission,
                contradiction_flagged=has_discordance,
                critic_notes=audit_result.audit_notes
            ))

        self._record_transition(
            PipelineStage.CRITIC_CROSS_EXAMINATION,
            "SUCCESS" if not disagreements else "DISAGREEMENTS_DETECTED",
            {
                "disagreement_count": len(disagreements),
                "disputed_criteria": disagreements,
                "critic_verdicts": [v.model_dump() for v in critic_verdicts]
            }
        )

        # Stage 4: Deterministic Slice Verification
        slice_failures = []
        for candidate in proposals:
            if candidate.exact_quote and candidate.exact_quote != "No explicit evidence span found":
                is_valid_slice = ExtractorTools.verify_exact_character_slice(
                    raw_ehr_text,
                    candidate.exact_quote,
                    candidate.char_offset_start,
                    candidate.char_offset_end
                )
                if not is_valid_slice:
                    slice_failures.append({
                        "criterion_code": candidate.criterion_code,
                        "quote": candidate.exact_quote,
                        "start": candidate.char_offset_start,
                        "end": candidate.char_offset_end
                    })

        self._record_transition(
            PipelineStage.DETERMINISTIC_SLICE_CHECK,
            "SUCCESS" if not slice_failures else "UNGROUNDED_CITATIONS_DETECTED",
            {"slice_failures_count": len(slice_failures), "failures": slice_failures}
        )

        # Stage 5: Calibrated Abstention Gate (Delegating directly to CalibratedAbstentionGate)
        gate_decision, abstain_triggered, raw_conf, calibrated_confidence, abstain_reason, clinician_notes = (
            self.abstention_gate.evaluate(
                criteria_assessments=criteria_assessments_for_gate,
                audit_results=adversarial_audits
            )
        )

        abstain_reasons = [abstain_reason] if abstain_reason else []

        # If extractor-critic disagreed or slice failed, safely defer to human review
        if disagreements and not abstain_triggered:
            abstain_triggered = True
            gate_decision = AdjudicationDecision.DEFERRED_TO_HUMAN
            abstain_reasons.append(f"Extractor-Critic agent disagreement on: {disagreements}")

        if slice_failures and not abstain_triggered:
            abstain_triggered = True
            gate_decision = AdjudicationDecision.DEFERRED_TO_HUMAN
            abstain_reasons.append(f"Grounding failure: {len(slice_failures)} ungrounded quotes")

        # Explicit Safety Invariant: Pattern-matched extraction CANNOT approve without
        # grounded, verified evidence and a passing calibrated gate.
        if gate_decision == AdjudicationDecision.APPROVED:
            ungrounded_or_unmet = [
                c.criterion_code for c in criteria_assessments_for_gate
                if not c.is_exclusion and (
                    c.status != DeterminationStatus.MET
                    or not c.verified_spans
                    or c.verified_spans[0].source_text == "No explicit evidence span found"
                )
            ]
            if ungrounded_or_unmet:
                gate_decision = AdjudicationDecision.DEFERRED_TO_HUMAN
                abstain_triggered = True
                abstain_reasons.append(
                    f"Safety Guardrail: Approval blocked due to missing or ungrounded mandatory criteria: {ungrounded_or_unmet}"
                )
            elif calibrated_confidence < self.tau:
                gate_decision = AdjudicationDecision.DEFERRED_TO_HUMAN
                abstain_triggered = True
                abstain_reasons.append(
                    f"Safety Guardrail: Calibrated confidence ({calibrated_confidence:.3f}) below safety threshold tau ({self.tau:.2f})"
                )

        self._record_transition(
            PipelineStage.CALIBRATED_ABSTENTION_GATE,
            "ABSTAIN" if abstain_triggered else "PASS",
            {
                "calibrated_confidence": calibrated_confidence,
                "tau_threshold": self.tau,
                "abstain_triggered": abstain_triggered,
                "abstain_reasons": abstain_reasons,
                "final_decision": gate_decision.value
            }
        )

        # Stage 6: Finalized State
        total_latency_ms = (time.perf_counter() - self._start_perf) * 1000.0
        transition_json = json.dumps([t.model_dump() for t in self.transitions], sort_keys=True)
        state_hash = hashlib.sha256(transition_json.encode("utf-8")).hexdigest()

        self._record_transition(
            PipelineStage.FINALIZED,
            "COMPLETED",
            {
                "final_decision": gate_decision.value,
                "state_hash": state_hash,
                "total_latency_ms": round(total_latency_ms, 2)
            }
        )

        return {
            "final_decision": gate_decision.value,
            "calibrated_confidence": calibrated_confidence,
            "raw_confidence": sum(p.sampling_agreement_rate for p in proposals) / max(1, len(proposals)),
            "abstention_status": abstain_triggered,
            "abstention_reasons": abstain_reasons,
            "abstention_reason": "; ".join(abstain_reasons) if abstain_reasons else None,
            "total_latency_ms": round(total_latency_ms, 2),
            "state_audit_hash": state_hash,
            "transitions_log": [t.model_dump() for t in self.transitions],
            "proposals": [p.model_dump() for p in proposals],
            "critic_verdicts": [v.model_dump() for v in critic_verdicts],
            "criterion_assessments": criteria_assessments_for_gate,
            "verification_audits": adversarial_audits,
            "clinician_action_notes": clinician_notes
        }
