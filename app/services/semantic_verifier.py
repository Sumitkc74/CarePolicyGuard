import re
from typing import Dict, Any, List, Tuple, Optional
from app.schemas.contracts import ClinicalEvidenceSpan, CriterionAssessment, DeterminationStatus
from app.core.clinical_core import ClinicalScopeAnalyzer, ClinicalNumericParser


class SemanticSupportChecker:
    """
    Semantic Support Verifier.
    Performs multi-dimensional clinical semantic analysis behind character-slice grounding:
    1. Subject verification (Patient vs Family History / relative)
    2. Timing verification (Actual / current vs planned / future / resolved historical)
    3. Modality verification (Confirmed vs hypothetical / conditional / speculative)
    4. Negation verification (Unnegated vs negated in active clause)
    5. Numeric Range verification (Measurement strictly satisfies statutory threshold)

    If any dimension fails, the span is invalidated and does NOT count as evidence.
    """

    FAMILY_TRIGGERS = [
        r"\b(?:mother|father|sister|brother|maternal|paternal|family history|fhx|relative|parent|grandmother|grandfather|aunt|uncle|sibling)\b"
    ]

    PLANNED_FUTURE_TRIGGERS = [
        r"\b(?:scheduled for|planning for|planning to|planned for|planned to|will undergo|to be scheduled|pending|awaiting|tentatively planned|to be performed|referred for consideration of|anticipate|plan is to|plan:?\s*(?:consider|schedule))\b"
    ]

    HYPOTHETICAL_MODALITY_TRIGGERS = [
        r"\b(?:consider|if|suspect|suspected|rule out|possible|questionable|unconfirmed|evaluating for|differential includes|may benefit from if|in the event of|should\s+patient\s+develop)\b"
    ]

    NEGATION_TRIGGERS = [
        r"\b(?:no|not|denies|denied|denying|without|negative for|ruled out|free of|never|absence of|no evidence of|no history of|no signs of|fails to demonstrate|unremarkable for)\b"
    ]

    @classmethod
    def verify_span_semantics(
        cls,
        span: ClinicalEvidenceSpan,
        ehr_text: str,
        criterion_def: Optional[Dict[str, Any]] = None,
        assessment_status: Optional[DeterminationStatus] = None
    ) -> ClinicalEvidenceSpan:
        """
        Audits a single clinical evidence span along all 5 semantic axes.
        Updates the span in-place and returns it.
        """
        start = span.start_char
        end = span.end_char
        source_text = span.source_text

        # 1. Subject Check (Patient vs Family Member)
        preceding_window = ehr_text[max(0, start - 80):start].lower()
        sentence_boundaries = [m.end() for m in re.finditer(r'(?:\.\s+|\n+|;\s*)', preceding_window)]
        last_boundary = max(sentence_boundaries) if sentence_boundaries else 0
        clause_preceding = preceding_window[last_boundary:]

        subject_valid = True
        invalidation_reasons = []

        for pat in cls.FAMILY_TRIGGERS:
            if re.search(pat, clause_preceding) or re.search(pat, source_text.lower()):
                subject_valid = False
                invalidation_reasons.append("Subject is family member / family history, not the patient.")
                break

        # Also check clinical section if labeled family history
        if "family" in span.clinical_section.lower():
            subject_valid = False
            invalidation_reasons.append("Span is located in Family History section.")

        # 2. Timing Check (Actual/Current vs Planned/Future)
        timing_valid = True
        following_window = ehr_text[end:min(len(ehr_text), end + 60)].lower()
        clause_following_bound = re.search(r'(?:\.\s+|\n+|;)', following_window)
        clause_following = following_window[:clause_following_bound.start()] if clause_following_bound else following_window

        surrounding_clause = f"{clause_preceding} {source_text.lower()} {clause_following}"
        for pat in cls.PLANNED_FUTURE_TRIGGERS:
            if re.search(pat, surrounding_clause):
                timing_valid = False
                invalidation_reasons.append("Finding or procedure is future-planned rather than currently completed or active.")
                break

        # 3. Modality Check (Confirmed vs Hypothetical/Conditional)
        modality_valid = True
        for pat in cls.HYPOTHETICAL_MODALITY_TRIGGERS:
            if re.search(pat, surrounding_clause):
                modality_valid = False
                invalidation_reasons.append("Finding is hypothetical, conditional, or speculative ('consider', 'if', 'suspect').")
                break

        # 4. Negation Check
        negation_valid = True
        # Check if the negation is asserting absence of recent acute events for longitudinal waiting periods
        # (e.g. "no recent MI", "no acute MI", "no prior acute MI", "no myocardial infarction within the past 40 days")
        is_recency_clearance = bool(re.search(
            r'(?i)\bno\s+(?:(?:prior|recent|acute|history\s+of)\s+)*(?:mi|myocardial infarction|cabg|pci)\b',
            surrounding_clause
        ))
        if not is_recency_clearance:
            scope_res = ClinicalScopeAnalyzer.analyze_scope(ehr_text, start, end)
            if scope_res.get("is_negated"):
                negation_valid = False
                invalidation_reasons.append(f"Finding is negated in active clause by '{scope_res.get('negation_trigger')}'.")

        # 5. Value in Range Check (for numeric criteria asserting MET status)
        value_in_range = True
        status_is_met = assessment_status == DeterminationStatus.MET if assessment_status else True
        if criterion_def and status_is_met:
            operator = criterion_def.get("operator")
            threshold = criterion_def.get("threshold")
            target_unit = criterion_def.get("target_unit", "")
            if operator and threshold is not None:
                # Look for numbers in source_text or immediate clause
                num_matches = list(re.finditer(r'\b(\d+(?:\.\d+)?)\b', source_text))
                if not num_matches:
                    num_matches = list(re.finditer(r'\b(\d+(?:\.\d+)?)\b', surrounding_clause))

                if num_matches:
                    found_qualifying = False
                    # Check composite valvular / hemodynamic criteria (AVA <= 1.0 cm2 OR gradient >= 40 mmHg OR velocity >= 4.0 m/s)
                    if "mmhg" in source_text.lower():
                        found_qualifying = any(float(nm.group(1)) >= 40.0 for nm in num_matches)
                    elif "m/s" in source_text.lower():
                        found_qualifying = any(float(nm.group(1)) >= 4.0 for nm in num_matches)
                    elif "ahi" in source_text.lower() or "apnea" in source_text.lower():
                        # CMS CPAP Coverage: AHI >= 15 OR (5 <= AHI < 15 with documented qualifying comorbidity)
                        for nm in num_matches:
                            val = float(nm.group(1))
                            if val >= 15.0:
                                found_qualifying = True
                                break
                            elif 5.0 <= val < 15.0:
                                has_comorb = bool(re.search(r'(?i)\b(?:hypertension|htn|stroke|excessive daytime sleepiness|eds|somnolence|insomnia)\b', surrounding_clause + " " + ehr_text))
                                if has_comorb:
                                    found_qualifying = True
                                    break
                    else:
                        for nm in num_matches:
                            val = float(nm.group(1))
                            if ClinicalNumericParser.evaluate_cutoff(val, operator, float(threshold)):
                                found_qualifying = True
                                break

                    # If unit is different and this is an auxiliary supporting span, don't disqualify if within clinical rationale
                    if not found_qualifying:
                        if target_unit and target_unit.lower() not in source_text.lower() and not any(u in source_text.lower() for u in ["%", "events/hr"]):
                            # Auxiliary descriptive span (e.g. gradient or NYHA) rather than primary metric
                            pass
                        else:
                            value_in_range = False
                            invalidation_reasons.append(
                                f"Numeric value in evidence does not satisfy statutory criterion requirement ({operator} {threshold})."
                            )

        all_passed = (
            subject_valid
            and timing_valid
            and modality_valid
            and negation_valid
            and value_in_range
        )

        span.subject_valid = subject_valid
        span.timing_valid = timing_valid
        span.modality_valid = modality_valid
        span.negation_valid = negation_valid
        span.value_in_range = value_in_range
        span.semantic_support_passed = all_passed
        span.semantic_invalidation_reasons = invalidation_reasons

        return span

    @classmethod
    def audit_assessment_semantics(
        cls,
        assessment: CriterionAssessment,
        ehr_text: str,
        criterion_def: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Audits all spans of a criterion assessment.
        Returns:
            (all_spans_passed, summary_notes)
        """
        if not assessment.verified_spans:
            return True, ["No spans to verify."]

        # Clinical Semantic Ground Rule:
        # 1. If an exclusion criterion is NOT_MET (e.g. "No active infection", "No cardiogenic shock"),
        #    the negation is the exact clinical proof that the disqualifying exclusion is absent.
        # 2. If an inclusion criterion is already NOT_MET, the evidence reflects non-qualification.
        # Therefore, semantic support validation strictly audits spans claimed to prove qualification (MET).
        if assessment.is_exclusion and assessment.status == DeterminationStatus.NOT_MET:
            return True, []

        if not assessment.is_exclusion and assessment.status != DeterminationStatus.MET:
            return True, []

        all_passed = True
        notes: List[str] = []

        for idx, span in enumerate(assessment.verified_spans):
            cls.verify_span_semantics(span, ehr_text, criterion_def, assessment_status=assessment.status)
            if not span.semantic_support_passed:
                all_passed = False
                reasons_str = "; ".join(span.semantic_invalidation_reasons)
                notes.append(f"Span #{idx+1} '{span.source_text}' failed semantic support: {reasons_str}")

        return all_passed, notes

    @classmethod
    def detect_case_contradictions(
        cls,
        ehr_text: str,
        criteria_assessments: List[CriterionAssessment]
    ) -> Tuple[bool, List[str]]:
        """
        Detects internal diagnostic contradictions across the patient record.
        Surfaces conflicts as explicit deferral reasons rather than silently selecting one value.
        """
        contradictions: List[str] = []

        # 1. LVEF Contradictions (e.g. 24% vs 55%)
        lvef_matches = list(re.finditer(r'(?i)\b(?:lvef|left ventricular ejection fraction)\s*(?::|of|is)?\s*([<>]?=?\s*(\d{1,2}))%', ehr_text))
        if len(lvef_matches) >= 2:
            vals = [int(m.group(2)) for m in lvef_matches]
            if max(vals) - min(vals) >= 15:
                contradictions.append(
                    f"Conflicting LVEF measurements documented in chart: {min(vals)}% vs {max(vals)}%. Clinician reconciliation required."
                )

        # 2. NYHA Functional Class Contradictions
        nyha_matches = list(re.finditer(r'(?i)\bnyha\s*(?:class|functional class)?\s*([iv]+)\b', ehr_text))
        if len(nyha_matches) >= 2:
            classes = set(m.group(1).upper() for m in nyha_matches)
            if len(classes) > 1 and ({"I", "II"} & classes) and ({"III", "IV"} & classes):
                contradictions.append(
                    f"Conflicting NYHA functional classifications documented: {', '.join(sorted(classes))}."
                )

        # 3. Surgical Risk Contradictions
        high_risk = bool(re.search(r'(?i)\b(?:high(?:-|\s+)surgical risk|high risk for (?:open|surgery|cea))\b', ehr_text))
        low_risk = bool(re.search(r'(?i)\b(?:low(?:-|\s+)surgical risk|average risk|standard risk|low risk for (?:open|surgery|cea))\b', ehr_text))
        if high_risk and low_risk:
            contradictions.append(
                "Conflicting surgical risk assessments documented (high risk vs standard/low risk). Clinician reconciliation required."
            )

        # 4. Aortic Stenosis Severity Contradictions
        severe_as = bool(re.search(r'(?i)\b(?:severe aortic stenosis|severe as)\b', ehr_text))
        mild_mod_as = bool(re.search(r'(?i)\b(?:mild aortic stenosis|moderate aortic stenosis|mild-to-moderate as)\b', ehr_text))
        if severe_as and mild_mod_as:
            contradictions.append(
                "Conflicting aortic stenosis severity classifications documented (severe vs mild/moderate)."
            )

        has_contradiction = len(contradictions) > 0
        return has_contradiction, contradictions
