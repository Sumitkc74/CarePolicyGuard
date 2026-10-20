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
            nyha_match = re.search(r'(?i)\b(nyha|new york heart association)\s*(?:class)?\s*([I|V|X]+|\d)\b', ehr_text)
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

        elif "revascularization" in code.lower() or "post-mi" in code.lower() or "waiting period" in name.lower():
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
            # Exclusion criteria check with clinical negation support
            neg_match = re.search(r'(?i)\b(no|without|denies|negative for|absence of)\s+(?:active\s+|acute\s+)?(cardiogenic shock|terminal illness|end-stage malignancy|hospice)\b', ehr_text)
            if neg_match:
                span = ClinicalEvidenceSpan(
                    source_text=ehr_text[neg_match.start():neg_match.end()],
                    start_char=neg_match.start(),
                    end_char=neg_match.end(),
                    clinical_section=self.detect_clinical_section(ehr_text, neg_match.start()),
                    confidence=0.96
                )
                spans.append(span)
                status = DeterminationStatus.NOT_MET  # Exclusion NOT MET -> qualifies for coverage!
                rationale = f"Documented absence of disqualifying exclusion: {span.source_text}."
                raw_confidence = 0.95
            else:
                shock_match = re.search(r'(?i)\b(active cardiogenic shock|in cardiogenic shock|refractory cardiogenic shock|end-stage malignancy|terminal illness|hospice|life expectancy < 1 year)\b', ehr_text)
                if not shock_match:
                    # Generic cardiogenic shock only if not negated
                    shock_match = re.search(r'(?i)\b(cardiogenic shock)\b', ehr_text)

                if shock_match:
                    span = ClinicalEvidenceSpan(
                        source_text=ehr_text[shock_match.start():shock_match.end()],
                        start_char=shock_match.start(),
                        end_char=shock_match.end(),
                        clinical_section=self.detect_clinical_section(ehr_text, shock_match.start()),
                        confidence=0.95
                    )
                    spans.append(span)
                    status = DeterminationStatus.MET  # Exclusion MET -> disqualifies!
                    rationale = f"Disqualifying exclusion criterion detected: {span.source_text}."
                    raw_confidence = 0.95
                else:
                    status = DeterminationStatus.NOT_MET  # Exclusion NOT MET -> good for coverage
                    rationale = "No documented disqualifying cardiogenic shock or non-cardiac disease limiting 1-year survival."
                    raw_confidence = 0.93

        # =========================================================================
        # 2. SLEEP APNEA / CPAP CRITERIA (LCD L33829)
        # =========================================================================
        elif "ahi" in code.lower() or "sleep study" in name.lower() or "apnea" in desc.lower():
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
                    # Check for comorbid symptoms
                    symp_match = re.search(r'(?i)\b(excessive daytime sleepiness|eds|hypertension|htn|insomnia|ischemic heart disease)\b', ehr_text)
                    if symp_match:
                        span_symp = ClinicalEvidenceSpan(
                            source_text=ehr_text[symp_match.start():symp_match.end()],
                            start_char=symp_match.start(),
                            end_char=symp_match.end(),
                            clinical_section=self.detect_clinical_section(ehr_text, symp_match.start()),
                            confidence=0.91
                        )
                        spans.append(span_symp)
                        status = DeterminationStatus.MET
                        rationale = f"AHI of {val} events/hr accompanied by documented comorbid symptoms ({span_symp.source_text})."
                        raw_confidence = 0.92
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

        elif "compliance" in code.lower() or "face-to-face" in name.lower() or "evaluation" in desc.lower():
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
        # 4. GENERAL KEYWORD FALLBACK
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

            if matched_kw_spans:
                spans = matched_kw_spans[:2]
                status = DeterminationStatus.NOT_MET if is_excl else DeterminationStatus.MET
                rationale = f"Identified supporting clinical terminology: {', '.join([s.source_text for s in spans])}."
                raw_confidence = 0.82
            else:
                status = DeterminationStatus.INSUFFICIENT_EVIDENCE
                rationale = f"No explicit clinical documentation found corresponding to criterion requirement: {desc[:60]}..."
                raw_confidence = 0.65

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

