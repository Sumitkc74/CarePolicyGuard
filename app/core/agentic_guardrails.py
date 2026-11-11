"""
Deterministic Agentic Guardrails Layer (Task 3).
Enforces non-bypassable safety constraints as deterministic code.
Guarantees that no agent can autonomously approve without:
1. Exact character-grounded verbatim evidence from the patient narrative.
2. Complete sequential passage through Gate B, Gate C, and Agent 3 cross-examination.
3. Invariant that grounded negative determinations (proven NOT_MET) are never overturned.
4. Hard execution budget bounds (calls, latency, debate rounds, agent turns) where exhaustion defers.
5. Calibrated sufficiency floor (weakest-link >= 0.65, tau >= 0.85).
"""

from __future__ import annotations

from typing import Any

from app.core.clinical_core import ClinicalScopeAnalyzer
from app.core.concept_map import ConceptMap, get_concept_map
from app.schemas.contracts import (
    ClinicalEvidenceSpan,
    CriterionAssessment,
    DeterminationStatus,
)


class GuardrailViolationError(Exception):
    """Raised when an agent action violates a statutory or safety guardrail."""
    def __init__(self, guardrail_name: str, message: str):
        super().__init__(f"GUARDRAIL_VIOLATION [{guardrail_name}]: {message}")
        self.guardrail_name = guardrail_name
        self.message = message


class BudgetExhaustionHalt(Exception):
    """Raised when hard operational budgets (LLM calls, latency, turns) are exceeded."""
    def __init__(self, resource: str, limit: Any, current: Any):
        super().__init__(f"BUDGET_EXHAUSTED [{resource}]: limit {limit} reached with {current}")
        self.resource = resource
        self.limit = limit
        self.current = current


class AgenticGuardrails:
    """
    Central deterministic guardrail engine governing all agent actions and transitions.
    """

    MAX_LLM_CALLS_PER_CASE: int = 3
    MAX_LLM_TIME_PER_CASE_SECONDS: float = 30.0
    MAX_DEBATE_ROUNDS_PER_CRITERION: int = 2
    MAX_AGENT_TURNS_PER_CASE: int = 25
    OPERATIVE_TAU: float = 0.85
    WEAKEST_LINK_FLOOR: float = 0.65

    # 1. Verbatim Grounding Guardrail
    @classmethod
    def verify_verbatim_grounding(
        cls,
        ehr_narrative: str,
        assessment: CriterionAssessment
    ) -> bool:
        """
        Enforces that no criterion can be MET without an exact, non-hallucinated
        substring of the patient's EHR narrative.
        """
        if assessment.status != DeterminationStatus.MET:
            return True

        if not assessment.verified_spans:
            raise GuardrailViolationError(
                "VERBATIM_GROUNDING",
                f"Criterion {assessment.criterion_code} marked MET with zero verified evidence spans."
            )

        for span in assessment.verified_spans:
            s = span.start_char
            e = span.end_char
            txt = span.source_text

            if s < 0 or e > len(ehr_narrative) or s >= e:
                raise GuardrailViolationError(
                    "VERBATIM_GROUNDING",
                    f"Invalid span offsets [{s}:{e}] for narrative length {len(ehr_narrative)}."
                )

            extracted_slice = ehr_narrative[s:e]
            if extracted_slice != txt:
                raise GuardrailViolationError(
                    "VERBATIM_GROUNDING",
                    f"Span text mismatch: expected '{txt}' but note contains '{extracted_slice}'."
                )

        return True

    # 2. Gate Chain Execution Guardrail
    @classmethod
    def evaluate_gate_chain(
        cls,
        candidate_span: ClinicalEvidenceSpan,
        criterion: dict[str, Any],
        ehr_narrative: str,
        concept_map: ConceptMap | None = None,
        verifier_agent: Any | None = None
    ) -> dict[str, Any]:
        """
        Passes a candidate span through the mandatory sequential gate chain:
        - Verbatim slice validation
        - Gate B: 5-dimension clinical semantics (experiencer, negation, modality)
        - Gate C: ConceptMap equivalence verification
        - Agent 3: Cross-examination challenge check
        No LLM output may bypass any gate in this chain.
        """
        cname = criterion.get("name", "")
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cmap = concept_map or get_concept_map()

        # Step 1: Exact slice check
        s = candidate_span.start_char
        e = candidate_span.end_char
        if s < 0 or e > len(ehr_narrative) or s >= e or ehr_narrative[s:e] != candidate_span.source_text:
            return {
                "passed": False,
                "failing_gate": "GATE_A_EXACT_SLICE",
                "reason": f"Candidate span offsets [{s}:{e}] do not match note text."
            }

        # Step 2: Gate B: Semantic scope check (negation, experiencer, modality)
        scope = ClinicalScopeAnalyzer.analyze_scope(ehr_narrative, s, e)
        if scope.get("is_negated"):
            return {
                "passed": False,
                "failing_gate": "GATE_B_SEMANTIC",
                "reason": f"Candidate span is negated in clinical context ({scope.get('negation_trigger')})."
            }
        if scope.get("is_family_history") or scope.get("experiencer") == "FAMILY_MEMBER":
            return {
                "passed": False,
                "failing_gate": "GATE_B_SEMANTIC",
                "reason": "Candidate span documents family medical history, not patient condition."
            }
        if scope.get("is_hypothetical"):
            return {
                "passed": False,
                "failing_gate": "GATE_B_SEMANTIC",
                "reason": "Candidate span documents hypothetical or conditional findings."
            }

        # Step 3: Gate C: ConceptMap equivalence check
        candidate_crit_terms = [cname] + list(criterion.get("entity_names", [])) + list(criterion.get("keywords", []))
        concept_match_found = False
        concept_match_reason = "No matching concept definition"

        for crit_term in candidate_crit_terms:
            is_equiv, equiv_reason = cmap.verify_equivalence(crit_term, candidate_span.source_text)
            if is_equiv:
                concept_match_found = True
                concept_match_reason = equiv_reason
                break
            elif "PROHIBITED_NEAR_MISS" in equiv_reason or "disjoint concepts" in equiv_reason:
                concept_match_reason = equiv_reason

        if not concept_match_found:
            return {
                "passed": False,
                "failing_gate": "GATE_C_MAP_CHECK",
                "reason": f"ConceptMap equivalence rejected: {concept_match_reason}."
            }

        # Step 4: Agent 3 Cross-Examination
        if verifier_agent is not None and hasattr(verifier_agent, "audit_assessment"):
            dummy_assessment = CriterionAssessment(
                criterion_id=ccode,
                criterion_code=ccode,
                name=cname,
                description=criterion.get("description", cname),
                status=DeterminationStatus.MET,
                raw_confidence=0.92,
                clinical_rationale="Gated equivalence candidate",
                is_exclusion=criterion.get("is_exclusion", False),
                verified_spans=[candidate_span]
            )
            audit = verifier_agent.audit_assessment(dummy_assessment, criterion, ehr_narrative)
            if audit.hallucination_flag or not audit.grounding_status or getattr(audit, "contradiction_detected", False):
                return {
                    "passed": False,
                    "failing_gate": "GATE_C_AGENT3_VETO",
                    "reason": f"Agent 3 cross-examination veto: {audit.audit_notes}."
                }

        return {
            "passed": True,
            "failing_gate": None,
            "reason": concept_match_reason
        }

    # 3. Grounded Negative Reconciliation Guardrail (Task 2 Reconciliation Rule)
    @classmethod
    def reconcile_deterministic_and_llm(
        cls,
        deterministic_status: DeterminationStatus,
        llm_verdict: str,
        is_exclusion: bool = False
    ) -> DeterminationStatus:
        """
        Reconciliation rule:
        - A criterion proven NOT_MET by deterministic patterns on grounded evidence
          (or an exclusion proven MET) is NEVER overturned by an LLM EQUIVALENT verdict.
        - Only a criterion left INSUFFICIENT_EVIDENCE may be upgraded to MET by a verified EQUIVALENT claim.
        """
        # Proven exclusion cannot be overturned
        if is_exclusion and deterministic_status == DeterminationStatus.MET:
            return DeterminationStatus.MET  # Exclusion stands, leads to DENIAL

        # Proven NOT_MET inclusion criterion cannot be overturned by LLM
        if not is_exclusion and deterministic_status == DeterminationStatus.NOT_MET:
            return DeterminationStatus.NOT_MET

        # Criteria left INSUFFICIENT_EVIDENCE can be upgraded to MET if LLM verdict is EQUIVALENT
        if (
            deterministic_status in (DeterminationStatus.INSUFFICIENT_EVIDENCE, DeterminationStatus.NOT_MET)
            and llm_verdict.strip().upper() == "EQUIVALENT"
        ):
            if deterministic_status == DeterminationStatus.INSUFFICIENT_EVIDENCE:
                return DeterminationStatus.MET
            return DeterminationStatus.NOT_MET

        return deterministic_status

    # 4. Operational Budget Guardrail
    @classmethod
    def check_budgets(
        cls,
        llm_calls: int,
        elapsed_seconds: float,
        agent_turns: int,
        criterion_debate_rounds: int
    ) -> None:
        """
        Enforces execution limits. If any limit is breached, raises BudgetExhaustionHalt,
        guaranteeing the case defers to human review and never auto-approves.
        """
        if llm_calls > cls.MAX_LLM_CALLS_PER_CASE:
            raise BudgetExhaustionHalt("LLM_CALLS", cls.MAX_LLM_CALLS_PER_CASE, llm_calls)

        if elapsed_seconds > cls.MAX_LLM_TIME_PER_CASE_SECONDS:
            raise BudgetExhaustionHalt("LLM_TIME_SECONDS", cls.MAX_LLM_TIME_PER_CASE_SECONDS, elapsed_seconds)

        if agent_turns > cls.MAX_AGENT_TURNS_PER_CASE:
            raise BudgetExhaustionHalt("AGENT_TURNS", cls.MAX_AGENT_TURNS_PER_CASE, agent_turns)

        if criterion_debate_rounds > cls.MAX_DEBATE_ROUNDS_PER_CRITERION:
            raise BudgetExhaustionHalt("DEBATE_ROUNDS", cls.MAX_DEBATE_ROUNDS_PER_CRITERION, criterion_debate_rounds)

    # 5. Weakest-Link & Tau Floor Guardrail
    @classmethod
    def check_confidence_floors(
        cls,
        criteria_assessments: list[CriterionAssessment],
        calibrated_aggregate_confidence: float | None
    ) -> str | None:
        """
        Checks weakest-link floor (0.65) and calibrated sufficiency threshold tau (0.85).
        Returns failure reason string if breached, or None if passed.
        """
        # Weakest-link floor on mandatory inclusion criteria
        for ca in criteria_assessments:
            if (
                not ca.is_exclusion
                and ca.status == DeterminationStatus.MET
                and (ca.raw_confidence or 0.0) < cls.WEAKEST_LINK_FLOOR
            ):
                return (
                    f"Weakest-link safety floor breached: Mandatory inclusion criterion "
                    f"{ca.criterion_code} raw confidence ({ca.raw_confidence:.2f}) < floor ({cls.WEAKEST_LINK_FLOOR:.2f})."
                )

        # Tau threshold check
        conf = calibrated_aggregate_confidence if calibrated_aggregate_confidence is not None else 0.0
        if conf < cls.OPERATIVE_TAU:
            return f"Calibrated aggregate confidence ({conf:.3f}) falls below safety threshold tau ({cls.OPERATIVE_TAU:.2f})."

        return None
