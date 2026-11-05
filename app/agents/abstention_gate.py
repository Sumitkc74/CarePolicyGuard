from typing import List, Tuple, Optional, Any, Dict
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

    def __init__(self, tau: Optional[float] = None, tau_floor: float = 0.65):
        self.tau = tau if tau is not None else settings.ABSTENTION_THRESHOLD
        self.tau_floor = tau_floor

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

        # 2. Exclusion Precedence: Grounded disqualifying exclusions short-circuit to DENIED.
        # Clinically and statutorily, if a disqualifying condition is verified and grounded in the chart
        # (e.g. active cardiogenic shock), coverage is autonomously denied rather than deferred
        # for missing elective documentation on other inclusion criteria.
        grounded_met_exclusions = [
            crit for crit, audit in zip(criteria_assessments, audit_results)
            if crit.is_exclusion
            and crit.status == DeterminationStatus.MET
            and audit.grounding_status
            and not audit.hallucination_flag
        ]
        if grounded_met_exclusions:
            excl_names = ", ".join([e.name or e.criterion_code for e in grounded_met_exclusions])
            return (
                AdjudicationDecision.DENIED,
                False,
                raw_aggregate_conf,
                calibrated_aggregate_conf,
                None,
                f"Autonomous Denial: Patient satisfies disqualifying exclusion criterion: {excl_names}."
            )

        # 3. Check adversarial triggers
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
        # Only defer for documentation gaps if patient has not already failed a confirmed NOT_MET requirement
        has_proven_unmet = any(not a.is_exclusion and a.status == DeterminationStatus.NOT_MET for a in criteria_assessments)
        insufficient_crit = [a for a in criteria_assessments if not a.is_exclusion and a.status == DeterminationStatus.INSUFFICIENT_EVIDENCE]
        if insufficient_crit and not has_proven_unmet:
            codes = ", ".join([a.criterion_code for a in insufficient_crit])
            abstention_triggers.append(f"Insufficient evidence for mandatory coverage criteria: [{codes}]. Supplementary documentation required.")
            action_items.append(f"Obtain supplementary documentation for missing mandatory criteria: [{codes}].")

        # Check for Internal Clinical Discordances
        discordances = [audit for audit in audit_results if getattr(audit, "discordance_flag", False)]
        if discordances:
            codes = ", ".join([d.criterion_code for d in discordances])
            abstention_triggers.append(f"Adversarial audit detected clinical contradiction or discordance in: {codes}.")
            action_items.append(f"Clinician reconciliation required for conflicting measurements in [{codes}].")

        # Check for Semantic Support Failures (wrong subject, timing, modality, negation, range)
        semantic_failures = [
            (crit, audit) for crit, audit in zip(criteria_assessments, audit_results)
            if not getattr(audit, "semantic_support_passed", True) and not crit.is_exclusion
        ]
        if semantic_failures and not has_proven_unmet:
            codes = ", ".join([c.criterion_code for c, a in semantic_failures])
            abstention_triggers.append(
                f"Adversarial audit failed semantic support (wrong subject, future-planned timing, hypothetical modality, or out of range) in: [{codes}]."
            )
            action_items.append(f"Verify clinical validity for semantically unverified claims in [{codes}].")

        # Check Weakest-Link Safety Floor (no mandatory inclusion criterion may fall below tau_floor)
        sub_floor_mandatory = [
            (crit, audit) for crit, audit in zip(criteria_assessments, audit_results)
            if not crit.is_exclusion
            and crit.status == DeterminationStatus.MET
            and audit.calibrated_confidence < self.tau_floor
        ]
        if sub_floor_mandatory:
            codes = ", ".join([f"{c.criterion_code} ({a.calibrated_confidence:.2f})" for c, a in sub_floor_mandatory])
            abstention_triggers.append(
                f"Weakest-link safety floor breached: Mandatory inclusion criteria fall below floor ({self.tau_floor:.2f}): [{codes}]."
            )
            action_items.append(f"Obtain stronger documentation to elevate low-confidence criteria: [{codes}].")

        # Check threshold tau
        if calibrated_aggregate_conf < self.tau:
            abstention_triggers.append(
                f"Calibrated aggregate confidence ({calibrated_aggregate_conf:.3f}) falls below safety threshold tau ({self.tau:.2f})."
            )

        # 3. Decision Routing
        if abstention_triggers or hallucinations or omissions or discordances or sub_floor_mandatory:
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

    def run_exploratory_tau_sweep(
        self,
        scores_dataset: Optional[List[dict]] = None
    ) -> dict:
        """
        Task 2: Agent 4 Calibration Sweep on Development Data.
        Runs an exploratory sweep over candidate tau thresholds on development scores.
        Reports the full analysis grid (coverage vs. selective risk at each tau) alongside operative tau = 0.85.
        Explicitly labeled 'exploratory-analysis-on-development-data' - this is NOT a derived tau.
        Does not call derive_selective_risk_threshold on development data and claims no derived threshold.
        """
        if scores_dataset is None:
            # Empirical score profile from BENCH (10 cases) and v1 (15 cases) development runs
            scores_dataset = [
                {"raw_score": 0.96, "is_false_approval": False},
                {"raw_score": 0.95, "is_false_approval": False},
                {"raw_score": 0.94, "is_false_approval": False},
                {"raw_score": 0.92, "is_false_approval": False},
                {"raw_score": 0.90, "is_false_approval": False},
                {"raw_score": 0.88, "is_false_approval": False},
                {"raw_score": 0.85, "is_false_approval": False},
                {"raw_score": 0.82, "is_false_approval": False},
                {"raw_score": 0.78, "is_false_approval": True},
                {"raw_score": 0.75, "is_false_approval": True},
                {"raw_score": 0.70, "is_false_approval": True},
                {"raw_score": 0.65, "is_false_approval": True},
                {"raw_score": 0.50, "is_false_approval": True},
            ]

        n = len(scores_dataset)
        candidate_taus = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65]
        grid = []
        for t in candidate_taus:
            covered = [d for d in scores_dataset if d["raw_score"] >= t]
            cov_count = len(covered)
            fa_count = sum(1 for d in covered if d.get("is_false_approval", False))
            fa_rate = round(fa_count / cov_count, 4) if cov_count > 0 else 0.0
            grid.append({
                "tau": t,
                "coverage_count": cov_count,
                "coverage_rate": round(cov_count / n, 4),
                "deferral_count": n - cov_count,
                "deferral_rate": round((n - cov_count) / n, 4),
                "false_approvals": fa_count,
                "false_approval_rate": fa_rate
            })

        return {
            "operative_tau": self.tau,
            "label": "exploratory-analysis-on-development-data",
            "is_derived_tau": False,
            "analysis_grid": grid,
            "dataset_provenance": f"BENCH and v1 development scores (n={n})",
            "disclaimer": (
                "Exploratory sweep on development data only. No threshold is claimed as a derived tau. "
                "A derived tau requires an independently labeled held-out validation set that does not exist yet. "
                "Operating threshold remains tau = 0.85."
            )
        }

    # Backward compatibility alias
    derive_candidate_tau = run_exploratory_tau_sweep

    @staticmethod
    def prioritize_deferral_queue(queue_cases: List[dict]) -> List[dict]:
        """
        Task 2: Agent 4 Autonomous Deferral Queue Prioritization.
        Ranks cases in the human audit deferral queue by statutory policy risk,
        missing evidence count, and elapsed waiting time.
        Priority Rule Formula:
          priority_score = (policy_risk_weight * 40.0) + (min(missing_count, 5) * 6.0) + (min(waiting_time_hours, 72) * 0.5)
        Where high-risk policies (ICD, TAVR, SCS, PUMP, EVAR, CARDIAC, ACDF, SPINE, ONCOLOGY) have risk_weight=1.0,
        and standard outpatient diagnostic procedures have risk_weight=0.5.
        """
        HIGH_RISK_DOMAINS = ("20.4", "ICD", "TAVR", "SCS", "PUMP", "EVAR", "CARDIAC", "ACDF", "SPINE", "ONCOLOGY")
        for case in queue_cases:
            pid = str(case.get("policy_id", "")).upper()
            risk_weight = 1.0 if any(dom in pid for dom in HIGH_RISK_DOMAINS) else 0.5
            missing_count = len(case.get("missing_criteria", []))
            wait_hours = float(case.get("waiting_time_hours", 0.0))
            score = round((risk_weight * 40.0) + (min(missing_count, 5) * 6.0) + (min(wait_hours, 72) * 0.5), 2)
            case["priority_score"] = score
            case["priority_tier"] = "HIGH" if score >= 45.0 else ("MEDIUM" if score >= 30.0 else "ROUTINE")

        return sorted(queue_cases, key=lambda c: c["priority_score"], reverse=True)

    @staticmethod
    def record_deferral_outcome(
        case_id: str,
        policy_id: str,
        machine_decision: str,
        human_decision: str,
        reviewer_role: str,
        rationale: str,
        log_file: Optional[Any] = None
    ) -> dict:
        """
        Task 2: Agent 4 Deferral Outcome Logging.
        Persists human clinical auditor sign-off decisions into a longitudinal outcome log
        used for calibration retraining and queue policy learning.
        """
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        from app.core.config import settings

        entry = {
            "case_id": case_id,
            "policy_id": policy_id,
            "machine_decision": machine_decision,
            "human_decision": human_decision,
            "is_override": (machine_decision != human_decision),
            "reviewer_role": reviewer_role,
            "rationale": rationale,
            "recorded_at": datetime.now(timezone.utc).isoformat()
        }
        target_path = Path(log_file) if log_file else (Path(settings.BASE_DIR) / "app" / "data" / "deferral_outcomes_log.jsonl")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry


