import re
from typing import Dict, Any, Optional, List, Tuple
from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType, DeclarativePolicy
from app.schemas.contracts import CriterionAssessment, ClinicalEvidenceSpan, DeterminationStatus
from app.agents.criteria_evaluator import CriteriaEvaluationAgent

class DeclarativePolicyEngine:
    """
    Policy-as-Data Declarative Evaluation Engine.
    Executes declarative criterion schemas deterministically against clinical EHR documentation.
    Replaces brittle hand-coded procedural branches with a modular, scalable compiler.
    """

    @classmethod
    def compile_from_dict(cls, data: Dict[str, Any]) -> DeclarativeCriterion:
        """
        Translates raw database rows or dictionary criteria into strongly-typed DeclarativeCriterion.
        Infers criterion_type, entity synonyms, and operational thresholds.
        """
        code = data.get("criterion_code", "CRIT-UNKNOWN")
        name = data.get("name", "")
        desc = data.get("description", "")
        is_excl = bool(data.get("is_exclusion", False))
        keywords = data.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        code_low = code.lower()
        desc_low = desc.lower()
        name_low = name.lower()

        c_type = CriterionType.FINDING_PRESENCE
        operator = None
        threshold = None
        unit = None
        ordinals = None
        min_days = None

        if is_excl:
            c_type = CriterionType.EXCLUSION_SYMPTOM
        elif "lvef" in code_low or "lvef" in desc_low or "ejection fraction" in desc_low:
            c_type = CriterionType.NUMERIC_THRESHOLD
            operator = "<="
            threshold = 35.0
            unit = "%"
        elif "ahi" in code_low or "ahi" in desc_low or "apnea" in desc_low:
            c_type = CriterionType.NUMERIC_THRESHOLD
            operator = ">="
            threshold = 15.0
            unit = "events/hr"
        elif "nyha" in code_low or "nyha" in desc_low or "functional class" in desc_low:
            c_type = CriterionType.ORDINAL_RANK
            ordinals = ["II", "III", "IV"]
        elif "gdmt" in code_low or "duration" in desc_low or "days" in desc_low or "medical therapy" in desc_low:
            c_type = CriterionType.TEMPORAL_DURATION
            min_days = 90
            operator = ">="
        elif "mr" in code_low or "regurgitation" in desc_low:
            c_type = CriterionType.ORDINAL_RANK
            ordinals = ["3+", "4+", "SEVERE", "MODERATE-TO-SEVERE"]

        entity_names = list(set(keywords + [name]))

        return DeclarativeCriterion(
            criterion_code=code,
            name=name,
            description=desc,
            clinical_intent=data.get("clinical_intent", "Coverage qualification requirement"),
            criterion_type=c_type,
            entity_names=entity_names,
            operator=operator,
            threshold=threshold,
            target_unit=unit,
            ordinal_allowed=ordinals,
            min_duration_days=min_days,
            is_exclusion=is_excl,
            required_temporal_window=data.get("required_temporal_window", "Within past 12 months"),
            min_score=data.get("min_score", 0.85)
        )

    @classmethod
    def evaluate(cls, criterion: DeclarativeCriterion, ehr_text: str) -> CriterionAssessment:
        """
        Deterministically evaluates a DeclarativeCriterion against raw EHR narrative.
        Ensures exact character slice grounding, negation scoping, and explicit rationales.
        """
        spans: List[ClinicalEvidenceSpan] = []
        status = DeterminationStatus.INSUFFICIENT_EVIDENCE
        rationale = "No documented clinical evidence matching statutory criteria."
        raw_confidence = 0.50

        # 1. Scope and Negation Analyzer helper from CriteriaEvaluationAgent
        analyzer = CriteriaEvaluationAgent()

        # 2. Evaluation according to Declarative Paradigm
        if criterion.criterion_type == CriterionType.NUMERIC_THRESHOLD:
            # Handle numeric cutoffs (LVEF <= 35%, AHI >= 15, etc.)
            search_terms = criterion.entity_names or [criterion.name]
            num_match = None

            # Pattern for numeric clinical metrics
            metric_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in search_terms) + r')[^\d\n]*?([<>]?=?\s*(\d{1,3}(?:\.\d+)?))\s*([%a-zA-Z/]*)'
            m = re.search(metric_pattern, ehr_text)
            if m:
                raw_num_str = m.group(2)
                try:
                    val = float(raw_num_str)
                    s_idx = m.start()
                    e_idx = m.end()

                    # NegEx scope check
                    scope = analyzer.analyze_clinical_scope(ehr_text, s_idx, e_idx)
                    if not scope["is_negated"]:
                        op = criterion.operator or "<="
                        thresh = criterion.threshold if criterion.threshold is not None else 35.0
                        passed = False
                        if op in ("<=", "le"):
                            passed = (val <= thresh)
                        elif op in (">=", "ge"):
                            passed = (val >= thresh)
                        elif op in ("<", "lt"):
                            passed = (val < thresh)
                        elif op in (">", "gt"):
                            passed = (val > thresh)
                        elif op in ("==", "eq"):
                            passed = abs(val - thresh) < 1e-4

                        span_obj = ClinicalEvidenceSpan(
                            source_text=ehr_text[s_idx:e_idx],
                            start_char=s_idx,
                            end_char=e_idx,
                            clinical_section=analyzer.detect_clinical_section(ehr_text, s_idx),
                            confidence=0.98
                        )
                        spans.append(span_obj)

                        if passed:
                            status = DeterminationStatus.MET
                            raw_confidence = 0.98
                            rationale = f"Statutory metric verified: {val}{criterion.target_unit or ''} satisfies {op} {thresh} threshold."
                        else:
                            status = DeterminationStatus.NOT_MET
                            raw_confidence = 0.95
                            rationale = f"Metric fails statutory threshold: {val}{criterion.target_unit or ''} does not satisfy {op} {thresh}."
                except ValueError:
                    pass

        elif criterion.criterion_type == CriterionType.ORDINAL_RANK:
            # Handle ordinal stages (e.g. NYHA Class II/III, MR Grade 3+/4+)
            search_terms = criterion.entity_names or [criterion.name]
            ord_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in search_terms) + r')[^\n\.]*?\b(?:class\s+|grade\s+)?([ivx0-9\+\-]+)'
            m = re.search(ord_pattern, ehr_text)
            if m:
                found_rank = m.group(1).upper().strip()
                s_idx = m.start()
                e_idx = m.end()

                scope = analyzer.analyze_clinical_scope(ehr_text, s_idx, e_idx)
                if not scope["is_negated"]:
                    span_obj = ClinicalEvidenceSpan(
                        source_text=ehr_text[s_idx:e_idx],
                        start_char=s_idx,
                        end_char=e_idx,
                        clinical_section=analyzer.detect_clinical_section(ehr_text, s_idx),
                        confidence=0.95
                    )
                    spans.append(span_obj)
                    allowed = criterion.ordinal_allowed or ["II", "III", "IV"]
                    if found_rank in allowed or any(a in found_rank for a in allowed):
                        status = DeterminationStatus.MET
                        raw_confidence = 0.95
                        rationale = f"Qualifying functional/severity stage confirmed: {found_rank} in {allowed}."
                    else:
                        status = DeterminationStatus.NOT_MET
                        raw_confidence = 0.90
                        rationale = f"Non-qualifying stage: {found_rank} not in qualifying list {allowed}."

        elif criterion.criterion_type == CriterionType.TEMPORAL_DURATION:
            # Handle medical therapy duration (e.g. GDMT >= 90 days)
            duration_pattern = r'(?i)\b(?:gdmt|medical therapy|optimal therapy|treatment)[^\n\.]*?\b(?:for\s+)?(?:[><=~]+\s*)?(\d+)\s*(days|weeks|months)'
            m = re.search(duration_pattern, ehr_text)
            if m:
                count = int(m.group(1))
                unit_str = m.group(2).lower()
                days = count * 30 if "month" in unit_str else (count * 7 if "week" in unit_str else count)
                s_idx = m.start()
                e_idx = m.end()

                scope = analyzer.analyze_clinical_scope(ehr_text, s_idx, e_idx)
                if not scope["is_negated"]:
                    span_obj = ClinicalEvidenceSpan(
                        source_text=ehr_text[s_idx:e_idx],
                        start_char=s_idx,
                        end_char=e_idx,
                        clinical_section=analyzer.detect_clinical_section(ehr_text, s_idx),
                        confidence=0.96
                    )
                    spans.append(span_obj)
                    min_req = criterion.min_duration_days or 90
                    if days >= min_req:
                        status = DeterminationStatus.MET
                        raw_confidence = 0.96
                        rationale = f"Documented therapy duration ({days} days) satisfies statutory minimum of {min_req} days."
                    else:
                        status = DeterminationStatus.NOT_MET
                        raw_confidence = 0.92
                        rationale = f"Insufficient therapy duration ({days} days < statutory requirement of {min_req} days)."

        elif criterion.criterion_type == CriterionType.EXCLUSION_SYMPTOM:
            # Handle statutory exclusions (e.g. cardiogenic shock, life expectancy < 1 yr)
            search_terms = criterion.entity_names or [criterion.name]
            excl_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in search_terms) + r')\b'
            m = re.search(excl_pattern, ehr_text)
            if m:
                s_idx = m.start()
                e_idx = m.end()
                scope = analyzer.analyze_clinical_scope(ehr_text, s_idx, e_idx)

                span_obj = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=analyzer.detect_clinical_section(ehr_text, s_idx),
                    confidence=0.95
                )
                spans.append(span_obj)

                if scope["is_negated"]:
                    # Condition is negated e.g. "No cardiogenic shock" -> Exclusion NOT met (Coverage Allowed)
                    status = DeterminationStatus.NOT_MET
                    raw_confidence = 0.95
                    rationale = f"Statutory exclusion condition ruled out: documented as absent or resolved ({scope['negation_trigger']})."
                else:
                    # Condition is active -> Exclusion MET (Coverage Blocked)
                    status = DeterminationStatus.MET
                    raw_confidence = 0.95
                    rationale = f"Active statutory exclusion identified: patient manifests disqualifying condition."
            else:
                # Absence of mention for exclusion defaults to NOT_MET (clean)
                status = DeterminationStatus.NOT_MET
                raw_confidence = 0.90
                rationale = "No documented statutory exclusion conditions identified in EHR narrative."

        else:
            # CriterionType.FINDING_PRESENCE (General diagnostic finding)
            search_terms = criterion.entity_names or [criterion.name]
            found = False
            for term in search_terms:
                idx = ehr_text.lower().find(term.lower())
                if idx != -1:
                    e_idx = idx + len(term)
                    scope = analyzer.analyze_clinical_scope(ehr_text, idx, e_idx)
                    span_obj = ClinicalEvidenceSpan(
                        source_text=ehr_text[idx:e_idx],
                        start_char=idx,
                        end_char=e_idx,
                        clinical_section=analyzer.detect_clinical_section(ehr_text, idx),
                        confidence=0.90
                    )
                    spans.append(span_obj)
                    if not scope["is_negated"]:
                        status = DeterminationStatus.MET
                        raw_confidence = 0.92
                        rationale = f"Clinical finding documented: '{term}'."
                        found = True
                        break
                    else:
                        status = DeterminationStatus.NOT_MET
                        raw_confidence = 0.90
                        rationale = f"Documented finding was explicitly negated ({scope['negation_trigger']})."
                        found = True
                        break

        return CriterionAssessment(
            criterion_id=criterion.criterion_code,
            criterion_code=criterion.criterion_code,
            name=criterion.name,
            description=criterion.description,
            is_exclusion=criterion.is_exclusion,
            required_temporal_window=criterion.required_temporal_window or "Not specified",
            status=status,
            clinical_rationale=rationale,
            raw_confidence=raw_confidence,
            verified_spans=spans
        )
