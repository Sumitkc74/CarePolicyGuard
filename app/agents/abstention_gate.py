from typing import List, Tuple, Optional
from app.schemas.contracts import (
    DeterminationStatus,
    AdjudicationDecision,
    CriterionAssessment,
    VerificationAuditResult
)
from app.core.config import settings

class CalibratedAbstentionGate:
    """
    Agent 4: Calibrated Abstention Gate
    Enforces confidence thresholds (tau = 0.85) and adversarial integrity checks.
    When confidence is suboptimal, hallucinations are detected, or unverified omissions occur,
    the gate abstains from autonomous coverage determination and defers to clinician/auditor review.
    """

    def __init__(self, tau: Optional[float] = None):
        self.tau = tau if tau is not None else settings.ABSTENTION_THRESHOLD

    def evaluate(
        self,
        criteria_assessments: List[CriterionAssessment],
        audit_results: List[VerificationAuditResult]
    ) -> Tuple[AdjudicationDecision, bool, float, float, Optional[str], Optional[str]]:
        """
        Determines final coverage adjudication or triggers abstention.
        Returns:
            (decision, abstention_status, raw_aggregate_conf, calibrated_aggregate_conf, abstention_reason, clinician_action_notes)
        """
        if not criteria_assessments:
            return (
                AdjudicationDecision.DEFERRED_TO_HUMAN,
                True,
                0.0,
                0.0,
                "No policy criteria evaluated.",
                "Review policy selection and criteria configuration."
            )

        # 1. Aggregate confidence calculation
        raw_confs = [a.raw_confidence for a in criteria_assessments]
        calibrated_confs = [audit.calibrated_confidence for audit in audit_results]

        raw_aggregate_conf = round(sum(raw_confs) / len(raw_confs), 4)
        calibrated_aggregate_conf = round(sum(calibrated_confs) / len(calibrated_confs), 4)

        # 2. Check adversarial triggers
        abstention_triggers: List[str] = []
        action_items: List[str] = []

        # Check for Hallucinations or Grounding failures
        hallucinations = [audit for audit in audit_results if audit.hallucination_flag]
        if hallucinations:
            codes = ", ".join([h.criterion_code for h in hallucinations])
            abstention_triggers.append(f"Adversarial audit detected fabricated / hallucinated evidence spans in criteria: {codes}.")
            action_items.append(f"Manually review EHR documentation for ungrounded claims in [{codes}].")

        # Check for Offset Drifts
        offset_drifts = [audit for audit in audit_results if audit.offset_drift_detected]
        if offset_drifts:
            codes = ", ".join([od.criterion_code for od in offset_drifts])
            action_items.append(f"Verify character offset drift in cited spans for [{codes}].")

        # Check for Unverified Omissions
        omissions = [audit for audit in audit_results if audit.unverified_omission_flag]
        if omissions:
            codes = ", ".join([o.criterion_code for o in omissions])
            abstention_triggers.append(f"Potential unverified negative omission detected in [{codes}]: EHR mentions clinical criteria terms but marked non-qualifying.")
            action_items.append(f"Verify if patient chart actually fulfills requirements for [{codes}], as salient clinical keywords were found in the note.")

        # Check for Insufficient Evidence in mandatory criteria
        insufficient_crit = [a for a in criteria_assessments if not a.is_exclusion and a.status == DeterminationStatus.INSUFFICIENT_EVIDENCE]
        if insufficient_crit:
            codes = ", ".join([a.criterion_code for a in insufficient_crit])
            action_items.append(f"Obtain supplementary documentation for missing mandatory criteria: [{codes}].")

        # Check threshold tau
        if calibrated_aggregate_conf < self.tau:
            abstention_triggers.append(
                f"Calibrated aggregate confidence ({calibrated_aggregate_conf:.3f}) falls below safety threshold tau ({self.tau:.2f})."
            )

        # 3. Decision Routing
        if abstention_triggers or hallucinations or omissions:
            decision = AdjudicationDecision.DEFERRED_TO_HUMAN
            abstention_status = True
            abstention_reason = " | ".join(abstention_triggers)
            clinician_action_notes = "CLINICAL AUDITOR ACTION REQUIRED:\n" + "\n".join([f"- {item}" for item in action_items])
            return (
                decision,
                abstention_status,
                raw_aggregate_conf,
                calibrated_aggregate_conf,
                abstention_reason,
                clinician_action_notes
            )

        # If not abstaining, evaluate coverage logic:
        # - Exclusions: if ANY exclusion criterion is MET -> DENIED
        # - Inclusions: ALL inclusion criteria must be MET -> APPROVED, else DENIED
        met_exclusions = [a for a in criteria_assessments if a.is_exclusion and a.status == DeterminationStatus.MET]
        unmet_inclusions = [a for a in criteria_assessments if not a.is_exclusion and a.status != DeterminationStatus.MET]

        if met_exclusions:
            decision = AdjudicationDecision.DENIED
            abstention_status = False
            abstention_reason = None
            excl_names = ", ".join([e.name or e.criterion_code for e in met_exclusions])
            clinician_action_notes = f"Autonomous Denial: Patient satisfies disqualifying exclusion criterion: {excl_names}."
        elif unmet_inclusions:
            decision = AdjudicationDecision.DENIED
            abstention_status = False
            abstention_reason = None
            unmet_names = ", ".join([u.name or u.criterion_code for u in unmet_inclusions])
            clinician_action_notes = f"Autonomous Denial: Patient does not satisfy mandatory coverage criteria: {unmet_names}."
        else:
            decision = AdjudicationDecision.APPROVED
            abstention_status = False
            abstention_reason = None
            clinician_action_notes = "Autonomous Approval: All governing Medicare clinical criteria and temporal preconditions verified with high calibration."

        return (
            decision,
            abstention_status,
            raw_aggregate_conf,
            calibrated_aggregate_conf,
            abstention_reason,
            clinician_action_notes
        )

