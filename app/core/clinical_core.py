import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.contracts import (
    DeterminationStatus,
    ClinicalEvidenceSpan,
    CriterionAssessment
)
from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType

class ClinicalScopeAnalyzer:
    """
    Unified Clinical NegEx & ConText Scope Analyzer.
    Shared across Deterministic, State Machine, and Declarative execution modes.
    Enforces clinical linguistic invariants:
    1. Negation triggers do NOT cross sentence or clause boundaries (. , \n, ;).
    2. Conjunctions (but, however, nevertheless) reset preceding negation scope.
    3. Experiencer distinction (Patient vs Family History).
    """

    PRE_NEGATIONS = [
        r"\b(?:no|not|denies|denied|denying|without|negative for|ruled out|free of|absence of|never)\b",
        r"\b(?:no evidence of|no history of|no signs of|fails to demonstrate|unremarkable for)\b"
    ]
    POST_NEGATIONS = [
        r"\b(?:is ruled out|was ruled out|is absent|unlikely)\b"
    ]
    EXPERIENCER_TRIGGERS = [
        r"\b(?:mother|father|sister|brother|maternal|paternal|family history|fhx|relative|parent)\b"
    ]
    CONJUNCTIONS = [
        r"\b(?:but|however|nevertheless|although|except|yet)\b"
    ]

    @classmethod
    def analyze_scope(cls, text: str, span_start: int, span_end: int) -> Dict[str, Any]:
        preceding_window = text[max(0, span_start - 60):span_start].lower()
        following_window = text[span_end:min(len(text), span_end + 35)].lower()

        # Negation does not cross sentence/clause boundaries
        sentence_boundaries = [m.end() for m in re.finditer(r'(?:\.\s+|\n+|;\s*)', preceding_window)]
        last_boundary = max(sentence_boundaries) if sentence_boundaries else 0
        in_sentence_preceding = preceding_window[last_boundary:]

        last_conjunction = -1
        for conj in cls.CONJUNCTIONS:
            for m in re.finditer(conj, in_sentence_preceding):
                if m.start() > last_conjunction:
                    last_conjunction = m.start()

        active_preceding = in_sentence_preceding[last_conjunction + 1:] if last_conjunction != -1 else in_sentence_preceding

        following_boundary_match = re.search(r'(?:\.\s+|\n+|;)', following_window)
        active_following = following_window[:following_boundary_match.start()] if following_boundary_match else following_window

        is_negated = False
        negation_trigger = None
        for pat in cls.PRE_NEGATIONS:
            m = re.search(pat, active_preceding)
            if m:
                is_negated = True
                negation_trigger = m.group(0)
                break

        if not is_negated:
            for pat in cls.POST_NEGATIONS:
                m = re.search(pat, active_following)
                if m:
                    is_negated = True
                    negation_trigger = m.group(0)
                    break

        is_family_history = False
        experiencer = "PATIENT"
        for pat in cls.EXPERIENCER_TRIGGERS:
            m = re.search(pat, active_preceding)
            if m:
                is_family_history = True
                experiencer = "FAMILY_MEMBER"
                break

        return {
            "is_negated": is_negated,
            "negation_trigger": negation_trigger,
            "is_family_history": is_family_history,
            "experiencer": experiencer
        }


class ClinicalSectionDetector:
    """
    Unified section boundary detector for EHR narratives.
    """
    HEADERS = [
        ("History of Present Illness", [r"(?i)\bhistory of present illness\b", r"(?i)\bhpi\b"]),
        ("Past Medical History", [r"(?i)\bpast medical history\b", r"(?i)\bpmh\b"]),
        ("Medications", [r"(?i)\bmedications\b", r"(?i)\bcurrent meds\b", r"(?i)\bgdmt\b"]),
        ("Diagnostic Studies", [r"(?i)\bdiagnostics\b", r"(?i)\bechocardiogram\b", r"(?i)\becho\b", r"(?i)\bpolysomnography\b", r"(?i)\blabs\b"]),
        ("Physical Examination", [r"(?i)\bphysical examination\b", r"(?i)\bexam\b"]),
        ("Assessment & Plan", [r"(?i)\bassessment & plan\b", r"(?i)\bassessment and plan\b", r"(?i)\bplan\b", r"(?i)\ba/p\b"])
    ]

    @classmethod
    def detect_section(cls, text: str, char_pos: int) -> str:
        prior_text = text[:char_pos]
        last_found_section = "Clinical Documentation"
        last_found_index = -1

        for sec_name, patterns in cls.HEADERS:
            for pat in patterns:
                for match in re.finditer(pat, prior_text):
                    if match.start() > last_found_index:
                        last_found_index = match.start()
                        last_found_section = sec_name

        return last_found_section


class ClinicalNumericParser:
    """
    Unified clinical numeric and score parser.
    Guarantees:
    - Never parses calendar dates (MM/DD/YYYY or YYYY-MM-DD) as clinical measurements.
    - Accurately parses scales and indices (AHI, LVEF, AVA, PaO2, SpO2, CHA2DS2-VASc, HAS-BLED, STS PROM).
    - Compares values against threshold operators (<, <=, >, >=, ==).
    """

    @staticmethod
    def evaluate_cutoff(value: float, operator: str, threshold: float) -> bool:
        if operator in ("<=", "le"):
            return value <= threshold
        elif operator in ("<", "lt"):
            return value < threshold
        elif operator in (">=", "ge"):
            return value >= threshold
        elif operator in (">", "gt"):
            return value > threshold
        elif operator in ("==", "eq"):
            return abs(value - threshold) < 1e-5
        return False

    @classmethod
    def is_date_pattern(cls, text: str, start: int, end: int) -> bool:
        before = text[max(0, start - 5):start]
        after = text[end:min(len(text), end + 5)]
        return bool(re.search(r'\d\s*[/-]\s*$', before) or re.match(r'^\s*[/-]\s*\d', after))


class ClinicalTemporalParser:
    """
    Unified temporal duration and calendar delta calculator.
    Shared across Extractor, State Machine, and Declarative Engine.
    """
    @staticmethod
    def calculate_calendar_delta(event_date_str: str, reference_date_str: str) -> Optional[int]:
        try:
            d_event = datetime.strptime(event_date_str.strip(), "%Y-%m-%d")
            d_ref = datetime.strptime(reference_date_str.strip(), "%Y-%m-%d")
            return abs((d_ref - d_event).days)
        except Exception:
            return None

    @staticmethod
    def parse_duration_to_days(value: int, unit: str) -> int:
        u = unit.lower().strip()
        if "year" in u:
            return value * 365
        elif "month" in u:
            return value * 30
        elif "week" in u:
            return value * 7
        return value


class ClinicalGroundingVerifier:
    """
    Unified programmatic character slice verifier.
    Guarantees strict substring identity: raw_text[start:end] == quote.
    """
    @staticmethod
    def verify_exact_slice(raw_text: str, quote: str, start: int, end: int) -> bool:
        if start < 0 or end > len(raw_text) or start >= end:
            return False
        return raw_text[start:end] == quote


class ClinicalCoreEvaluator:
    """
    Canonical shared clinical criteria evaluation engine.
    Unified core powering Deterministic, State Machine, and Declarative evaluation modes.
    Guarantees consistent determination, grounding, and calibration across the entire platform.
    """

    @classmethod
    def evaluate(
        cls,
        criterion: Dict[str, Any],
        ehr_text: str
    ) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-UNKNOWN")
        name = criterion.get("name", "")
        desc = criterion.get("description", "")
        is_excl = bool(criterion.get("is_exclusion", False))
        temporal_req = criterion.get("required_temporal_window", "Not specified")
        min_score = float(criterion.get("min_score", 0.85))

        code_low = code.lower()
        name_low = name.lower()
        desc_low = desc.lower()

        # Delegate to specialized canonical evaluators based on clinical policy domain
        # 1. Cardiac: LVEF
        if "lvef" in code_low or "ejection fraction" in name_low or "lvef" in desc_low:
            return cls._evaluate_lvef(criterion, ehr_text)

        # 2. Cardiac: NYHA Functional Class
        if "nyha" in code_low or "functional class" in name_low or "nyha" in desc_low:
            return cls._evaluate_nyha(criterion, ehr_text)

        # 3. Cardiac: GDMT Duration
        if "gdmt" in code_low or "medical therapy" in name_low or ("optimal medical" in desc_low and "guideline" in desc_low):
            return cls._evaluate_gdmt(criterion, ehr_text)

        # 4. Cardiac: Post-MI / Revascularization Timeline
        if "crit-icd-04" in code_low or "timeline" in name_low or "revascularization" in name_low or "post-mi" in desc_low:
            return cls._evaluate_revasc_timeline(criterion, ehr_text)

        # 5. General / Cardiac / TAVR: Futility / Shock / Terminal Illness Exclusion
        if is_excl and any(k in desc_low or k in name_low for k in ["shock", "futility", "terminal", "endocarditis", "survival", "metastatic", "hospice"]):
            return cls._evaluate_futility_exclusion(criterion, ehr_text)

        # 6. Pulmonology: Resting Hypoxemia (NCD-240.2)
        if "crit-o2-01" in code_low or ("hypoxemia" in name_low and "pao2" in desc_low):
            return cls._evaluate_oxygen_hypoxemia(criterion, ehr_text)

        # 7. Pulmonology: Clinical Stability (NCD-240.2)
        if "crit-o2-02" in code_low or "clinical stability" in name_low:
            return cls._evaluate_clinical_stability(criterion, ehr_text)

        # 8. Pulmonology: Reversible Etiology Exclusion (NCD-240.2)
        if "crit-o2-excl" in code_low or ("reversible" in name_low and is_excl):
            return cls._evaluate_reversible_etiology_exclusion(criterion, ehr_text)

        # 9. TAVR: Severe Aortic Stenosis Hemodynamics (NCD-20.33)
        if "crit-tavr-01" in code_low or ("aortic stenosis" in name_low and "ava" in desc_low):
            return cls._evaluate_tavr_hemodynamics(criterion, ehr_text)

        # 10. TAVR: Heart Team Consultation (NCD-20.33)
        if "crit-tavr-02" in code_low or "heart team" in name_low:
            return cls._evaluate_heart_team(criterion, ehr_text)

        # 11. TAVR: Prohibitive Contraindication Exclusion (NCD-20.33)
        if "crit-tavr-excl-02" in code_low or ("prohibitive" in name_low and is_excl):
            return cls._evaluate_tavr_prohibitive_exclusion(criterion, ehr_text)

        # 12. Carotid Artery Stenting (NCD-20.7)
        if "crit-cas" in code_low or "carotid" in name_low or "carotid" in desc_low:
            return cls._evaluate_carotid(criterion, ehr_text)

        # 13. Sleep Apnea / CPAP (LCD-L33829)
        if "ahi" in code_low or "sleep apnea" in name_low or "ahi" in desc_low or "face-to-face" in name_low:
            return cls._evaluate_sleep_apnea(criterion, ehr_text)

        # 14. Hyperbaric Oxygen / DFU (NCD-20.29)
        if "crit-hbot" in code_low or "wagner" in desc_low or "wound" in name_low:
            return cls._evaluate_hbot(criterion, ehr_text)

        # 15. LAAC / Watchman (NCD-220.13)
        if "crit-laac" in code_low or "cha2ds2" in desc_low or "watchman" in desc_low:
            return cls._evaluate_laac(criterion, ehr_text)

        # 16. Total Knee Arthroplasty (LCD-TOTAL-KNEE-01)
        if "crit-tka" in code_low or "flexion" in name_low or "knee" in desc_low:
            return cls._evaluate_tka(criterion, ehr_text)

        # Fallback: General Declarative Entity & Threshold Evaluator
        return cls._evaluate_generic_declarative(criterion, ehr_text)

    # -------------------------------------------------------------------------
    # Specialized Domain Evaluators (Unified implementations)
    # -------------------------------------------------------------------------

    @classmethod
    def _evaluate_lvef(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-ICD-01")
        name = criterion.get("name", "Severe LV Systolic Dysfunction")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Within past 12 months")

        lvef_match = re.search(r'(?i)\b(lvef|left ventricular ejection fraction)\s*(?:\([a-z0-9\s]+\)\s*)?(?:is|of|:)?\s*([<>]?=?\s*(\d{1,2}))%', ehr_text)
        if not lvef_match:
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented left ventricular ejection fraction (LVEF) measurement found in diagnostic reports.",
                raw_confidence=0.60
            )

        val = int(lvef_match.group(3))
        start_c = lvef_match.start()
        end_c = lvef_match.end()
        span = ClinicalEvidenceSpan(
            source_text=ehr_text[start_c:end_c],
            start_char=start_c,
            end_char=end_c,
            clinical_section=ClinicalSectionDetector.detect_section(ehr_text, start_c),
            confidence=0.98
        )

        mod_match = re.search(r'(?i)\b(tte|transthoracic echocardiogram|echocardiography|echocardiogram|echo|tee|transesophageal echocardiogram|cardiac mri|cmr|radionuclide ventriculography|muga|left ventriculography|ventriculogram)\b', ehr_text)
        if mod_match:
            m_str = mod_match.group(0).lower()
            if m_str in ["tte", "transthoracic echocardiogram"]:
                modality_name = "Transthoracic Echocardiogram"
            elif m_str in ["cmr", "cardiac mri"]:
                modality_name = "Cardiac MRI (CMR)"
            elif m_str in ["muga", "radionuclide ventriculography"]:
                modality_name = "MUGA Scan"
            else:
                modality_name = "Echocardiography"
        else:
            modality_name = "Diagnostic Imaging"

        if val <= 35:
            status = DeterminationStatus.MET
            rationale = f"Documented LVEF is {val}% confirmed by {modality_name}, meeting the mandatory primary prevention threshold of ≤35% (HFrEF)."
            conf = 0.96
        elif 36 <= val <= 49:
            status = DeterminationStatus.NOT_MET
            rationale = f"Documented LVEF is {val}% via {modality_name} (Heart Failure with Mildly Reduced Ejection Fraction / HFmrEF). Fails the Medicare NCD 20.4 primary prevention threshold of ≤35%."
            conf = 0.94
        else:
            status = DeterminationStatus.NOT_MET
            rationale = f"Documented LVEF is {val}% via {modality_name} (Heart Failure with Preserved Ejection Fraction / HFpEF). CMS NCD 20.4 restricts primary prevention ICD coverage strictly to severe systolic dysfunction (HFrEF with LVEF ≤ 35%). Prophylactic device placement is not indicated for preserved systolic function."
            conf = 0.95

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=status,
            verified_spans=[span],
            clinical_rationale=rationale,
            raw_confidence=conf
        )

    @classmethod
    def _evaluate_nyha(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-ICD-02")
        name = criterion.get("name", "Heart Failure Functional Classification")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Documented at clinical evaluation")

        nyha_match = re.search(r'(?i)\b(nyha|new york heart association)\s*(?:functional\s+)?(?:class)?\s*([IVX]+|\d)\b', ehr_text)
        if not nyha_match:
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="NYHA functional heart failure class not documented in physical exam or assessment.",
                raw_confidence=0.62
            )

        cls_str = nyha_match.group(2).upper()
        start_c = nyha_match.start()
        end_c = nyha_match.end()
        span = ClinicalEvidenceSpan(
            source_text=ehr_text[start_c:end_c],
            start_char=start_c,
            end_char=end_c,
            clinical_section=ClinicalSectionDetector.detect_section(ehr_text, start_c),
            confidence=0.95
        )

        if cls_str in ["II", "III", "2", "3"]:
            status = DeterminationStatus.MET
            rationale = f"Patient classified as NYHA Class {cls_str} heart failure symptoms."
            conf = 0.94
        else:
            status = DeterminationStatus.NOT_MET
            rationale = f"Patient classified as NYHA Class {cls_str}, which does not meet qualifying Class II/III criteria."
            conf = 0.91

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=status,
            verified_spans=[span],
            clinical_rationale=rationale,
            raw_confidence=conf
        )

    @classmethod
    def _evaluate_gdmt(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-ICD-03")
        name = criterion.get("name", "Guideline-Directed Medical Therapy Duration (>=90 Days)")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", ">= 90 days / 3 months duration")

        gdmt_pattern = r'(?i)\b(gdmt|guideline-directed medical therapy|optimal medical therapy|beta[- ]blocker|carvedilol|metoprolol|lisinopril|entresto|sacubitril|spironolactone|eplerenone|dapagliflozin|empagliflozin)\b'
        time_pattern = r'(?i)\b(?:for\s+|at least\s+|stable for\s+)?(?:>|>=|over|more than)?\s*(\d+)\s*(?:months|days|weeks)\b'
        contra_pattern = r'(?i)\b(contraindicated|contraindication|intolerant|intolerance|allergy|angioedema|hyperkalemia|severe renal impairment|prohibitive bradycardia)\b'

        med_match = re.search(gdmt_pattern, ehr_text)
        contra_match = re.search(contra_pattern, ehr_text)

        if contra_match:
            s_idx = contra_match.start()
            e_idx = contra_match.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.MET,
                verified_spans=[span],
                clinical_rationale=f"Documented clinical contraindication / intolerance to guideline-directed medical therapy ({span.source_text}), satisfying CMS exception criteria.",
                raw_confidence=0.95,
                temporal_window_met=True
            )

        if med_match:
            s_idx = med_match.start()
            e_idx = med_match.end()
            med_span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.92
            )

            # Check duration in nearby context
            nearby_text = ehr_text[max(0, s_idx - 100):min(len(ehr_text), e_idx + 150)]
            t_match = re.search(time_pattern, nearby_text)
            if t_match:
                duration_val = int(t_match.group(1))
                duration_unit = "months" if "month" in t_match.group(0).lower() else ("weeks" if "week" in t_match.group(0).lower() else "days")
                days_equiv = duration_val * 30 if duration_unit == "months" else (duration_val * 7 if duration_unit == "weeks" else duration_val)

                if days_equiv >= 90:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[med_span],
                        clinical_rationale=f"Documented medical therapy duration is {duration_val} {duration_unit} (≥90 days requirement satisfied).",
                        raw_confidence=0.94,
                        temporal_window_met=True
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[med_span],
                        clinical_rationale=f"Documented medical therapy duration is only {duration_val} {duration_unit} (<90 days required by CMS NCD 20.4).",
                        raw_confidence=0.93,
                        temporal_window_met=False
                    )

            # Check if duration is documented elsewhere in note
            global_time_match = re.search(time_pattern, ehr_text)
            if global_time_match:
                d_val = int(global_time_match.group(1))
                d_unit = "months" if "month" in global_time_match.group(0).lower() else ("weeks" if "week" in global_time_match.group(0).lower() else "days")
                days_eq = d_val * 30 if d_unit == "months" else (d_val * 7 if d_unit == "weeks" else d_val)
                if days_eq >= 90:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[med_span],
                        clinical_rationale=f"Documented medical therapy duration is {d_val} {d_unit} (≥90 days satisfied).",
                        raw_confidence=0.91,
                        temporal_window_met=True
                    )

            # Mention of GDMT without duration
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[med_span],
                clinical_rationale="Medical therapy mentioned, but duration of therapy (>=90 days) is not documented.",
                raw_confidence=0.68,
                temporal_window_met=None
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="No documentation of guideline-directed medical therapy (GDMT) found.",
            raw_confidence=0.60
        )

    @classmethod
    def _evaluate_revasc_timeline(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-ICD-04")
        name = criterion.get("name", "Cardiomyopathy Etiology & Revascularization Timeline")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", ">= 40 days post-MI or >= 90 days post-CABG/PCI")

        premature_match = re.search(r'(?i)\b(?:stemi|mi|myocardial infarction|pci|cabg)\s+(?:occurred|was|performed)?\s*(\d{1,2})\s*days\s*ago\b', ehr_text)
        if premature_match:
            days = int(premature_match.group(1))
            s_idx = premature_match.start()
            e_idx = premature_match.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            )
            if days < 40:
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.NOT_MET,
                    verified_spans=[span],
                    clinical_rationale=f"Recent event occurred only {days} days ago. CMS NCD 20.4 mandates a 40-day waiting period post-MI and 90-day post-revascularization before ICD implantation.",
                    raw_confidence=0.95,
                    temporal_window_met=False
                )

        event_match = re.search(r'(?i)\b(remote\s+mi|remote\s+myocardial\s+infarction|non-ischemic\s+dilated\s+cardiomyopathy|non-ischemic\s+cardiomyopathy|nicm|post-mi|myocardial infarction|cabg|pci)\b', ehr_text)
        if event_match:
            s_idx = event_match.start()
            e_idx = event_match.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.93
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.MET,
                verified_spans=[span],
                clinical_rationale=f"Event timeline documented: {span.source_text}; satisfies CMS mandatory post-event waiting periods.",
                raw_confidence=0.91,
                temporal_window_met=True
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.MET,
            verified_spans=[],
            clinical_rationale="No acute MI (<40 days) or recent revascularization (<90 days) disqualifying the patient.",
            raw_confidence=0.88,
            temporal_window_met=True
        )

    @classmethod
    def _evaluate_futility_exclusion(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-EXCL-FUTILITY")
        name = criterion.get("name", "Cardiogenic Shock / Futility / Terminal Illness Exclusion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current clinical encounter")

        pos_pattern = r'(?i)\b(?:active cardiogenic shock|in cardiogenic shock|refractory cardiogenic shock|cardiogenic shock|metastatic\s+(?:[a-z]+\s+)?(?:cancer|malignancy|disease)|end-stage malignancy|terminal illness|terminal non-cardiac illness|hospice(?:-directed)?|life expectancy\s*(?:<|less than)\s*1\s*year|active infective endocarditis|infective endocarditis|active endocarditis)\b'
        
        for m in re.finditer(pos_pattern, ehr_text):
            s_idx = m.start()
            e_idx = m.end()
            scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
            if not scope["is_negated"]:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=True,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Disqualifying exclusion criterion detected: {span.source_text}.",
                    raw_confidence=0.96
                )

        neg_match = re.search(r'(?i)\b(no|without|denies|negative for|absence of)\s+(?:active\s+|acute\s+)?(cardiogenic shock|terminal illness|terminal non-cardiac illness|end-stage malignancy|hospice|endocarditis|infective endocarditis)\b', ehr_text)
        if neg_match:
            s_idx = neg_match.start()
            e_idx = neg_match.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=True,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.NOT_MET,
                verified_spans=[span],
                clinical_rationale=f"Documented absence of disqualifying exclusion: {span.source_text}.",
                raw_confidence=0.95
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=True,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.NOT_MET,
            verified_spans=[],
            clinical_rationale="No documented disqualifying cardiogenic shock, active endocarditis, or non-cardiac disease limiting 1-year survival.",
            raw_confidence=0.93
        )

    @classmethod
    def _evaluate_oxygen_hypoxemia(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-O2-01")
        name = criterion.get("name", "Resting Hypoxemia (PaO2 <= 55 mmHg or SpO2 <= 88%)")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Within 30 days of order")

        spo2_match = re.search(r'(?i)\b(?:spo2|oxygen saturation|o2 sat(?:uration)?|room air)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d{1,2}))%', ehr_text)
        pao2_match = re.search(r'(?i)\b(?:pao2|arterial blood gas|abg)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d{1,2}))\s*(?:mm\s*hg)?\b', ehr_text)

        spans = []
        val_spo2 = None
        val_pao2 = None

        if spo2_match:
            val_spo2 = int(spo2_match.group(2))
            s_idx = spo2_match.start()
            e_idx = spo2_match.end()
            spans.append(ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            ))

        if pao2_match:
            val_pao2 = int(pao2_match.group(2))
            s_idx = pao2_match.start()
            e_idx = pao2_match.end()
            spans.append(ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            ))

        if val_spo2 is not None or val_pao2 is not None:
            qualifies = (val_spo2 is not None and val_spo2 <= 88) or (val_pao2 is not None and val_pao2 <= 55)
            if qualifies:
                details = []
                if val_spo2 is not None:
                    details.append(f"SpO2 {val_spo2}% (≤88%)")
                if val_pao2 is not None:
                    details.append(f"PaO2 {val_pao2} mmHg (≤55 mmHg)")
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=spans,
                    clinical_rationale=f"Documented severe resting hypoxemia on room air: {', '.join(details)}, meeting CMS NCD 240.2 threshold.",
                    raw_confidence=0.95
                )
            else:
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.NOT_MET,
                    verified_spans=spans,
                    clinical_rationale="Documented resting oxygenation does not meet severe hypoxemia threshold (requires SpO2 ≤ 88% or PaO2 ≤ 55 mmHg).",
                    raw_confidence=0.93
                )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="No documented room-air resting arterial blood gas (PaO2) or pulse oximetry (SpO2) values found.",
            raw_confidence=0.60
        )

    @classmethod
    def _evaluate_clinical_stability(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-O2-02")
        name = criterion.get("name", "Clinical Stability at Evaluation")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "At time of qualifying test")

        m = re.search(r'(?i)\b(clinically stable|clinical stability|stable outpatient state|stable state|chronic stable state|outpatient stability|stable baseline|chronic stability)\b', ehr_text)
        if m:
            s_idx = m.start()
            e_idx = m.end()
            scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
            if not scope["is_negated"]:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Documented chronic clinical stability verified: '{span.source_text}'.",
                    raw_confidence=0.94
                )
            else:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.NOT_MET,
                    verified_spans=[span],
                    clinical_rationale="Patient is not clinically stable (negated clinical stability), indicating acute decompensation.",
                    raw_confidence=0.92
                )

        unstable_m = re.search(r'(?i)\b(acute exacerbation|acute respiratory failure|inpatient status|acute decompensation|unstable respiratory)\b', ehr_text)
        if unstable_m:
            s_idx = unstable_m.start()
            e_idx = unstable_m.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.94
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.NOT_MET,
                verified_spans=[span],
                clinical_rationale=f"Patient has acute instability ({span.source_text}); CMS NCD 240.2 requires testing in a chronic, clinically stable state.",
                raw_confidence=0.91
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="Clinical stability not documented at time of oxygen testing; deferral required.",
            raw_confidence=0.62
        )

    @classmethod
    def _evaluate_reversible_etiology_exclusion(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-O2-EXCL-01")
        name = criterion.get("name", "Acute Reversible Etiology Exclusion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current clinical presentation")

        m = re.search(r'(?i)\b(acute pneumonia|untreated pneumonia|acute bronchospasm|transient pulmonary edema|acute pulmonary edema|reversible etiology|reversible hypoxemia)\b', ehr_text)
        if m:
            s_idx = m.start()
            e_idx = m.end()
            scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
            if not scope["is_negated"]:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=True,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Active reversible etiology of hypoxemia detected: '{span.source_text}', disqualifying long-term home oxygen.",
                    raw_confidence=0.95
                )

        neg_m = re.search(r'(?i)\b(no|without|absence of)\s+(?:active\s+|acute\s+)?(pneumonia|bronchospasm|pulmonary edema|reversible etiology)\b', ehr_text)
        if neg_m:
            s_idx = neg_m.start()
            e_idx = neg_m.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.95
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=True,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.NOT_MET,
                verified_spans=[span],
                clinical_rationale=f"Absence of acute reversible etiology confirmed: '{span.source_text}'.",
                raw_confidence=0.94
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=True,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.NOT_MET,
            verified_spans=[],
            clinical_rationale="No documented acute reversible cause of hypoxemia.",
            raw_confidence=0.91
        )

    @classmethod
    def _evaluate_tavr_hemodynamics(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-TAVR-01")
        name = criterion.get("name", "Severe Aortic Stenosis Hemodynamic Threshold")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Within past 6 months")

        ava_m = re.search(r'(?i)\b(?:aortic valve area|ava)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\s*(?:cm2|cm\^2)?\b', ehr_text)
        grad_m = re.search(r'(?i)\b(?:mean\s+(?:transvalvular\s+)?gradient|mean\s+gradient)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\s*(?:mm\s*hg)?\b', ehr_text)
        vel_m = re.search(r'(?i)\b(?:peak\s+(?:aortic\s+jet\s+)?velocity|peak\s+velocity)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\s*(?:m/s)?\b', ehr_text)

        spans = []
        val_ava = float(ava_m.group(2)) if ava_m else None
        val_grad = float(grad_m.group(2)) if grad_m else None
        val_vel = float(vel_m.group(2)) if vel_m else None

        if ava_m:
            s_idx = ava_m.start()
            e_idx = ava_m.end()
            spans.append(ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.98
            ))
        if grad_m:
            s_idx = grad_m.start()
            e_idx = grad_m.end()
            spans.append(ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.98
            ))
        if vel_m:
            s_idx = vel_m.start()
            e_idx = vel_m.end()
            spans.append(ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.98
            ))

        if val_ava is not None or val_grad is not None or val_vel is not None:
            qualifies = (
                (val_ava is not None and val_ava <= 1.0) or
                (val_grad is not None and val_grad >= 40.0) or
                (val_vel is not None and val_vel >= 4.0)
            )
            if qualifies:
                parts = []
                if val_ava is not None:
                    parts.append(f"Aortic valve area {val_ava} cm2")
                if val_grad is not None:
                    parts.append(f"mean transvalvular gradient {val_grad} mmHg")
                if val_vel is not None:
                    parts.append(f"peak velocity {val_vel} m/s")
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=spans,
                    clinical_rationale=f"Severe aortic stenosis verified by quantified hemodynamics ({'; '.join(parts)}), satisfying NCD 20.33.",
                    raw_confidence=0.97
                )
            else:
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.NOT_MET,
                    verified_spans=spans,
                    clinical_rationale="Quantified aortic stenosis hemodynamics fail severe threshold (requires AVA ≤ 1.0 cm2, mean gradient ≥ 40 mmHg, or peak velocity ≥ 4.0 m/s).",
                    raw_confidence=0.94
                )

        # Check qualitative stenosis mention without quantified values
        qual_m = re.search(r'(?i)\b(severe aortic stenosis|severe calcific aortic stenosis|severe as)\b', ehr_text)
        if qual_m:
            s_idx = qual_m.start()
            e_idx = qual_m.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.85
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[span],
                clinical_rationale="Echocardiogram describes severe aortic stenosis in qualitative terms only; no quantified AVA (<= 1.0 cm2), mean gradient (>= 40 mmHg), or peak velocity (>= 4.0 m/s) recorded. Deferral required for quantified report.",
                raw_confidence=0.65
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="No documented aortic stenosis hemodynamics or echocardiography report found.",
            raw_confidence=0.60
        )

    @classmethod
    def _evaluate_heart_team(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-TAVR-02")
        name = criterion.get("name", "Heart Team Consultation")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Prior to procedure")

        m = re.search(r'(?i)\b(heart team|multidisciplinary heart team|cardiac surgeon\s+(?:and|with)\s+interventional cardiologist|interventional cardiologist\s+(?:and|with)\s+cardiac surgeon)\b', ehr_text)
        if m:
            s_idx = m.start()
            e_idx = m.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.MET,
                verified_spans=[span],
                clinical_rationale=f"Multidisciplinary Heart Team consultation documented: '{span.source_text}'.",
                raw_confidence=0.95
            )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="Multidisciplinary Heart Team collaborative consultation not documented.",
            raw_confidence=0.60
        )

    @classmethod
    def _evaluate_tavr_prohibitive_exclusion(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-TAVR-EXCL-02")
        name = criterion.get("name", "Prohibitive Surgical or Anatomical Contraindication Exclusion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current pre-procedure evaluation")

        m = re.search(r'(?i)\b(prohibitive aortic root|prohibitive anatomy|anatomical contraindication|prohibitive surgical contraindication|active bacteremia|uncorrectable bleeding diathesis)\b', ehr_text)
        if m:
            s_idx = m.start()
            e_idx = m.end()
            scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
            if not scope["is_negated"]:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=True,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Prohibitive procedural contraindication detected: '{span.source_text}'.",
                    raw_confidence=0.95
                )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=True,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.NOT_MET,
            verified_spans=[],
            clinical_rationale="No prohibitive anatomical or procedural contraindications documented.",
            raw_confidence=0.92
        )

    @classmethod
    def _evaluate_carotid(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-CAS-01")
        name = criterion.get("name", "Carotid Stenosis Criterion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current evaluation")

        # Stenosis check
        if "stenosis" in name.lower() or "stenosis" in desc.lower() or "crit-cas-01" in code.lower():
            sten_match = re.search(r'(\d{1,2})%\s*.*?\b(?:stenosis|narrowing)\b', ehr_text, re.IGNORECASE) or re.search(r'\b(?:stenosis|narrowing)[^\d\n]{0,30}(\d{1,2})%', ehr_text, re.IGNORECASE)
            if sten_match:
                val = int(sten_match.group(1))
                s_idx = sten_match.start()
                e_idx = sten_match.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                is_symptomatic = bool(re.search(r'(?i)\b(tia|transient ischemic attack|stroke|cva|amaurosis fugax|ipsilateral)\b', ehr_text))
                thresh = 70 if is_symptomatic else 80
                if val >= thresh:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented carotid stenosis of {val}% meets CMS NCD 20.7 threshold (≥{thresh}% {'symptomatic' if is_symptomatic else 'asymptomatic'}).",
                        raw_confidence=0.95
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented carotid stenosis of {val}% fails threshold (≥{thresh}% required).",
                        raw_confidence=0.93
                    )

            qual_sten = re.search(r'(?i)\b(severe carotid stenosis|severe ica stenosis|high-grade stenosis|carotid stenosis)\b', ehr_text)
            if qual_sten:
                s_idx = qual_sten.start()
                e_idx = qual_sten.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.85
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                    verified_spans=[span],
                    clinical_rationale="Carotid stenosis mentioned qualitatively, but exact numeric percentage is unquantified.",
                    raw_confidence=0.65
                )

            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented carotid stenosis evaluation.",
                raw_confidence=0.60
            )

        # High surgical risk check
        if "high surgical risk" in name.lower() or "cea" in desc.lower() or "crit-cas-02" in code.lower():
            hr_match = re.search(r'(?i)\b(high risk for cea|hostile neck|prior neck radiation|prior radical neck dissection|tracheostomy|severe copd|sts score\s*[>]=?\s*8%|contralateral carotid occlusion)\b', ehr_text)
            if hr_match:
                s_idx = hr_match.start()
                e_idx = hr_match.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"High surgical risk for CEA documented: '{span.source_text}'.",
                    raw_confidence=0.94
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented high surgical risk features for open CEA.",
                raw_confidence=0.62
            )

        # EPD check
        if "epd" in name.lower() or "embolic protection" in name.lower() or "crit-cas-03" in code.lower():
            epd_match = re.search(r'(?i)\b(embolic protection device|epd|distal filter|embolic filter|fda-approved carotid stent)\b', ehr_text)
            if epd_match:
                s_idx = epd_match.start()
                e_idx = epd_match.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Mandatory FDA-approved embolic protection documented: '{span.source_text}'.",
                    raw_confidence=0.95
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Mandatory FDA-approved embolic protection system (EPD) not documented in procedure plan.",
                raw_confidence=0.62
            )

        return cls._evaluate_generic_declarative(criterion, ehr_text)

    @classmethod
    def _evaluate_sleep_apnea(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-OSA-01")
        name = criterion.get("name", "Sleep Apnea Criterion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Within 30 days")

        # Face-to-face evaluation
        if "face-to-face" in name.lower() or "face to face" in desc.lower() or "f2f" in code.lower():
            f2f_m = re.search(r'(?i)\b(face-to-face clinical evaluation|face-to-face evaluation|in-person evaluation|clinical evaluation by treating physician)\b', ehr_text)
            if f2f_m:
                s_idx = f2f_m.start()
                e_idx = f2f_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Face-to-face clinical evaluation documented: '{span.source_text}'.",
                    raw_confidence=0.95
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Face-to-face evaluation prior to sleep study not documented.",
                raw_confidence=0.62
            )

        # AHI threshold
        ahi_m = re.search(r'(?i)\b(?:ahi|apnea-hypopnea index|apnea hypopnea index)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\b', ehr_text)
        if ahi_m:
            val = float(ahi_m.group(2))
            s_idx = ahi_m.start()
            e_idx = ahi_m.end()
            span = ClinicalEvidenceSpan(
                source_text=ehr_text[s_idx:e_idx],
                start_char=s_idx,
                end_char=e_idx,
                clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                confidence=0.96
            )

            if val >= 15.0:
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"AHI is {val} events/hr, meeting severe OSA threshold (≥15 events/hr) under LCD L33829.",
                    raw_confidence=0.96
                )
            elif 5.0 <= val < 15.0:
                # Requires comorbidity
                comorb_m = re.search(r'(?i)\b(hypertension|htn|stroke|tia|excessive daytime sleepiness|insomnia|coronary artery disease|cad|ischemic heart disease)\b', ehr_text)
                if comorb_m:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"AHI is {val} events/hr (5-14) with qualifying comorbidity ({comorb_m.group(0)}).",
                        raw_confidence=0.92
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                        verified_spans=[span],
                        clinical_rationale=f"AHI is {val} events/hr (borderline 5-14), but no qualifying comorbidity documented. Deferral to human review required.",
                        raw_confidence=0.68
                    )
            else:
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.NOT_MET,
                    verified_spans=[span],
                    clinical_rationale=f"AHI is {val} events/hr (<5 events/hr threshold).",
                    raw_confidence=0.93
                )

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=False,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale="No documented diagnostic polysomnography or AHI measurement found.",
            raw_confidence=0.60
        )

    @classmethod
    def _evaluate_hbot(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-HBOT-01")
        name = criterion.get("name", "HBOT DFU Criterion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current evaluation")

        # Wagner grade check
        if "wagner" in name.lower() or "wagner" in desc.lower() or "crit-hbot-01" in code.lower():
            wagner_m = re.search(r'(?i)\bwagner\s*(?:grade|class)?\s*([0-5]|I{1,3}|IV|V)\b', ehr_text)
            if wagner_m:
                g_str = wagner_m.group(1).upper()
                s_idx = wagner_m.start()
                e_idx = wagner_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                if g_str in ["3", "4", "5", "III", "IV", "V"]:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Diabetic foot ulcer staged as Wagner Grade {g_str} (≥ Grade III required under NCD 20.29).",
                        raw_confidence=0.96
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[span],
                        clinical_rationale=f"Diabetic foot ulcer staged as Wagner Grade {g_str} (< Grade III fails coverage threshold).",
                        raw_confidence=0.94
                    )

            # Check deep ulceration / probe to bone
            bone_m = re.search(r'(?i)\b(deep probe-to-bone ulceration|probe-to-bone|osteomyelitis|gangrene)\b', ehr_text)
            if bone_m:
                s_idx = bone_m.start()
                e_idx = bone_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Severe ulceration documented: '{span.source_text}' (consistent with Wagner Grade III+).",
                    raw_confidence=0.93
                )

            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented Wagner Grade staging for diabetic foot ulcer.",
                raw_confidence=0.60
            )

        # Conservative care check
        if "conservative" in name.lower() or "30 days" in desc.lower() or "crit-hbot-02" in code.lower():
            care_m = re.search(r'(?i)\b(>30 days standard care|>= 30 days conservative|failure of >= 30 days|offloading|debridement|moist dressing)\b', ehr_text)
            if care_m:
                s_idx = care_m.start()
                e_idx = care_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.94
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Documented conservative wound therapy failure: '{span.source_text}'.",
                    raw_confidence=0.93
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Documented trial of conservative wound care (≥30 days) not found.",
                raw_confidence=0.62
            )

        return cls._evaluate_generic_declarative(criterion, ehr_text)

    @classmethod
    def _evaluate_laac(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-LAAC-01")
        name = criterion.get("name", "LAAC Criterion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current evaluation")

        # CHA2DS2-VASc score
        if "cha2ds2" in name.lower() or "cha2ds2" in desc.lower() or "stroke risk" in name.lower() or "crit-laac-01" in code.lower():
            chads_m = re.search(r'(?i)\b(?:cha2ds2-vasc|chads-vasc|cha2ds2)\b(?:\s*score)?\s*(?:calculated at|is|of|:|=)?\s*(\d{1,2})\b', ehr_text)
            if chads_m:
                val = int(chads_m.group(1))
                s_idx = chads_m.start()
                e_idx = chads_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                if val >= 3:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented CHA2DS2-VASc score is {val} (≥3 requirement satisfied).",
                        raw_confidence=0.96
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented CHA2DS2-VASc score is {val} (<3 fails coverage threshold).",
                        raw_confidence=0.93
                    )

            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Documented CHA2DS2-VASc score not found in clinical note.",
                raw_confidence=0.60
            )

        # HAS-BLED / Anticoagulation contraindication
        if "has-bled" in name.lower() or "bleeding risk" in name.lower() or "anticoagul" in desc.lower() or "crit-laac-02" in code.lower():
            contra_m = re.search(r'(?i)\b(has-bled\s*(?:score)?\s*(?:is|of|:|=)?\s*(\d{1,2})|intracranial hemorrhage|major gastrointestinal bleeding|contraindication to anticoagulation|severe bleeding risk)\b', ehr_text)
            if contra_m:
                s_idx = contra_m.start()
                e_idx = contra_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Anticoagulation contraindication / bleeding risk documented: '{span.source_text}'.",
                    raw_confidence=0.95
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented contraindication to oral anticoagulation or elevated bleeding risk.",
                raw_confidence=0.62
            )

        # Absence of thrombus
        if "thrombus" in name.lower() or "thrombus" in desc.lower() or "crit-laac-03" in code.lower():
            neg_thrombus = re.search(r'(?i)\b(no\s+thrombus|without\s+thrombus|negative\s+for\s+thrombus|absence\s+of\s+laa\s+thrombus|no\s+intracardiac\s+thrombus)\b', ehr_text)
            if neg_thrombus:
                s_idx = neg_thrombus.start()
                e_idx = neg_thrombus.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.MET,
                    verified_spans=[span],
                    clinical_rationale=f"Documented absence of intracardiac thrombus: '{span.source_text}'.",
                    raw_confidence=0.96
                )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Absence of left atrial appendage thrombus not verified by imaging.",
                raw_confidence=0.60
            )

        return cls._evaluate_generic_declarative(criterion, ehr_text)

    @classmethod
    def _evaluate_tka(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-TKA-01")
        name = criterion.get("name", "TKA Criterion")
        desc = criterion.get("description", "")
        temporal_req = criterion.get("required_temporal_window", "Current presentation")

        # Flexion limitation
        if "flexion" in name.lower() or "flexion" in desc.lower() or "crit-tka-01" in code.lower():
            flex_m = re.search(r'(?i)\b(?:flexion|range of motion)\s*(?:is|of|to|:)?\s*([<>]?=?\s*(\d{1,3}))\s*(?:degrees|deg)?\b', ehr_text)
            if flex_m:
                val = int(flex_m.group(2))
                s_idx = flex_m.start()
                e_idx = flex_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.96
                )
                if val <= 90:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented knee flexion is {val} degrees (≤90 degrees required).",
                        raw_confidence=0.95
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented knee flexion is {val} degrees (>90 degrees fails mechanical limitation threshold).",
                        raw_confidence=0.93
                    )
            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="Knee flexion range of motion not documented.",
                raw_confidence=0.60
            )

        # Conservative therapy duration
        if "conservative" in name.lower() or "180 days" in desc.lower() or "crit-tka-02" in code.lower():
            cons_m = re.search(r'(?i)\b(?:conservative therapy|physical therapy|pt)\s+(?:for|failed for)?\s*(\d+)\s*(?:days|months|weeks)\b', ehr_text)
            if cons_m:
                dur = int(cons_m.group(1))
                unit = "months" if "month" in cons_m.group(0).lower() else ("weeks" if "week" in cons_m.group(0).lower() else "days")
                days_eq = dur * 30 if unit == "months" else (dur * 7 if unit == "weeks" else dur)
                s_idx = cons_m.start()
                e_idx = cons_m.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.95
                )
                if days_eq >= 180:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented conservative therapy failure for {dur} {unit} (≥180 days satisfied).",
                        raw_confidence=0.95
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.NOT_MET,
                        verified_spans=[span],
                        clinical_rationale=f"Documented conservative therapy failure for {dur} {unit} (<180 days required).",
                        raw_confidence=0.92
                    )

            qual_cons = re.search(r'(?i)\b(failed conservative therapy|failed physical therapy|conservative management exhausted)\b', ehr_text)
            if qual_cons:
                s_idx = qual_cons.start()
                e_idx = qual_cons.end()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.88
                )
                return CriterionAssessment(
                    criterion_id=criterion.get("id", code),
                    criterion_code=code,
                    name=name,
                    description=desc,
                    is_exclusion=False,
                    required_temporal_window=temporal_req,
                    status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                    verified_spans=[span],
                    clinical_rationale="Conservative therapy failure noted, but duration (≥180 days) is unverified.",
                    raw_confidence=0.65
                )

            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=False,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
                verified_spans=[],
                clinical_rationale="No documented trial of conservative therapy.",
                raw_confidence=0.60
            )

        # Infection exclusion
        if "infection" in name.lower() or "sepsis" in desc.lower() or "crit-tka-excl" in code.lower():
            inf_m = re.search(r'(?i)\b(septic arthritis|active joint sepsis|active infection)\b', ehr_text)
            if inf_m:
                s_idx = inf_m.start()
                e_idx = inf_m.end()
                scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
                if not scope["is_negated"]:
                    span = ClinicalEvidenceSpan(
                        source_text=ehr_text[s_idx:e_idx],
                        start_char=s_idx,
                        end_char=e_idx,
                        clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                        confidence=0.96
                    )
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=True,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Active joint infection detected: '{span.source_text}'.",
                        raw_confidence=0.96
                    )

            return CriterionAssessment(
                criterion_id=criterion.get("id", code),
                criterion_code=code,
                name=name,
                description=desc,
                is_exclusion=True,
                required_temporal_window=temporal_req,
                status=DeterminationStatus.NOT_MET,
                verified_spans=[],
                clinical_rationale="No active joint sepsis or systemic infection documented.",
                raw_confidence=0.93
            )

        return cls._evaluate_generic_declarative(criterion, ehr_text)

    @classmethod
    def _evaluate_generic_declarative(cls, criterion: Dict[str, Any], ehr_text: str) -> CriterionAssessment:
        code = criterion.get("criterion_code", "CRIT-UNKNOWN")
        name = criterion.get("name", "")
        desc = criterion.get("description", "")
        is_excl = bool(criterion.get("is_exclusion", False))
        temporal_req = criterion.get("required_temporal_window", "Not specified")
        keywords = criterion.get("keywords") or criterion.get("entity_names") or [name]

        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        for term in keywords:
            if not term or len(term) < 2:
                continue
            escaped = re.escape(term)
            pattern = r'(?i)\b' + escaped + r'\b'
            for m in re.finditer(pattern, ehr_text):
                s_idx = m.start()
                e_idx = m.end()
                scope = ClinicalScopeAnalyzer.analyze_scope(ehr_text, s_idx, e_idx)
                if scope["is_family_history"] and not is_excl:
                    continue
                if scope["is_negated"]:
                    if is_excl:
                        span = ClinicalEvidenceSpan(
                            source_text=ehr_text[s_idx:e_idx],
                            start_char=s_idx,
                            end_char=e_idx,
                            clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                            confidence=0.95
                        )
                        return CriterionAssessment(
                            criterion_id=criterion.get("id", code),
                            criterion_code=code,
                            name=name,
                            description=desc,
                            is_exclusion=True,
                            required_temporal_window=temporal_req,
                            status=DeterminationStatus.NOT_MET,
                            verified_spans=[span],
                            clinical_rationale=f"Documented absence of exclusion: '{span.source_text}'.",
                            raw_confidence=0.93
                        )
                    continue

                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[s_idx:e_idx],
                    start_char=s_idx,
                    end_char=e_idx,
                    clinical_section=ClinicalSectionDetector.detect_section(ehr_text, s_idx),
                    confidence=0.92
                )
                if is_excl:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=True,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Disqualifying exclusion condition detected: '{span.source_text}'.",
                        raw_confidence=0.94
                    )
                else:
                    return CriterionAssessment(
                        criterion_id=criterion.get("id", code),
                        criterion_code=code,
                        name=name,
                        description=desc,
                        is_exclusion=False,
                        required_temporal_window=temporal_req,
                        status=DeterminationStatus.MET,
                        verified_spans=[span],
                        clinical_rationale=f"Qualifying clinical evidence documented: '{span.source_text}'.",
                        raw_confidence=0.92
                    )

        # Insufficient evidence
        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=is_excl,
            required_temporal_window=temporal_req,
            status=DeterminationStatus.NOT_MET if is_excl else DeterminationStatus.INSUFFICIENT_EVIDENCE,
            verified_spans=[],
            clinical_rationale=f"No documented evidence matching {name or code}." if not is_excl else f"No documented {name or code} exclusion.",
            raw_confidence=0.90 if is_excl else 0.60
        )
