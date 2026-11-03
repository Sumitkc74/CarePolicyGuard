import re
from typing import Dict, Any, List, Optional
from app.schemas.contracts import (
    CriterionAssessment,
    DeterminationStatus,
    AdjudicationDecision
)
from app.services.semantic_verifier import SemanticSupportChecker


class CriticAgent:
    """
    Critic Agent: Adversarial Falsification & Disagreement Engine.
    Sub-task: Actively attempts to falsify provisional coverage approvals by searching for:
    - Counter-evidence and disqualifying exclusions
    - Hidden negations and contextual cancellations
    - Temporal conflicts and contradictory measurements across sections
    - Hypothetical, conditional, or planned future framing
    - Experiencer mismatch (family history vs patient)

    Operational Invariant:
    Agents propose; the deterministic engine disposes.
    No agent may approve on its own. If the Critic Agent uncovers falsifying evidence,
    it records an explicit agent disagreement and forces a deterministic veto (DENIED or DEFERRED).
    """

    def __init__(self):
        pass

    def critique_approval(
        self,
        provisional_decision: AdjudicationDecision,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        policy_id: str
    ) -> Dict[str, Any]:
        """
        Executes falsification analysis on a provisional approval or determination.
        Returns:
            dict containing:
            - falsification_detected: bool
            - critic_action: "CONCUR", "VETO_TO_DENIED", "VETO_TO_DEFERRED"
            - objections: list[str]
            - counter_evidence_spans: list[dict]
            - disagreement_recorded: bool
        """
        objections: List[str] = []
        counter_evidence_spans: List[Dict[str, Any]] = []

        # 1. Contradiction Detection across EHR Note
        has_contra, contra_notes = SemanticSupportChecker.detect_case_contradictions(
            ehr_text,
            criteria_assessments
        )
        if has_contra:
            for cn in contra_notes:
                objections.append(f"Critic detected internal clinical contradiction: {cn}")

        # 2. Search for Disqualifying Exclusions in EHR that were missed
        text_lower = ehr_text.lower()
        exclusion_patterns = {
            "cardiogenic_shock": r"\b(?:cardiogenic shock|severe shock|hemodynamic collapse)\b",
            "terminal_illness": r"\b(?:life expectancy\s*<\s*1\s*year|terminal illness|metastatic stage iv|hospice care)\b",
            "active_infection": r"\b(?:active sepsis|bacteremia|untreated systemic infection|endocarditis)\b",
            "severe_dementia": r"\b(?:severe advanced dementia|bedbound vegetative state)\b"
        }

        for excl_name, pat in exclusion_patterns.items():
            for match in re.finditer(pat, text_lower):
                # Verify scope is not negated
                scope = SemanticSupportChecker.verify_span_semantics(
                    span=type("TempSpan", (), {
                        "start_char": match.start(),
                        "end_char": match.end(),
                        "source_text": ehr_text[match.start():match.end()],
                        "clinical_section": "Clinical Note"
                    })(),
                    ehr_text=ehr_text
                )
                if scope.negation_valid and scope.subject_valid:
                    obj_text = f"Critic identified unaddressed disqualifying exclusion: '{match.group(0)}' at character [{match.start()}:{match.end()}]."
                    objections.append(obj_text)
                    counter_evidence_spans.append({
                        "type": "EXCLUSION_COUNTER_EVIDENCE",
                        "text": ehr_text[match.start():match.end()],
                        "start": match.start(),
                        "end": match.end(),
                        "detail": excl_name
                    })

        # 3. Audit each proposed MET criterion for invalidating semantics
        for assess in criteria_assessments:
            if assess.status == DeterminationStatus.MET and not assess.is_exclusion:
                for span in assess.verified_spans:
                    if not getattr(span, "semantic_support_passed", True):
                        reasons = getattr(span, "semantic_invalidation_reasons", [])
                        obj_msg = f"Critic rejected evidence for {assess.criterion_code}: {'; '.join(reasons)}"
                        objections.append(obj_msg)

        # 4. Determine critic verdict
        if objections:
            # If any disqualifying exclusion was confirmed, veto to DENIED
            if any("disqualifying exclusion" in obj for obj in objections):
                action = "VETO_TO_DENIED"
            else:
                action = "VETO_TO_DEFERRED"

            return {
                "falsification_detected": True,
                "critic_action": action,
                "objections": objections,
                "counter_evidence_spans": counter_evidence_spans,
                "disagreement_recorded": True
            }

        return {
            "falsification_detected": False,
            "critic_action": "CONCUR",
            "objections": [],
            "counter_evidence_spans": [],
            "disagreement_recorded": False
        }

