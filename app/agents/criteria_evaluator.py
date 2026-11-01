import re
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.contracts import (
    DeterminationStatus,
    ClinicalEvidenceSpan,
    CriterionAssessment
)

class CriteriaEvaluationAgent:
    """
    Agent 2: Criteria Evaluation Agent
    Extracts clinical entities, diagnostic values, and temporal preconditions from raw EHR narratives,
    anchoring evidence to exact character offsets and mapping patient facts to retrieved CMS criteria.
    """

    def __init__(self):
        pass

    def detect_clinical_section(self, text: str, char_pos: int) -> str:
        """
        Determines the clinical section of the EHR based on section headers preceding the character position.
        """
        headers = [
            ("History of Present Illness", [r"(?i)\bhistory of present illness\b", r"(?i)\bhpi\b"]),
            ("Past Medical History", [r"(?i)\bpast medical history\b", r"(?i)\bpmh\b"]),
            ("Medications", [r"(?i)\bmedications\b", r"(?i)\bcurrent meds\b", r"(?i)\bgdmt\b"]),
            ("Diagnostic Studies", [r"(?i)\bdiagnostics\b", r"(?i)\bechocardiogram\b", r"(?i)\becho\b", r"(?i)\bpolysomnography\b", r"(?i)\blabs\b"]),
            ("Physical Examination", [r"(?i)\bphysical examination\b", r"(?i)\bexam\b"]),
            ("Assessment & Plan", [r"(?i)\bassessment & plan\b", r"(?i)\bassessment and plan\b", r"(?i)\bplan\b", r"(?i)\ba/p\b"])
        ]

        # Scan text before char_pos
        prior_text = text[:char_pos]
        last_found_section = "Clinical Documentation"
        last_found_index = -1

        for sec_name, patterns in headers:
            for pat in patterns:
                for match in re.finditer(pat, prior_text):
                    if match.start() > last_found_index:
                        last_found_index = match.start()
                        last_found_section = sec_name

        return last_found_section

    def find_span(self, text: str, pattern: str, section: Optional[str] = None) -> Optional[ClinicalEvidenceSpan]:
        """
        Finds the first regex pattern match in text and returns ClinicalEvidenceSpan with exact character offsets.
        """
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start_c = match.start()
            end_c = match.end()
            source_txt = text[start_c:end_c]
            sec = section or self.detect_clinical_section(text, start_c)
            return ClinicalEvidenceSpan(
                source_text=source_txt,
                start_char=start_c,
                end_char=end_c,
                clinical_section=sec,
                confidence=0.95
            )
        return None

    @classmethod
    def analyze_clinical_scope(cls, text: str, span_start: int, span_end: int) -> Dict[str, Any]:
        """
        Clinical NegEx & ConText Scope Analyzer.
        Inspects preceding and following text windows around a clinical evidence span:
        1. Negation triggers (pre- and post-negation)
        2. Experiencer triggers (Family history vs patient)
        """
        preceding_window = text[max(0, span_start - 60):span_start].lower()
        following_window = text[span_end:min(len(text), span_end + 35)].lower()

        pre_negations = [
            r"\b(?:no|not|denies|denied|denying|without|negative for|ruled out|free of|absence of|never)\b",
            r"\b(?:no evidence of|no history of|no signs of|fails to demonstrate|unremarkable for)\b"
        ]
        post_negations = [
            r"\b(?:is ruled out|was ruled out|is absent|unlikely)\b"
        ]
        experiencer_triggers = [
            r"\b(?:mother|father|sister|brother|maternal|paternal|family history|fhx|relative|parent)\b"
        ]
        conjunctions = [r"\b(?:but|however|nevertheless|although|except|yet)\b"]

        last_conjunction = -1
        for conj in conjunctions:
            for m in re.finditer(conj, preceding_window):
                if m.start() > last_conjunction:
                    last_conjunction = m.start()

        active_preceding = preceding_window[last_conjunction + 1:] if last_conjunction != -1 else preceding_window

        is_negated = False
        negation_trigger = None
        for pat in pre_negations:
            m = re.search(pat, active_preceding)
            if m:
                is_negated = True
                negation_trigger = m.group(0)
                break

        if not is_negated:
            for pat in post_negations:
                m = re.search(pat, following_window)
                if m:
                    is_negated = True
                    negation_trigger = m.group(0)
                    break

        is_family_history = False
        experiencer = "PATIENT"
        for pat in experiencer_triggers:
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


    def evaluate_criterion(
        self,
        criterion: Dict[str, Any],
        ehr_text: str
    ) -> CriterionAssessment:
        """
        Evaluates a single policy criterion against the EHR narrative.
        Extracts verified spans, temporal logic, and clinical status.
        """
        code = criterion.get("criterion_code", "")
        name = criterion.get("name", "")
        desc = criterion.get("description", "")
        is_excl = criterion.get("is_exclusion", False)
        temporal_req = criterion.get("required_temporal_window", "Not specified")
        keywords = criterion.get("keywords", [])

        spans: List[ClinicalEvidenceSpan] = []
        status = DeterminationStatus.INSUFFICIENT_EVIDENCE
        rationale = ""
        raw_confidence = 0.50
        temporal_window_met = None

        text_lower = ehr_text.lower()

        # =========================================================================
        # 1. CARDIAC CRITERIA (NCD 20.4 ICD Coverage)
        # =========================================================================
        if "lvef" in code.lower() or "ejection fraction" in name.lower() or "lvef" in desc.lower():
            # Search for LVEF patterns e.g., "LVEF 25%", "LVEF of 30%", "LVEF <= 35%", "Left Ventricular Ejection Fraction (LVEF) of 28%"
            lvef_match = re.search(r'(?i)\b(lvef|left ventricular ejection fraction)\s*(?:\([a-z0-9\s]+\)\s*)?(?:is|of|:)?\s*([<>]?=?\s*(\d{1,2}))%', ehr_text)
            if lvef_match:
                val = int(lvef_match.group(3))
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[lvef_match.start():lvef_match.end()],
                    start_char=lvef_match.start(),
                    end_char=lvef_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, lvef_match.start()),
                    confidence=0.98
                )
                spans.append(span)

                # Detect diagnostic imaging modality
                mod_match = re.search(r'(?i)\b(tte|transthoracic echocardiogram|echocardiography|echocardiogram|echo|tee|transesophageal echocardiogram|cardiac mri|cmr|radionuclide ventriculography|muga|left ventriculography|ventriculogram)\b', ehr_text)
                if mod_match:
                    m_str = mod_match.group(0).lower()
                    if m_str in ["tte", "transthoracic echocardiogram"]:
                        modality_name = "Transthoracic Echocardiogram"
                    elif m_str in ["tee", "transesophageal echocardiogram"]:
                        modality_name = "Transesophageal Echocardiogram"
                    elif m_str in ["cmr", "cardiac mri"]:
                        modality_name = "Cardiac MRI (CMR)"
                    elif m_str in ["muga", "radionuclide ventriculography"]:
                        modality_name = "MUGA Scan"
                    elif "ventriculo" in m_str:
                        modality_name = "Left Ventriculography"
                    else:
                        modality_name = "Echocardiography"
                else:
                    modality_name = "Diagnostic Imaging"

                if val <= 35:
                    status = DeterminationStatus.MET
                    rationale = f"Documented LVEF is {val}% confirmed by {modality_name}, meeting the mandatory primary prevention threshold of ≤35% (HFrEF)."
                    raw_confidence = 0.96
                elif 36 <= val <= 49:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Documented LVEF is {val}% via {modality_name} (Heart Failure with Mildly Reduced Ejection Fraction / HFmrEF). Fails the Medicare NCD 20.4 primary prevention threshold of ≤35%."
                    raw_confidence = 0.94
                else:  # val >= 50%
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Documented LVEF is {val}% via {modality_name} (Heart Failure with Preserved Ejection Fraction / HFpEF). CMS NCD 20.4 restricts primary prevention ICD coverage strictly to severe systolic dysfunction (HFrEF with LVEF ≤ 35%). Prophylactic device placement is not indicated for preserved systolic function."
                    raw_confidence = 0.95
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "No documented left ventricular ejection fraction (LVEF) measurement found in diagnostic reports."
                raw_confidence = 0.60

        elif "nyha" in code.lower() or "functional class" in name.lower() or "nyha" in desc.lower():
            # NYHA Class II or III
            nyha_match = re.search(r'(?i)\b(nyha|new york heart association)\s*(?:functional\s+)?(?:class)?\s*([IVX]+|\d)\b', ehr_text)
            if nyha_match:
                cls_str = nyha_match.group(2).upper()
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[nyha_match.start():nyha_match.end()],
                    start_char=nyha_match.start(),
                    end_char=nyha_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, nyha_match.start()),
                    confidence=0.95
                )
                spans.append(span)
                if cls_str in ["II", "III", "2", "3"]:
                    status = DeterminationStatus.MET
                    rationale = f"Patient classified as NYHA Class {cls_str} heart failure symptoms."
                    raw_confidence = 0.94
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Patient classified as NYHA Class {cls_str}, which does not meet qualifying Class II/III criteria."
                    raw_confidence = 0.91
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "NYHA functional heart failure class not documented in physical exam or assessment."
                raw_confidence = 0.62

        elif "gdmt" in code.lower() or "medical therapy" in name.lower() or "optimal medical" in desc.lower():
            # GDMT requirement: beta blockers, ace/arb/arni, aldosterone antagonist, with temporal >=90 days
            # Or documented clinical contraindication/intolerance (angioedema, hyperkalemia, severe renal impairment, bradycardia)
            gdmt_pattern = r'(?i)\b(gdmt|guideline-directed medical therapy|optimal medical therapy|beta[- ]blocker|carvedilol|metoprolol|lisinopril|entresto|sacubitril|spironolactone|eplerenone|dapagliflozin|empagliflozin)\b'
            time_pattern = r'(?i)\b(?:for\s+|at least\s+|stable for\s+)?(?:>|>=|over|more than)?\s*(\d+)\s*(?:months|days|weeks)\b'
            contra_pattern = r'(?i)\b(contraindicated|contraindication|intolerant|intolerance|allergy|angioedema|hyperkalemia|severe renal impairment|prohibitive bradycardia)\b'
            
            med_match = re.search(gdmt_pattern, ehr_text)
            time_match = re.search(time_pattern, ehr_text)
            contra_match = re.search(contra_pattern, ehr_text)

            contra_note = ""
            if contra_match:
                span_c = ClinicalEvidenceSpan(
                    source_text=ehr_text[contra_match.start():contra_match.end()],
                    start_char=contra_match.start(),
                    end_char=contra_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, contra_match.start()),
                    confidence=0.93
                )
                spans.append(span_c)
                contra_note = f"; clinical exception recognized for documented contraindication/intolerance ('{contra_match.group(0)}')"

            if med_match:
                span1 = ClinicalEvidenceSpan(
                    source_text=ehr_text[med_match.start():med_match.end()],
                    start_char=med_match.start(),
                    end_char=med_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, med_match.start()),
                    confidence=0.92
                )
                spans.append(span1)

                if time_match:
                    span2 = ClinicalEvidenceSpan(
                        source_text=ehr_text[time_match.start():time_match.end()],
                        start_char=time_match.start(),
                        end_char=time_match.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, time_match.start()),
                        confidence=0.94
                    )
                    spans.append(span2)

                    # Check duration
                    raw_dur_str = time_match.group(0).lower()
                    if "month" in raw_dur_str:
                        nums = re.findall(r'\d+', raw_dur_str)
                        months = int(nums[0]) if nums else 3
                        if months >= 3:
                            status = DeterminationStatus.MET
                            temporal_window_met = True
                            rationale = f"Documented guideline-directed medical therapy sustained for {months} months (meets >=90 day / 3 month CMS threshold){contra_note}."
                            raw_confidence = 0.95
                        else:
                            status = DeterminationStatus.NOT_MET
                            temporal_window_met = False
                            rationale = f"GDMT documented for only {months} months (< 3 months requirement){contra_note}."
                            raw_confidence = 0.90
                    elif "week" in raw_dur_str:
                        nums = re.findall(r'\d+', raw_dur_str)
                        weeks = int(nums[0]) if nums else 12
                        if weeks >= 12:
                            status = DeterminationStatus.MET
                            temporal_window_met = True
                            rationale = f"Documented guideline-directed medical therapy sustained for {weeks} weeks (meets >=90 day / 12 weeks CMS threshold){contra_note}."
                            raw_confidence = 0.95
                        else:
                            status = DeterminationStatus.NOT_MET
                            temporal_window_met = False
                            rationale = f"GDMT documented for only {weeks} weeks (< 12 weeks / 90 days requirement){contra_note}."
                            raw_confidence = 0.90
                    elif "day" in raw_dur_str:
                        nums = re.findall(r'\d+', raw_dur_str)
                        days = int(nums[0]) if nums else 90
                        if days >= 90:
                            status = DeterminationStatus.MET
                            temporal_window_met = True
                            rationale = f"Documented guideline-directed medical therapy sustained for {days} days (meets >=90 day CMS threshold){contra_note}."
                            raw_confidence = 0.95
                        else:
                            status = DeterminationStatus.NOT_MET
                            temporal_window_met = False
                            rationale = f"GDMT documented for only {days} days (< 90 days requirement){contra_note}."
                            raw_confidence = 0.90
                    else:
                        status = DeterminationStatus.MET
                        temporal_window_met = True
                        rationale = f"Documented GDMT compliance: {raw_dur_str}{contra_note}."
                        raw_confidence = 0.92
                else:
                    # Medications present but duration omitted
                    status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                    temporal_window_met = False
                    rationale = f"Medications identified, but duration of therapy (≥90 days prerequisite) is not substantiated in note{contra_note}."
                    raw_confidence = 0.70
            elif contra_match and time_match:
                # Patient has contraindication documented with sustained timeline
                status = DeterminationStatus.MET
                temporal_window_met = True
                rationale = f"Patient has documented clinical contraindication to standard medical therapy sustained for required window{contra_note}."
                raw_confidence = 0.90
            else:
                status = DeterminationStatus.NOT_MET
                temporal_window_met = False
                rationale = "No documented guideline-directed heart failure medical therapy found."
                raw_confidence = 0.88

        elif "crit-icd-04" in code.lower() or "revascularization" in code.lower() or "post-mi" in code.lower() or "waiting period" in name.lower() or "revascularization" in name.lower() or "cardiomyopathy etiology" in name.lower():
            # Temporal waiting period: >= 40 days post-MI, >= 90 days post-CABG/PCI
            mi_match = re.search(r'(?i)\b(myocardial infarction|mi|stemi|nstemi|cabg|pci|revascularization)\b(?:\s*.*?(\d+)\s*(days|months|weeks|years)\s*ago)?', ehr_text)
            if mi_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[mi_match.start():mi_match.end()],
                    start_char=mi_match.start(),
                    end_char=mi_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, mi_match.start()),
                    confidence=0.90
                )
                spans.append(span)
                status = DeterminationStatus.MET
                temporal_window_met = True
                rationale = f"Event timeline documented: {span.source_text}; satisfies CMS mandatory post-event waiting periods."
                raw_confidence = 0.91
            else:
                # No recent MI or revascularization implies criterion satisfied or not an exclusion
                status = DeterminationStatus.MET
                temporal_window_met = True
                rationale = "No acute MI (<40 days) or recent revascularization (<90 days) disqualifying the patient."
                raw_confidence = 0.88

        elif is_excl and ("shock" in desc.lower() or "terminal" in desc.lower() or "survival" in desc.lower() or "exclusion" in code.lower()):
            # Disqualifying Exclusion Check (Active Cardiogenic Shock, Metastatic Cancer / Terminal Illness < 1 Year)
            pos_pattern = r'(?i)\b(?:active cardiogenic shock|in cardiogenic shock|refractory cardiogenic shock|cardiogenic shock|metastatic\s+(?:[a-z]+\s+)?(?:cancer|malignancy|disease)|end-stage malignancy|terminal illness|terminal non-cardiac illness|hospice(?:-directed)?|life expectancy\s*(?:<|less than)\s*1\s*year)\b'
            active_exclusion_found = False
            for m in re.finditer(pos_pattern, ehr_text):
                s_idx = m.start()
                e_idx = m.end()
                scope = self.analyze_clinical_scope(ehr_text, s_idx, e_idx)
                if not scope["is_negated"]:
                    span = ClinicalEvidenceSpan(
                        source_text=ehr_text[s_idx:e_idx],
                        start_char=s_idx,
                        end_char=e_idx,
                        clinical_section=self.detect_clinical_section(ehr_text, s_idx),
                        confidence=0.96
                    )
                    spans.append(span)
                    status = DeterminationStatus.MET
                    rationale = f"Disqualifying exclusion criterion detected: {span.source_text}."
                    raw_confidence = 0.96
                    active_exclusion_found = True
                    break

            if not active_exclusion_found:
                neg_match = re.search(r'(?i)\b(no|without|denies|negative for|absence of)\s+(?:active\s+|acute\s+)?(cardiogenic shock|terminal illness|terminal non-cardiac illness|end-stage malignancy|hospice)\b', ehr_text)
                if neg_match:
                    span = ClinicalEvidenceSpan(
                        source_text=ehr_text[neg_match.start():neg_match.end()],
                        start_char=neg_match.start(),
                        end_char=neg_match.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, neg_match.start()),
                        confidence=0.96
                    )
                    spans.append(span)
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Documented absence of disqualifying exclusion: {span.source_text}."
                    raw_confidence = 0.95
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = "No documented disqualifying cardiogenic shock or non-cardiac disease limiting 1-year survival."
                    raw_confidence = 0.93

        # =========================================================================
        # 2. SLEEP APNEA / CPAP CRITERIA (LCD L33829)
        # =========================================================================
        elif "crit-cpap-01" in code.lower() or "ahi" in code.lower() or "sleep study" in name.lower() or "polysomnography" in name.lower() or "apnea" in desc.lower():
            # AHI >= 15 or AHI 5-14 with symptoms (hypertension, excessive daytime sleepiness, stroke)
            ahi_match = re.search(r'(?i)\b(ahi|apnea-hypopnea index|rdi)\b(?:\s*\([a-z0-9]+\))?\s*(?:of|is|:)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:events\/hr)?\b', ehr_text)
            if not ahi_match:
                ahi_match = re.search(r'(?i)\b(?:ahi|rdi)\s*(?:of|is|:)?\s*(\d{1,3}(?:\.\d+)?)', ehr_text)

            if ahi_match:
                # Capture the numerical value
                num_match = re.search(r'\d+(?:\.\d+)?', ahi_match.group(0))
                val = float(num_match.group(0)) if num_match else 0.0
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[ahi_match.start():ahi_match.end()],
                    start_char=ahi_match.start(),
                    end_char=ahi_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, ahi_match.start()),
                    confidence=0.97
                )
                spans.append(span)
                if val >= 15.0:
                    status = DeterminationStatus.MET
                    rationale = f"Polysomnography demonstrates AHI of {val} events/hr (meets severe OSA threshold ≥15 events/hr)."
                    raw_confidence = 0.96
                elif val >= 5.0:
                    # Check for comorbid symptoms (must be non-negated to qualify)
                    symp_pattern = r'(?i)\b(excessive daytime sleepiness|eds|hypertension|htn|insomnia|ischemic heart disease|stroke)\b'
                    found_qualifying_symp = False
                    for m_s in re.finditer(symp_pattern, ehr_text):
                        scope = self.analyze_clinical_scope(ehr_text, m_s.start(), m_s.end())
                        if not scope["is_negated"]:
                            span_symp = ClinicalEvidenceSpan(
                                source_text=ehr_text[m_s.start():m_s.end()],
                                start_char=m_s.start(),
                                end_char=m_s.end(),
                                clinical_section=self.detect_clinical_section(ehr_text, m_s.start()),
                                confidence=0.92
                            )
                            spans.append(span_symp)
                            status = DeterminationStatus.MET
                            rationale = f"AHI of {val} events/hr accompanied by documented comorbid symptoms ({span_symp.source_text})."
                            raw_confidence = 0.92
                            found_qualifying_symp = True
                            break
                    if not found_qualifying_symp:
                        # Check if comorbidities were explicitly evaluated/negated or completely absent
                        neg_comorb_match = re.search(r'(?i)\b(?:denies|no|without|negative for)\b[^\.\n]*\b(daytime sleepiness|hypertension|stroke|insomnia)\b', ehr_text)
                        if neg_comorb_match:
                            span_neg = ClinicalEvidenceSpan(
                                source_text=ehr_text[neg_comorb_match.start():neg_comorb_match.end()],
                                start_char=neg_comorb_match.start(),
                                end_char=neg_comorb_match.end(),
                                clinical_section=self.detect_clinical_section(ehr_text, neg_comorb_match.start()),
                                confidence=0.95
                            )
                            spans.append(span_neg)
                            status = DeterminationStatus.NOT_MET
                            rationale = f"AHI of {val} events/hr falls in the 5-14 band, but required comorbidities (hypertension, stroke, excessive daytime sleepiness) are explicitly absent/negated: '{span_neg.source_text}'."
                            raw_confidence = 0.95
                        else:
                            status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                            rationale = f"AHI of {val} events/hr (5-14 range) requires comorbid condition documentation which is missing."
                            raw_confidence = 0.75
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"AHI of {val} events/hr fails the minimum diagnostic threshold for covered CPAP therapy (<5 events/hr)."
                    raw_confidence = 0.95
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "No documented polysomnography diagnostic study or Apnea-Hypopnea Index (AHI) found."
                raw_confidence = 0.65

        elif "crit-cpap-02" in code.lower() or "face-to-face" in name.lower():
            eval_match = re.search(r'(?i)\b(face-to-face|in-person|clinical evaluation|sleep specialist consultation)\b', ehr_text)
            if eval_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[eval_match.start():eval_match.end()],
                    start_char=eval_match.start(),
                    end_char=eval_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, eval_match.start()),
                    confidence=0.92
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented clinical evaluation: {span.source_text} prior to sleep study."
                raw_confidence = 0.93
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "Prerequisite face-to-face clinical evaluation prior to PSG not clearly confirmed."
                raw_confidence = 0.68

        # =========================================================================
        # 3. HYPERBARIC OXYGEN THERAPY (NCD 20.29 Diabetic Wounds)
        # =========================================================================
        elif "wagner" in code.lower() or "wound grade" in name.lower() or "wagner" in desc.lower():
            wagner_match = re.search(r'(?i)\b(wagner\s*(?:grade|class)?\s*([1-5]|I|II|III|IV|V)|deep ulceration|gangrene|osteomyelitis)\b', ehr_text)
            if wagner_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[wagner_match.start():wagner_match.end()],
                    start_char=wagner_match.start(),
                    end_char=wagner_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, wagner_match.start()),
                    confidence=0.96
                )
                spans.append(span)
                matched_val = wagner_match.group(0).lower()
                if any(x in matched_val for x in ["3", "4", "iii", "iv", "osteomyelitis", "gangrene"]):
                    status = DeterminationStatus.MET
                    rationale = f"Diabetic wound graded as {span.source_text}, satisfying Wagner Grade 3 or higher CMS requirement."
                    raw_confidence = 0.96
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Diabetic wound graded as {span.source_text}, failing the requirement for Grade III/IV or deeper tissue involvement."
                    raw_confidence = 0.92
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "No documented Wagner wound classification or depth staging found in physical exam."
                raw_confidence = 0.62

        elif "wound_care" in code.lower() or "prior therapy" in name.lower() or "30 days" in desc.lower():
            prior_wc_match = re.search(r'(?i)\b(standard wound care|debridement|dressings|offloading)\s*(?:for\s*(\d+)\s*(days|weeks|months)|at least 30 days|failed 30 days)?\b', ehr_text)
            if prior_wc_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[prior_wc_match.start():prior_wc_match.end()],
                    start_char=prior_wc_match.start(),
                    end_char=prior_wc_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, prior_wc_match.start()),
                    confidence=0.91
                )
                spans.append(span)
                status = DeterminationStatus.MET
                temporal_window_met = True
                rationale = f"Documented prior standard wound therapy: {span.source_text}."
                raw_confidence = 0.91
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                temporal_window_met = False
                rationale = "Documentation of at least 30 days of standard conservative wound management prior to HBOT is absent."
                raw_confidence = 0.70


        # =========================================================================
        # 4. TRANSCATHETER MITRAL / AORTIC VALVE (NCD 20.33 TEER & TAVR)
        # =========================================================================
        elif "crit-teer-01" in code.lower() or "crit-tavr-01" in code.lower() or "mitral regurgitation" in name.lower() or "aortic stenosis" in name.lower():
            # Check for Severe Mitral Regurgitation (TEER)
            mr_match = re.search(r"(?i)\b(moderate-to-severe|severe|grade\s*[34]\+?|grade\s*(?:iii|iv)\+?|3\+|4\+)\s*(?:primary|secondary|functional)?\s*(?:mitral regurgitation|mr)\b|\b(?:mitral regurgitation|mr)\s*(?:is\s*)?(?:moderate-to-severe|severe|grade\s*[34]\+?|grade\s*(?:iii|iv)\+?|3\+|4\+)\b", ehr_text)
            
            # Check for Quantified Aortic Stenosis (TAVR)
            ava_m = re.search(r'(?i)\b(?:aortic valve area|ava)\s*(?:\(ava\))?\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\s*(?:cm2|cm²)?\b', ehr_text)
            grad_m = re.search(r'(?i)\b(?:mean (?:transvalvular )?gradient)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d{1,3}(?:\.\d+)?))\s*mm\s*hg\b', ehr_text)
            vel_m = re.search(r'(?i)\b(?:peak (?:aortic )?velocity|vmax|peak velocity)\s*(?:is|of|:)?\s*([<>]?=?\s*(\d+(?:\.\d+)?))\s*m\/s\b', ehr_text)

            ava_val = float(ava_m.group(2)) if ava_m else None
            grad_val = float(grad_m.group(2)) if grad_m else None
            vel_val = float(vel_m.group(2)) if vel_m else None
            quantified_as_present = (ava_val is not None or grad_val is not None or vel_val is not None)

            if mr_match and ("mitral" in ehr_text.lower() or not "aortic" in ehr_text.lower()):
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[mr_match.start():mr_match.end()],
                    start_char=mr_match.start(),
                    end_char=mr_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, mr_match.start()),
                    confidence=0.96
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented severe valvular regurgitation: '{span.source_text}', satisfying NCD 20.33 Grade 3+/4+ criteria."
                raw_confidence = 0.96
            elif quantified_as_present:
                is_severe = (
                    (ava_val is not None and ava_val <= 1.0) or
                    (grad_val is not None and grad_val >= 40.0) or
                    (vel_val is not None and vel_val >= 4.0)
                )
                evidence_texts = []
                if ava_m:
                    spans.append(ClinicalEvidenceSpan(
                        source_text=ehr_text[ava_m.start():ava_m.end()],
                        start_char=ava_m.start(),
                        end_char=ava_m.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, ava_m.start()),
                        confidence=0.98
                    ))
                    evidence_texts.append(ehr_text[ava_m.start():ava_m.end()])
                if grad_m:
                    spans.append(ClinicalEvidenceSpan(
                        source_text=ehr_text[grad_m.start():grad_m.end()],
                        start_char=grad_m.start(),
                        end_char=grad_m.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, grad_m.start()),
                        confidence=0.98
                    ))
                    evidence_texts.append(ehr_text[grad_m.start():grad_m.end()])
                if vel_m:
                    spans.append(ClinicalEvidenceSpan(
                        source_text=ehr_text[vel_m.start():vel_m.end()],
                        start_char=vel_m.start(),
                        end_char=vel_m.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, vel_m.start()),
                        confidence=0.98
                    ))
                    evidence_texts.append(ehr_text[vel_m.start():vel_m.end()])

                if is_severe:
                    status = DeterminationStatus.MET
                    rationale = f"Severe aortic stenosis verified by quantified hemodynamics ({'; '.join(evidence_texts)}), satisfying NCD 20.33."
                    raw_confidence = 0.96
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Aortic stenosis hemodynamics ({'; '.join(evidence_texts)}) do not meet severe thresholds (AVA <= 1.0 cm2, gradient >= 40 mmHg, velocity >= 4.0 m/s); fails NCD 20.33."
                    raw_confidence = 0.94
            else:
                qual_match = re.search(r'(?i)\b(severe calcific aortic stenosis|severe aortic stenosis|calcific aortic stenosis)\b', ehr_text)
                if qual_match:
                    spans.append(ClinicalEvidenceSpan(
                        source_text=ehr_text[qual_match.start():qual_match.end()],
                        start_char=qual_match.start(),
                        end_char=qual_match.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, qual_match.start()),
                        confidence=0.70
                    ))
                    status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                    rationale = "Echocardiogram describes severe aortic stenosis in qualitative terms only; no quantified AVA (<= 1.0 cm2), mean gradient (>= 40 mmHg), or peak velocity (>= 4.0 m/s) recorded. Deferral required for quantified report."
                    raw_confidence = 0.65
                else:
                    status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                    rationale = "No documented quantification of severe valvular regurgitation or aortic stenosis found."
                    raw_confidence = 0.65
        elif "crit-teer-02" in code.lower() or "crit-tavr-02" in code.lower() or ("heart team" in name.lower() and "carotid" not in name.lower() and "cas" not in code.lower()):
            team_match = re.search(r'(?i)\b(multidisciplinary heart team|heart team consensus|sts score\s*(?:is\s*)?(?:[89]|\d{2})%?|prohibitive surgical risk|high surgical risk)\b', ehr_text)
            if team_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[team_match.start():team_match.end()],
                    start_char=team_match.start(),
                    end_char=team_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, team_match.start()),
                    confidence=0.94
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented multidisciplinary evaluation: '{span.source_text}', confirming high/prohibitive surgical risk consensus."
                raw_confidence = 0.94
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "Documented consensus between a cardiothoracic surgeon and interventional cardiologist confirming prohibitive surgical risk is missing."
                raw_confidence = 0.68

        # =========================================================================
        # =========================================================================
        # 4B. PERCUTANEOUS LEFT ATRIAL APPENDAGE CLOSURE (CMS NCD 220.13 LAAC / WATCHMAN)
        # =========================================================================
        elif "crit-laac-01" in code.lower() or "atrial fibrillation" in name.lower() or "stroke risk" in name.lower() or "cha2ds2" in desc.lower():
            chads_match = re.search(r"(?i)\b((?:cha2ds2-vasc|chads-vasc|chads2)(?:\s+score)?\s*(?:calculated at |is |: )?([2-9]|\d{2})|persistent non-valvular atrial fibrillation|atrial fibrillation|afib|a-fib)\b", ehr_text)
            if chads_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[chads_match.start():chads_match.end()],
                    start_char=chads_match.start(),
                    end_char=chads_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, chads_match.start()),
                    confidence=0.95
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented high thromboembolic stroke risk: '{span.source_text}', satisfying NCD 220.13 criteria."
                raw_confidence = 0.95
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "Non-valvular atrial fibrillation with high CHA2DS2-VASc stroke risk is not documented."
                raw_confidence = 0.60

        elif "crit-laac-02" in code.lower() or "has-bled" in name.lower() or "contraindication" in name.lower():
            contra_match = re.search(r"(?i)\b(?:has-bled(?:\s+score)?\s*(?:is|calculated at|:)?\s*([3-9]|\d{2})|contraindication to (?:long-term )?oral anticoagulation|oral anticoagulation is contraindicated|prior intracranial hemorrhage|intracranial hemorrhage|major recurrent (?:gastrointestinal )?hemorrhage)\b", ehr_text)
            if contra_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[contra_match.start():contra_match.end()],
                    start_char=contra_match.start(),
                    end_char=contra_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, contra_match.start()),
                    confidence=0.95
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented contraindication to long-term anticoagulation: '{span.source_text}', satisfying NCD 220.13 criteria."
                raw_confidence = 0.95
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "Formal contraindication to oral anticoagulation or HAS-BLED >= 3 is not documented."
                raw_confidence = 0.60

        elif "crit-laac-03" in code.lower() or "thrombus" in name.lower():
            tee_match = re.search(r"(?i)\b(absence of (?:left atrial )?thrombus|tee[^\.\n]*absence of (?:left atrial )?thrombus)\b", ehr_text)
            thrombus_present = re.search(r"(?i)\b(?:demonstrates|shows|reveals|identified|presence of)?\s*(?:a\s+)?(?:left atrial\s+)?thrombus(?:\s+measuring\s+\d+\s*mm)?\b", ehr_text)
            if tee_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[tee_match.start():tee_match.end()],
                    start_char=tee_match.start(),
                    end_char=tee_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, tee_match.start()),
                    confidence=0.95
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Imaging verified: '{span.source_text}', confirming absence of intracardiac thrombus."
                raw_confidence = 0.95
            elif thrombus_present and not self.analyze_clinical_scope(ehr_text, thrombus_present.start(), thrombus_present.end())["is_negated"]:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[thrombus_present.start():thrombus_present.end()],
                    start_char=thrombus_present.start(),
                    end_char=thrombus_present.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, thrombus_present.start()),
                    confidence=0.95
                )
                spans.append(span)
                status = DeterminationStatus.NOT_MET
                rationale = f"Imaging demonstrated presence of left atrial thrombus: '{span.source_text}', failing mandatory safety requirement for absence of intracardiac thrombus."
                raw_confidence = 0.95
            else:
                status = DeterminationStatus.NOT_MET
                rationale = "Pre-procedural imaging ruling out left atrial thrombus was not documented."
                raw_confidence = 0.85

        # 5. CAROTID ARTERY STENTING (CMS NCD 20.7 CAS / PTA)
        # =========================================================================
        elif "crit-cas-01" in code.lower() or "carotid stenosis" in name.lower() or "stenosis" in desc.lower():
            sten_match = re.search(r'(?i)(\d{1,2})%\s*.*?\b(?:stenosis|narrowing)\b', ehr_text) or re.search(r'(?i)\b(?:stenosis|narrowing)[^\d\n]{0,30}(\d{1,2})%', ehr_text)

            if sten_match:
                val = int(sten_match.group(1))
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[sten_match.start():sten_match.end()],
                    start_char=sten_match.start(),
                    end_char=sten_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, sten_match.start()),
                    confidence=0.96
                )
                spans.append(span)

                symp_match = re.search(r'(?i)\b(tia|transient ischemic attack|stroke|cva|amaurosis fugax|ipsilateral)\b', ehr_text)
                is_symptomatic = bool(symp_match)

                if is_symptomatic and val >= 70:
                    status = DeterminationStatus.MET
                    rationale = f"Documented {val}% carotid stenosis in symptomatic patient with neurological history (meets CMS NCD 20.7 threshold >=70%)."
                    raw_confidence = 0.96
                elif not is_symptomatic and val >= 80:
                    status = DeterminationStatus.MET
                    rationale = f"Documented {val}% carotid stenosis in asymptomatic patient (meets CMS NCD 20.7 threshold >=80%)."
                    raw_confidence = 0.94
                else:
                    status = DeterminationStatus.NOT_MET
                    rationale = f"Carotid stenosis is {val}%, which fails the Medicare NCD 20.7 minimum threshold (>=70% if symptomatic, >=80% if asymptomatic)."
                    raw_confidence = 0.92
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "No documented carotid stenosis percentage found on diagnostic carotid duplex, CTA, or MRA."
                raw_confidence = 0.65

        elif "crit-cas-02" in code.lower() or "high risk for cea" in name.lower() or "hostile neck" in desc.lower() or "surgical risk" in name.lower() or "carotid endarterectomy" in name.lower():
            risk_match = re.search(r'(?i)\b(high risk for open carotid endarterectomy|high risk for open cea|high risk for cea|hostile neck(?: anatomy)?|prior neck radiation|prior radiation|prior radical neck dissection|tracheostomy|severe copd|sts score\s*[>]=?\s*8%|contralateral carotid occlusion|severe cervical arthritis)\b', ehr_text)
            if risk_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[risk_match.start():risk_match.end()],
                    start_char=risk_match.start(),
                    end_char=risk_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, risk_match.start()),
                    confidence=0.94
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented high surgical risk for Carotid Endarterectomy (CEA): '{span.source_text}', satisfying CMS anatomical/medical risk criteria."
                raw_confidence = 0.95
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "Documentation confirming high surgical risk for Carotid Endarterectomy (CEA) is required under NCD 20.7."
                raw_confidence = 0.68

        elif "crit-cas-03" in code.lower() or "embolic protection" in name.lower() or "epd" in desc.lower():
            epd_match = re.search(r'(?i)\b(embolic protection device|epd|distal filter|embolic filter|fda-approved carotid stent)\b', ehr_text)
            if epd_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[epd_match.start():epd_match.end()],
                    start_char=epd_match.start(),
                    end_char=epd_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, epd_match.start()),
                    confidence=0.95
                )
                spans.append(span)
                status = DeterminationStatus.MET
                rationale = f"Documented utilization of mandatory CMS embolic protection system: '{span.source_text}'."
                raw_confidence = 0.96
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = "CMS NCD 20.7 mandates explicit documentation of FDA-approved Embolic Protection Device (EPD) deployment."
                raw_confidence = 0.70

        # =========================================================================
        # 5B. DECLARATIVE POLICY ENGINE DELEGATION
        # =========================================================================
        # If the criterion has declarative fields or matches an unseeded declarative policy,
        # route evaluation directly through DeclarativePolicyEngine for zero-code policy execution.
        elif "threshold" in criterion or "min_duration_days" in criterion or "ordinal_allowed" in criterion or ("criterion_type" in criterion and criterion["criterion_type"] != "FINDING_PRESENCE"):
            from app.services.declarative_engine import DeclarativePolicyEngine
            decl_crit = DeclarativePolicyEngine.compile_from_dict(criterion)
            decl_assessment = DeclarativePolicyEngine.evaluate(decl_crit, ehr_text)
            return decl_assessment

        # =========================================================================
        # 6. GENERAL KEYWORD FALLBACK
        # =========================================================================
        else:
            # Fallback search using criterion keywords
            matched_kw_spans = []
            for kw in keywords:
                if kw and len(kw) > 3:
                    m = re.search(r'(?i)\b' + re.escape(kw) + r'\b', ehr_text)
                    if m:
                        s = ClinicalEvidenceSpan(
                            source_text=ehr_text[m.start():m.end()],
                            start_char=m.start(),
                            end_char=m.end(),
                            clinical_section=self.detect_clinical_section(ehr_text, m.start()),
                            confidence=0.85
                        )
                        matched_kw_spans.append(s)

            is_quantitative = any(re.search(r'\b' + re.escape(term) + r'\b', (code + " " + name + " " + desc).lower()) for term in [
                "threshold", "lvef", "ahi", "rdi", "ava", "gradient", "velocity", "wagner", "cha2ds2", "has-bled", "ejection fraction"
            ])
            if matched_kw_spans and not is_quantitative:
                spans = matched_kw_spans[:2]
                status = DeterminationStatus.NOT_MET if is_excl else DeterminationStatus.MET
                rationale = f"Identified supporting clinical terminology: {', '.join([s.source_text for s in spans])}."
                raw_confidence = 0.82
            elif matched_kw_spans and is_quantitative:
                spans = matched_kw_spans[:2]
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = f"Supporting clinical terms detected ({', '.join([s.source_text for s in spans])}), but quantitative threshold or diagnostic score is not substantiated."
                raw_confidence = 0.65
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = f"No explicit clinical documentation found corresponding to criterion requirement: {desc[:60]}..."
                raw_confidence = 0.65

        # Negation and Family History Scope Verification
        is_negative_req = is_excl or "waiting period" in name.lower() or "post-mi" in code.lower() or "revascularization" in code.lower() or "exclusion" in name.lower() or "crit-icd-04" in code.lower() or "revascularization" in name.lower() or "timeline" in name.lower()

        if spans:
            for sp in spans:
                scope = self.analyze_clinical_scope(ehr_text, sp.start_char, sp.end_char)
                if scope["is_family_history"] and not is_negative_req:
                    status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                    rationale = f"Evidence attributed to family history ({scope['experiencer']}), not patient."
                    raw_confidence = 0.40
                    break
                elif scope["is_negated"]:
                    if not is_negative_req:
                        status = DeterminationStatus.NOT_MET
                        rationale = f"Condition explicitly negated in chart: '{scope['negation_trigger']}'. Mandatory requirement unmet."
                        raw_confidence = 0.90
                        break
                    elif is_negative_req:
                        # Negation of an acute event or exclusion satisfies the absence/waiting period requirement
                        status = DeterminationStatus.MET if not is_excl else DeterminationStatus.NOT_MET
                        rationale += f" [Affirmed Absence: Negation '{scope['negation_trigger']}' confirms event absence.]"
                        raw_confidence = 0.95

        return CriterionAssessment(
            criterion_id=criterion.get("id", code),
            criterion_code=code,
            name=name,
            description=desc,
            is_exclusion=is_excl,
            required_temporal_window=temporal_req,
            status=status,
            verified_spans=spans,
            clinical_rationale=rationale,
            raw_confidence=raw_confidence,
            temporal_window_met=temporal_window_met
        )





def evaluate_patient_against_policy(ehr_text: str, policy: Any) -> Dict[str, Any]:
    """
    Evaluates clinical narrative against Medicare coverage criteria for HL7 Da Vinci CRD CDS Hooks.
    Returns determination ('APPROVED' or 'WARNING'), confidence score, rationale, and missing criteria.
    """
    policy_id = getattr(policy, "policy_id", str(policy)) if policy else "NCD-20.4"
    lower = ehr_text.lower()

    # ROUTE 1: CAROTID ARTERY STENTING (NCD 20.7)
    if policy_id == "NCD-20.7" or "carotid" in lower or "cas" in lower or ("stent" in lower and "endarterectomy" in lower):
        sten_match = re.search(r'(\d{1,2})%\s*.*?\b(?:stenosis|narrowing)\b', lower) or re.search(r'\b(?:stenosis|narrowing)[^\d\n]{0,30}(\d{1,2})%', lower)

        val = int(sten_match.group(1)) if sten_match else None
        is_symptomatic = bool(re.search(r'\b(tia|transient ischemic attack|stroke|cva|amaurosis fugax|ipsilateral)\b', lower))
        has_high_risk = bool(re.search(r'\b(high risk for cea|hostile neck|prior neck radiation|prior radical neck dissection|tracheostomy|severe copd|sts score\s*[>]=?\s*8%|contralateral carotid occlusion)\b', lower))
        has_epd = bool(re.search(r'\b(embolic protection device|epd|distal filter|embolic filter|fda-approved carotid stent)\b', lower))

        stenosis_ok = (is_symptomatic and val is not None and val >= 70) or (not is_symptomatic and val is not None and val >= 80)
        if stenosis_ok and has_high_risk and has_epd:
            return {
                "determination": "APPROVED",
                "confidence_score": 0.96,
                "clinical_rationale": f"Severe carotid stenosis confirmed ({val}%), patient satisfies high-risk criteria for CEA, and embolic protection device deployment is verified under NCD 20.7.",
                "missing_criteria": []
            }

        missing = []
        if not stenosis_ok:
            missing.append("Carotid stenosis >= 70% (symptomatic) or >= 80% (asymptomatic)")
        if not has_high_risk:
            missing.append("Documented high surgical risk for open Carotid Endarterectomy (CEA)")
        if not has_epd:
            missing.append("FDA-approved Embolic Protection Device (EPD) procedural plan")

        return {
            "determination": "WARNING",
            "confidence_score": 0.50,
            "clinical_rationale": "Carotid Artery Stenting requires documentation of severe stenosis threshold, high CEA risk justification, and embolic protection device.",
            "missing_criteria": missing or ["Documentation Deficiency"]
        }

    # ROUTE 2: TRANSCATHETER EDGE-TO-EDGE REPAIR (NCD 20.33)
    if policy_id == "NCD-20.33" or "mitral" in lower or "regurgitation" in lower or "teer" in lower:
        has_severe_mr = bool(re.search(r'\b(severe mitral regurgitation|severe mr|grade 3\+|grade 4\+|grade iii|grade iv)\b', lower))
        has_heart_team = bool(re.search(r'\b(heart team|multidisciplinary heart team|sts score|prohibitive surgical risk|high surgical risk)\b', lower))
        if has_severe_mr and has_heart_team:
            return {
                "determination": "APPROVED",
                "confidence_score": 0.95,
                "clinical_rationale": "Severe Mitral Regurgitation (Grade 3+/4+) and Multidisciplinary Heart Team surgical consensus documented under NCD 20.33.",
                "missing_criteria": []
            }
        missing = []
        if not has_severe_mr:
            missing.append("Documented Grade 3+ or Grade 4+ severe Mitral Regurgitation on echocardiography")
        if not has_heart_team:
            missing.append("Multidisciplinary Heart Team consensus documenting prohibitive surgical risk")
        return {
            "determination": "WARNING",
            "confidence_score": 0.50,
            "clinical_rationale": "TEER prior-authorization requires documented severe MR and Heart Team consensus.",
            "missing_criteria": missing
        }

    # ROUTE 3: IMPLANTABLE CARDIOVERTER DEFIBRILLATORS (NCD 20.4)
    days_match = re.search(r'\b(?:stemi|mi|myocardial infarction)\s+(?:within\s+)?(\d{1,2})\s*days?\s*ago\b', lower)
    if days_match and int(days_match.group(1)) < 40:
        return {
            "determination": "WARNING",
            "confidence_score": 0.45,
            "clinical_rationale": f"Statutory waiting period unmet: Only {days_match.group(1)} days elapsed since acute MI (minimum 40 days required under NCD 20.4).",
            "missing_criteria": [
                "Post-Myocardial Infarction Waiting Period (>= 40 days)",
                "NYHA Functional Class Documentation",
                "Guideline-Directed Medical Therapy (>= 90 days)"
            ]
        }

    # Check for LVEF
    lvef_val = None
    lvef_match = re.search(r'\blvef\s*(?:of|is|:)?\s*(\d{1,2})%', lower)
    if lvef_match:
        lvef_val = int(lvef_match.group(1))

    # Check for NYHA
    has_nyha = bool(re.search(r'\bnyha\s+(?:class\s+)?(?:i{1,3}|iv|[1-4])\b', lower))

    # Check for medical therapy or GDMT
    has_therapy = bool(re.search(r'\b(gdmt|optimal medical therapy|medical therapy|beta-blocker|acei|arb|arni)\b', lower))

    # Approved condition
    if lvef_val is not None and lvef_val <= 35 and has_nyha and has_therapy:
        return {
            "determination": "APPROVED",
            "confidence_score": 0.96,
            "clinical_rationale": f"Severe LV systolic dysfunction verified (LVEF {lvef_val}% <= 35%), NYHA functional class documented, and optimal medical therapy satisfied without statutory waiting period deficits.",
            "missing_criteria": []
        }

    missing = []
    if lvef_val is None or lvef_val > 35:
        missing.append("Documented LVEF <= 35% on diagnostic echocardiography")
    if not has_nyha:
        missing.append("NYHA Functional Class II-III documentation")
    if not has_therapy:
        missing.append("Guideline-Directed Medical Therapy (GDMT) duration documentation")

    return {
        "determination": "WARNING",
        "confidence_score": 0.50,
        "clinical_rationale": "Clinical narrative lacks one or more required Medicare documentation criteria.",
        "missing_criteria": missing or ["Documentation Deficiency"]
    }
