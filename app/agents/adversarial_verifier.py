import re
from typing import List, Dict, Any, Tuple, Optional
from app.schemas.contracts import (
    CriterionAssessment,
    VerificationAuditResult,
    DeterminationStatus,
    ClinicalEvidenceSpan
)
from app.agents.criteria_evaluator import CriteriaEvaluationAgent

class AdversarialVerificationAgent:
    """
    Agent 3: Adversarial Verification Agent
    Audits extracted clinical evidence by:
    1. Executing programmatic character-level string slice checks against raw EHR text to intercept hallucinations and offset drifts.
    2. Auditing unverified negative omissions (detecting cases where policy terms exist in notes but were marked NOT_MET without citation).
    3. Applying calibrated penalization to confidence scores based on grounding integrity.
    """

    def __init__(self):
        pass

    def verify_spans_programmatic(
        self,
        spans: List[ClinicalEvidenceSpan],
        ehr_text: str
    ) -> Tuple[bool, bool, bool, List[str]]:
        """
        Executes character-level slice checks:
        Returns: (all_grounded, hallucination_flag, offset_drift_detected, notes)
        """
        if not spans:
            return True, False, False, ["No clinical spans cited."]

        all_grounded = True
        hallucination_flag = False
        offset_drift_detected = False
        notes: List[str] = []

        for idx, span in enumerate(spans):
            claimed_start = span.start_char
            claimed_end = span.end_char
            claimed_text = span.source_text

            # Boundary safety
            if claimed_start < 0 or claimed_end > len(ehr_text) or claimed_start >= claimed_end:
                all_grounded = False
                hallucination_flag = True
                notes.append(f"Span #{idx+1} invalid offsets [{claimed_start}:{claimed_end}] for text length {len(ehr_text)}.")
                continue

            actual_slice = ehr_text[claimed_start:claimed_end]

            if actual_slice == claimed_text:
                notes.append(f"Span #{idx+1} verified: Character-perfect match [{claimed_start}:{claimed_end}].")
            else:
                all_grounded = False
                # Check if claimed text exists elsewhere in note (Offset Drift)
                if claimed_text in ehr_text:
                    offset_drift_detected = True
                    actual_first_pos = ehr_text.find(claimed_text)
                    notes.append(
                        f"Span #{idx+1} OFFSET DRIFT: Claimed [{claimed_start}:{claimed_end}] but actual match found at [{actual_first_pos}:{actual_first_pos + len(claimed_text)}]."
                    )
                else:
                    # Claimed text does not exist anywhere in EHR -> Hallucination!
                    hallucination_flag = True
                    notes.append(
                        f"Span #{idx+1} HALLUCINATION: Text '{claimed_text[:40]}...' does not exist in EHR narrative."
                    )

        return all_grounded, hallucination_flag, offset_drift_detected, notes

    def audit_negative_omissions(
        self,
        assessment: CriterionAssessment,
        criterion_def: Dict[str, Any],
        ehr_text: str
    ) -> Tuple[bool, str]:
        """
        Detects unverified negative omissions:
        If a criterion is marked NOT_MET or INSUFFICIENT_EVIDENCE, but the EHR contains
        high-salience keywords suggesting the criterion was actually discussed or met,
        flag this critical omission.
        """
        # Only audit if marked NOT_MET or INSUFFICIENT_EVIDENCE
        if assessment.status not in [DeterminationStatus.NOT_MET, DeterminationStatus.INSUFFICIENT_EVIDENCE]:
            return False, "Criterion assessed as MET; omission audit not triggered."

        crit_context = (
            assessment.criterion_code + " " +
            (assessment.name or "") + " " +
            (assessment.description or "") + " " +
            (
                " ".join(criterion_def.get("keywords", []))
                if isinstance(criterion_def.get("keywords"), list)
                else str(criterion_def.get("keywords", ""))
            )
        ).lower()
        text_lower = ehr_text.lower()
        omission_flag = False
        omission_note = ""

        # Specific checks based on clinical criterion type
        if "lvef" in crit_context or "ejection fraction" in crit_context:
            if re.search(r'(?i)\blvef\b|\bejection fraction\b', text_lower):
                omission_flag = True
                omission_note = "UNVERIFIED OMISSION: EHR note mentions LVEF / ejection fraction, but criterion was evaluated as non-qualifying without citation."

        elif "nyha" in crit_context or "functional class" in crit_context:
            if re.search(r'(?i)\bnyha\b|\bfunctional class\b', text_lower):
                omission_flag = True
                omission_note = "UNVERIFIED OMISSION: EHR note mentions NYHA functional classification, but criterion was marked negative/insufficient."

        elif "gdmt" in crit_context or "medical therapy" in crit_context:
            if re.search(r'(?i)\b(carvedilol|metoprolol|lisinopril|entresto|spironolactone|gdmt)\b', text_lower):
                omission_flag = True
                omission_note = "UNVERIFIED OMISSION: EHR note documents heart failure medications (beta-blocker, ACEi/ARNI), but criterion was marked NOT_MET without citing these therapies."

        elif "ahi" in crit_context or "apnea" in crit_context or "sleep" in crit_context:
            has_ahi_span = any(
                re.search(r'(?i)\b(?:ahi|apnea-hypopnea index|polysomnography|sleep study)\b', s.source_text)
                for s in (assessment.verified_spans or [])
            )
            if has_ahi_span:
                # AHI was cited; check if there is an unnegated comorbidity in the note that was omitted
                comorb_matches = list(re.finditer(r'(?i)\b(excessive daytime sleepiness|eds|hypertension|htn|insomnia|ischemic heart disease|stroke)\b', text_lower))
                unnegated_comorb = False
                for m in comorb_matches:
                    scope = CriteriaEvaluationAgent.analyze_clinical_scope(ehr_text, m.start(), m.end())
                    if not scope["is_negated"]:
                        unnegated_comorb = True
                        break
                if unnegated_comorb:
                    omission_flag = True
                    omission_note = "UNVERIFIED OMISSION: EHR note mentions qualifying comorbid conditions that were not credited for AHI 5-14 band."
            else:
                if re.search(r'(?i)\bahi\b|\bapnea-hypopnea index\b', text_lower):
                    omission_flag = True
                    omission_note = "UNVERIFIED OMISSION: EHR note documents AHI / polysomnography indices, but sleep study criterion was marked NOT_MET without citation."

        elif "wagner" in crit_context or "ulcer" in crit_context:
            if re.search(r'(?i)\bwagner\b|\bosteomyelitis\b|\bgangrene\b|\bdeep ulcer\b', text_lower):
                omission_flag = True
                omission_note = "UNVERIFIED OMISSION: EHR note documents deep diabetic ulceration / Wagner staging terms, but criterion was marked negative."

        return omission_flag, omission_note

    def audit_discordance(
        self,
        assessment: CriterionAssessment,
        ehr_text: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Detects internal diagnostic contradictions across the patient chart.
        For example: Conflicting LVEF measurements (e.g. 24% vs 52%) or contradictory NYHA classes.
        """
        code_lower = (assessment.criterion_code + " " + (assessment.name or "") + " " + (assessment.description or "")).lower()
        if "lvef" in code_lower or "ejection fraction" in code_lower:
            matches = list(re.finditer(r'(?i)\b(?:lvef|left ventricular ejection fraction)\s*(?::|of|is)?\s*([<>]?=?\s*(\d{1,2}))%', ehr_text))
            if len(matches) >= 2:
                values = [int(m.group(2)) for m in matches]
                diff = max(values) - min(values)
                if diff >= 15:
                    return True, f"CLINICAL DISCORDANCE: Multiple conflicting LVEF measurements found in chart ({min(values)}% vs {max(values)}%). Requires clinician reconciliation."
        elif "nyha" in code_lower:
            nyha_matches = list(re.finditer(r'(?i)\bnyha\s*(?:class|functional class)?\s*([iv]+)\b', ehr_text))
            if len(nyha_matches) >= 2:
                classes = set(m.group(1).upper() for m in nyha_matches)
                if len(classes) > 1 and ({"I", "II"} & classes) and ({"III", "IV"} & classes):
                    return True, f"CLINICAL DISCORDANCE: Conflicting NYHA functional classes documented ({', '.join(sorted(classes))})."
        elif "risk" in code_lower or "surgical" in code_lower:
            high_risk_found = bool(re.search(r'(?i)\b(?:high(?:-|\s+)surgical risk|high risk for (?:open|surgery|cea))\b', ehr_text))
            low_risk_found = bool(re.search(r'(?i)\b(?:low(?:-|\s+)surgical risk|average risk|standard risk|low risk for (?:open|surgery|cea))\b', ehr_text))
            if high_risk_found and low_risk_found:
                return True, "CLINICAL DISCORDANCE: Conflicting surgical risk assessments documented (high risk vs low/standard risk). Requires clinician reconciliation."
        return False, None

    def heal_offset_drift(
        self,
        span: ClinicalEvidenceSpan,
        ehr_text: str
    ) -> bool:
        """
        Autonomously resolves offset drift by anchoring the span to its true position in the raw text.
        """
        if span.source_text in ehr_text:
            pos = ehr_text.find(span.source_text)
            span.start_char = pos
            span.end_char = pos + len(span.source_text)
            return True
        return False

    def recalibrate_confidence(
        self,
        raw_confidence: float,
        grounding_status: bool,
        hallucination_flag: bool,
        offset_drift_detected: bool,
        unverified_omission_flag: bool,
        discordance_flag: bool = False
    ) -> float:
        """
        Recalibrates confidence using adversarial penalization:
        - Hallucination: massive penalization (factor 0.20)
        - Unverified Omission: severe penalization (factor 0.45)
        - Offset Drift: moderate penalization (factor 0.65)
        - Perfect Grounding: retain or slight boost
        """
        score = raw_confidence

        if hallucination_flag:
            score *= 0.20
        elif offset_drift_detected:
            score *= 0.65
        elif not grounding_status:
            score *= 0.50

        if unverified_omission_flag:
            score *= 0.45

        if discordance_flag:
            score *= 0.50

        return round(max(0.05, min(0.99, score)), 4)

    def audit_assessment(
        self,
        assessment: CriterionAssessment,
        criterion_def: Dict[str, Any],
        ehr_text: str
    ) -> VerificationAuditResult:
        """
        Runs comprehensive adversarial verification across spans, offsets, and omissions.
        """
        all_grounded, hallucination_flag, offset_drift, span_notes = self.verify_spans_programmatic(
            assessment.verified_spans,
            ehr_text
        )

        omission_flag, omission_note = self.audit_negative_omissions(
            assessment,
            criterion_def,
            ehr_text
        )

        discordance_flag, discordance_note = self.audit_discordance(assessment, ehr_text)

        calibrated_conf = self.recalibrate_confidence(
            assessment.raw_confidence,
            all_grounded,
            hallucination_flag,
            offset_drift,
            omission_flag,
            discordance_flag=discordance_flag
        )

        audit_summary_parts = span_notes.copy()
        if omission_flag:
            audit_summary_parts.append(omission_note)
        if discordance_flag and discordance_note:
            audit_summary_parts.append(discordance_note)

        audit_notes = " | ".join(audit_summary_parts) if audit_summary_parts else "Adversarial verification passed: evidence fully grounded."

        return VerificationAuditResult(
            criterion_code=assessment.criterion_code,
            grounding_status=all_grounded,
            hallucination_flag=hallucination_flag,
            unverified_omission_flag=omission_flag,
            offset_drift_detected=offset_drift,
            discordance_flag=discordance_flag,
            healed_offset_drift=False,
            audit_notes=audit_notes,
            calibrated_confidence=calibrated_conf
        )

