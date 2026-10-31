import os
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType, DeclarativePolicy
from app.schemas.contracts import CriterionAssessment, ClinicalEvidenceSpan, DeterminationStatus
from app.agents.criteria_evaluator import CriteriaEvaluationAgent

class DeclarativePolicyEngine:
    """
    Policy-as-Data Declarative Evaluation Engine.
    Loads and executes declarative JSON policy schemas deterministically against clinical EHR documentation.
    Enables adding any new CMS LCD or NCD via pure structured JSON/YAML with zero Python code changes.
    """

    _POLICY_CACHE: Dict[str, DeclarativePolicy] = {}

    @classmethod
    def get_policies_dir(cls) -> Path:
        """Returns the path to the declarative policy JSON store."""
        return Path(__file__).resolve().parent.parent / "data" / "policies"

    @classmethod
    def load_policy(cls, policy_id: str) -> Optional[DeclarativePolicy]:
        """Loads a DeclarativePolicy from declarative JSON specification."""
        clean_id = policy_id.strip()
        if clean_id in cls._POLICY_CACHE:
            return cls._POLICY_CACHE[clean_id]

        file_path = cls.get_policies_dir() / f"{clean_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            policy = DeclarativePolicy(**data)
            cls._POLICY_CACHE[clean_id] = policy
            return policy
        except Exception:
            return None

    @classmethod
    def get_all_policies(cls) -> List[DeclarativePolicy]:
        """Loads all available declarative policies from JSON store."""
        policies = []
        p_dir = cls.get_policies_dir()
        if p_dir.exists():
            for p_file in p_dir.glob("*.json"):
                pol = cls.load_policy(p_file.stem)
                if pol:
                    policies.append(pol)
        return policies

    @classmethod
    def compile_from_dict(cls, data: Dict[str, Any]) -> DeclarativeCriterion:
        """
        Translates raw dictionary or DB rows into a strongly-typed DeclarativeCriterion.
        Prioritizes explicitly declared schema fields (threshold, operator, unit, ordinals);
        falls back to inferred defaults if reading unannotated legacy database records.
        """
        code = data.get("criterion_code", "CRIT-UNKNOWN")
        name = data.get("name", "")
        desc = data.get("description", "")
        is_excl = bool(data.get("is_exclusion", False))
        keywords = data.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        # 1. Use explicitly declared fields if present in data
        if "threshold" in data and data["threshold"] is not None:
            c_type = data.get("criterion_type", CriterionType.NUMERIC_THRESHOLD)
            return DeclarativeCriterion(
                criterion_code=code,
                name=name,
                description=desc,
                clinical_intent=data.get("clinical_intent", "Declared policy requirement"),
                criterion_type=c_type,
                entity_names=data.get("entity_names") or list(set(keywords + [name])),
                operator=data.get("operator", "<="),
                threshold=float(data["threshold"]),
                target_unit=data.get("target_unit"),
                ordinal_allowed=data.get("ordinal_allowed"),
                min_duration_days=data.get("min_duration_days"),
                is_exclusion=is_excl,
                negation_sensitive=data.get("negation_sensitive", True),
                required_temporal_window=data.get("required_temporal_window", "Within past 12 months"),
                min_score=data.get("min_score", 0.85)
            )

        # 2. Check if a declarative policy JSON file already defines this criterion code
        for pol in cls.get_all_policies():
            for crit in pol.criteria:
                if crit.criterion_code.upper() == code.upper():
                    return crit

        # 3. Fallback heuristic inference for unseeded legacy DB rows
        code_low = code.lower()
        desc_low = desc.lower()

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

        # Scope and Negation Analyzer helper from CriteriaEvaluationAgent
        analyzer = CriteriaEvaluationAgent()

        if criterion.criterion_type == CriterionType.NUMERIC_THRESHOLD:
            # Handle numeric cutoffs (LVEF <= 35%, AHI >= 15, CHA2DS2-VASc >= 3, etc.)
            search_terms = criterion.entity_names or [criterion.name]
            target_unit = (criterion.target_unit or "").strip()
            
            # Identify core metric abbreviations/names (e.g., AHI, LVEF, AVA, PaO2, SpO2, CHA2DS2-VASc, HAS-BLED)
            score_metrics = {"cha2ds2-vasc", "chads-vasc", "has-bled", "cha2ds2", "chads2", "sts score", "epworth", "ahi", "lvef", "ava", "pao2", "spo2"}
            core_metrics = [t for t in search_terms if len(t) <= 6 or t.isupper() or t.lower() in score_metrics or t.lower() in ("apnea-hypopnea index", "ejection fraction", "aortic valve area")]
            metric_candidates = []

            # Strategy 0: Dedicated clinical score extraction for score-based scales (e.g. CHA2DS2-VASc score is 4, HAS-BLED: 3)
            score_terms = [t for t in search_terms if "cha" in t.lower() or "bled" in t.lower() or "score" in t.lower()]
            if score_terms:
                score_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in score_terms) + r')\b(?:\s*score)?\s*(?:calculated at|is|of|:|=)?\s*(?<![a-zA-Z0-9])([<>]?=?\s*(\d{1,2}(?:\.\d+)?))(?![a-zA-Z0-9])'
                for m_cand in re.finditer(score_pattern, ehr_text):
                    metric_candidates.append(m_cand)

            # Strategy 1: Look for matches anchored to the specific target_unit (events/hr, %, mmHg, cm2, points)
            if not metric_candidates and target_unit and target_unit.lower() != "points":
                escaped_unit = re.escape(target_unit)
                unit_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in search_terms) + r')[^\d\n\.]*?(?<![a-zA-Z0-9])([<>]?=?\s*(\d{1,3}(?:\.\d+)?))\s*' + escaped_unit + r'(?![a-zA-Z0-9])'
                for m_cand in re.finditer(unit_pattern, ehr_text):
                    metric_candidates.append(m_cand)

            # Strategy 2: Look for core metric tokens directly adjacent to values, skipping date patterns and preventing internal token digit extraction
            if not metric_candidates and core_metrics:
                core_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in core_metrics) + r')\b[^\d\n\.]*?(?<![a-zA-Z0-9])([<>]?=?\s*(\d{1,3}(?:\.\d+)?))(?![a-zA-Z0-9])'
                for m_cand in re.finditer(core_pattern, ehr_text):
                    end_pos = m_cand.end(2)
                    after_text = ehr_text[end_pos:end_pos+5]
                    before_text = ehr_text[max(0, m_cand.start(2)-5):m_cand.start(2)]
                    if re.match(r'^\s*[/-]\s*\d', after_text) or re.search(r'\d\s*[/-]\s*$', before_text):
                        continue
                    metric_candidates.append(m_cand)

            # Strategy 3: General fallback search across all synonyms, filtering out date-shaped numbers and forbidding sentence crossing
            if not metric_candidates:
                fallback_pattern = r'(?i)\b(?:' + '|'.join(re.escape(t) for t in search_terms) + r')\b[^\d\n\.]*?(?<![a-zA-Z0-9])([<>]?=?\s*(\d{1,3}(?:\.\d+)?))(?![a-zA-Z0-9])\s*([%a-zA-Z/]*)'
                for m_cand in re.finditer(fallback_pattern, ehr_text):
                    end_pos = m_cand.end(2)
                    after_text = ehr_text[end_pos:end_pos+5]
                    before_text = ehr_text[max(0, m_cand.start(2)-5):m_cand.start(2)]
                    if re.match(r'^\s*[/-]\s*\d', after_text) or re.search(r'\d\s*[/-]\s*$', before_text):
                        continue
                    metric_candidates.append(m_cand)
                    break

            if metric_candidates:
                m = metric_candidates[0]
                raw_num_str = m.group(2)
                try:
                    val = float(raw_num_str)
                    s_idx = m.start()
                    e_idx = m.end()

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
            search_terms = list(criterion.entity_names) + ["therapy", "treatment", "management", "care", "gdmt"] if criterion.entity_names else ["therapy", "treatment", "management", "care", "gdmt"]
            terms_alt = '|'.join(re.escape(t) for t in search_terms)
            min_req = criterion.min_duration_days or 90
            
            # Pass 1: Stated therapy duration (e.g., "for 35 days", "35 days of wound therapy")
            m = re.search(r'(?i)\b(?:' + terms_alt + r')[^\n\.]*?\b(?:for\s+)?(?:[><=~]+\s*)?(\d+)\s*(days|weeks|months|years)', ehr_text)
            if not m:
                m = re.search(r'(?i)\b(\d+)\s*(days|weeks|months|years)\b[^\n\.]*?\b(?:' + terms_alt + r')\b', ehr_text)
            
            # Pass 2: Relative-date elapsed / waiting period (e.g., "13 days post-acute MI", "3 years ago", "14 months ago", "13 days elapsed")
            if not m:
                m = re.search(r'(?i)\b(\d+)\s*(days|weeks|months|years)\s*(?:post[- ]|after|since|elapsed|ago)\b[^\n\.]*?\b(?:' + terms_alt + r')\b', ehr_text)
            if not m:
                m = re.search(r'(?i)\b(?:' + terms_alt + r')[^\n\.]*?\b(\d+)\s*(days|weeks|months|years)\s*(?:post[- ]|after|since|elapsed|ago)\b', ehr_text)
            if not m:
                m = re.search(r'(?i)\b(?:currently\s+)?(\d+)\s*(days|weeks|months|years)\s*(?:post[- ]acute|post[- ]|elapsed)\b', ehr_text)
            if not m:
                m = re.search(r'(?i)\b(\d+)\s*(days|weeks|months|years)\s*elapsed\b', ehr_text)

            if m:
                count = int(m.group(1))
                unit_str = m.group(2).lower()
                days = count * 365 if "year" in unit_str else (count * 30 if "month" in unit_str else (count * 7 if "week" in unit_str else count))
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
                    if days >= min_req:
                        status = DeterminationStatus.MET
                        raw_confidence = 0.96
                        rationale = f"Documented timeline/duration ({days} days) satisfies statutory minimum requirement of {min_req} days."
                    else:
                        status = DeterminationStatus.NOT_MET
                        raw_confidence = 0.95
                        rationale = f"Statutory waiting period unmet: documented timeline ({days} days) does not satisfy requirement of {min_req} days."

        elif criterion.criterion_type == CriterionType.EXCLUSION_SYMPTOM:
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
                    status = DeterminationStatus.NOT_MET
                    raw_confidence = 0.95
                    rationale = f"Statutory exclusion condition ruled out: documented as absent or resolved ({scope['negation_trigger']})."
                else:
                    status = DeterminationStatus.MET
                    raw_confidence = 0.95
                    rationale = "Active statutory exclusion identified: patient manifests disqualifying condition."
            else:
                status = DeterminationStatus.NOT_MET
                raw_confidence = 0.90
                rationale = "No documented statutory exclusion conditions identified in EHR narrative."

        else:
            # CriterionType.FINDING_PRESENCE
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

    @classmethod
    def evaluate_policy(cls, policy: DeclarativePolicy, ehr_text: str) -> List[CriterionAssessment]:
        """Evaluates all criteria declared in a DeclarativePolicy."""
        return [cls.evaluate(crit, ehr_text) for crit in policy.criteria]
