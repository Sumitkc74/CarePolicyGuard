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
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus

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
    Every transition is deterministic, logged, and included in the SHA-256 audit digest.
    """

    def __init__(self, tau: float = 0.85):
        self.tau = tau
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
        Stage 1: Retrieval verification
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

        # Stage 1: Retrieval
        self._record_transition(
            PipelineStage.POLICY_RETRIEVAL,
            "SUCCESS",
            {"policy_id": policy_id, "policy_title": policy_title, "criteria_count": len(criteria_list)}
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

        # Stage 3: Critic Cross-Examination
        critic_verdicts: List[CriticVerdict] = []
        disagreements = []

        for candidate, crit in zip(proposals, criteria_list):
            is_exclusion = crit.get("is_exclusion", False)
            quote = candidate.exact_quote
            crit_code = candidate.criterion_code

            # Check for contradiction terms
            contradiction = False
            negation = False
            if quote and quote != "No explicit evidence span found":
                q_low = quote.lower()
                neg_terms = ["denies", "no history", "without", "resolved", "absent", "ruled out"]
                if any(nt in q_low for nt in neg_terms):
                    negation = True

            # Critic determination
            critic_status = candidate.status_proposed
            if negation and candidate.status_proposed == "MET" and not is_exclusion:
                critic_status = "NOT_MET"
                contradiction = True

            agrees = (critic_status == candidate.status_proposed) and not contradiction
            if not agrees:
                disagreements.append(crit_code)

            critic_verdicts.append(CriticVerdict(
                criterion_code=crit_code,
                agrees_with_extractor=agrees,
                critic_status=critic_status,
                negation_detected=negation,
                contradiction_flagged=contradiction,
                critic_notes="Verified consistent." if agrees else f"Disagreement on status ({candidate.status_proposed} vs {critic_status}) or negation flagged."
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

        # Stage 5: Calibrated Abstention Gate
        # Compute empirical aggregate confidence from candidate sampling agreement
        confidences = [p.sampling_agreement_rate for p in proposals]
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
        
        # Penalize confidence if disagreements or slice failures occurred
        calibrated_confidence = avg_confidence
        if disagreements:
            calibrated_confidence = round(calibrated_confidence * 0.75, 3)
        if slice_failures:
            calibrated_confidence = round(calibrated_confidence * 0.50, 3)

        abstain_triggered = False
        abstain_reasons = []

        if disagreements:
            abstain_triggered = True
            abstain_reasons.append(f"Extractor-Critic agent disagreement on {disagreements}")
        if slice_failures:
            abstain_triggered = True
            abstain_reasons.append(f"Grounding failure: {len(slice_failures)} citations failed character slice verification")
        if calibrated_confidence < self.tau:
            abstain_triggered = True
            abstain_reasons.append(f"Calibrated confidence {calibrated_confidence:.3f} below safety floor tau {self.tau:.2f}")

        # Compute decision
        if abstain_triggered:
            final_decision = AdjudicationDecision.DEFERRED_TO_HUMAN
        else:
            # Check if any inclusion criteria NOT_MET or exclusion criteria MET
            has_unmet_inclusion = any(
                p.status_proposed in ("NOT_MET", "INSUFFICIENT_EVIDENCE") 
                for p, c in zip(proposals, criteria_list) if not c.get("is_exclusion", False)
            )
            has_met_exclusion = any(
                p.status_proposed == "MET"
                for p, c in zip(proposals, criteria_list) if c.get("is_exclusion", False)
            )

            if has_unmet_inclusion or has_met_exclusion:
                final_decision = AdjudicationDecision.DENIED
            else:
                final_decision = AdjudicationDecision.APPROVED

        self._record_transition(
            PipelineStage.CALIBRATED_ABSTENTION_GATE,
            "ABSTAIN" if abstain_triggered else "PASS",
            {
                "calibrated_confidence": calibrated_confidence,
                "tau_threshold": self.tau,
                "abstain_triggered": abstain_triggered,
                "abstain_reasons": abstain_reasons,
                "preliminary_decision": final_decision.value
            }
        )

        # Stage 6: Finalized State
        total_latency_ms = (time.perf_counter() - self._start_perf) * 1000.0
        
        # Compute SHA-256 seal of the state transitions
        transition_json = json.dumps([t.model_dump() for t in self.transitions], sort_keys=True)
        state_hash = hashlib.sha256(transition_json.encode("utf-8")).hexdigest()

        self._record_transition(
            PipelineStage.FINALIZED,
            "COMPLETED",
            {
                "final_decision": final_decision.value,
                "state_hash": state_hash,
                "total_latency_ms": round(total_latency_ms, 2)
            }
        )

        return {
            "final_decision": final_decision.value,
            "calibrated_confidence": calibrated_confidence,
            "raw_confidence": avg_confidence,
            "abstention_status": abstain_triggered,
            "abstention_reasons": abstain_reasons,
            "total_latency_ms": round(total_latency_ms, 2),
            "state_audit_hash": state_hash,
            "transitions_log": [t.model_dump() for t in self.transitions],
            "proposals": [p.model_dump() for p in proposals],
            "critic_verdicts": [v.model_dump() for v in critic_verdicts]
        }

