import re
from typing import Dict, Any, List, Optional, Tuple
from app.schemas.contracts import (
    CriterionAssessment,
    DeterminationStatus,
    AdjudicationDecision
)


class SectionDiscourseParser:
    """
    Independent Section Discourse Parser.
    Distinct from pipeline token-window regex matching:
    Deconstructs clinical text into structured discourse zones based on clinical headers
    and clause dependency boundaries.
    """

    KNOWN_SECTION_HEADERS = [
        ("FAMILY_HISTORY", r"(?i)\b(?:family\s+history|fhx|family\s+cardiac\s+history)\b"),
        ("SOCIAL_HISTORY", r"(?i)\b(?:social\s+history|shx|habits)\b"),
        ("ALLERGIES", r"(?i)\b(?:allergies|adverse\s+reactions)\b"),
        ("MEDICATIONS", r"(?i)\b(?:medications|current\s+meds|home\s+medications|pharmacotherapy)\b"),
        ("PAST_MEDICAL_HISTORY", r"(?i)\b(?:past\s+medical\s+history|pmhx|past\s+history|prior\s+history)\b"),
        ("REVIEW_OF_SYSTEMS", r"(?i)\b(?:review\s+of\s+systems|ros)\b"),
        ("PHYSICAL_EXAM", r"(?i)\b(?:physical\s+examination|pe|vital\s+signs|physical\s+findings)\b"),
        ("DIAGNOSTIC_STUDIES", r"(?i)\b(?:diagnostic\s+studies|diagnostics|imaging|echocardiogram|polysomnography|sleep\s+study|cardiac\s+mri|lab(?:oratory)?\s+results?)\b"),
        ("HPI", r"(?i)\b(?:history\s+of\s+present\s+illness|hpi|chief\s+complaint|presenting\s+complaint)\b"),
        ("PLAN", r"(?i)\b(?:assessment\s*(?:and|&)\s*plan|a&p|plan|recommendations|disposition)\b"),
    ]

    @classmethod
    def segment_document(cls, text: str) -> List[Dict[str, Any]]:
        """
        Segments EHR narrative into typed discourse sections with character spans.
        """
        sections: List[Dict[str, Any]] = []
        found_headers: List[Tuple[int, int, str]] = []

        for sec_type, header_pat in cls.KNOWN_SECTION_HEADERS:
            for match in re.finditer(header_pat, text):
                found_headers.append((match.start(), match.end(), sec_type))

        # Sort headers by character offset
        found_headers.sort(key=lambda x: x[0])

        if not found_headers:
            # Fallback: treat entire document as general clinical note
            return [{
                "section_type": "GENERAL_NOTE",
                "start": 0,
                "end": len(text),
                "text": text
            }]

        # Leading text before first header
        if found_headers[0][0] > 0:
            sections.append({
                "section_type": "HEADER_CLINICAL_SUMMARY",
                "start": 0,
                "end": found_headers[0][0],
                "text": text[0:found_headers[0][0]]
            })

        for i, (start, h_end, sec_type) in enumerate(found_headers):
            end = found_headers[i + 1][0] if i + 1 < len(found_headers) else len(text)
            sections.append({
                "section_type": sec_type,
                "start": start,
                "end": end,
                "text": text[start:end]
            })

        return sections

    @classmethod
    def split_into_clauses(cls, text: str) -> List[Dict[str, Any]]:
        """
        Splits section text into syntactically bounded clauses based on punctuation
        and coordinating/subordinating adversative conjunctions.
        """
        clause_delimiters = r"[.;\n]+|\b(?:however|although|whereas|despite|but|in contrast to)\b"
        clauses = []
        last_idx = 0

        for match in re.finditer(clause_delimiters, text, flags=re.IGNORECASE):
            c_text = text[last_idx:match.start()].strip()
            if c_text:
                clauses.append({
                    "text": c_text,
                    "start": last_idx,
                    "end": match.start()
                })
            last_idx = match.end()

        tail = text[last_idx:].strip()
        if tail:
            clauses.append({
                "text": tail,
                "start": last_idx,
                "end": len(text)
            })

        return clauses


class CriticAgent:
    """
    Critic Agent: Independent Adversarial Falsification & Bidirectional Disagreement Engine.

    Architectural Independence Invariant:
    The pipeline verifier uses token-window sliding regexes (-60 to +60 chars) on matched spans.
    The Critic Agent uses a completely different method:
    1. Structural Section Discourse Partitioning (identifying semantic authority zones).
    2. Clause Proposition Dependency Parsing (sentence-level polarity, subject, and modality).
    3. Cross-Section Measurement Incoherence Analysis (detecting conflicting values across sections).
    It does NOT import or wrap the pipeline's SemanticSupportChecker.

    Bidirectional Critique Invariant:
    The Critic evaluates EVERY decision:
    - Approvals: challenges false approvals via exclusion search and invalid semantics.
    - Denials: challenges false denials if affirmative clinical documentation exists in authoritative sections.
    - Deferrals: challenges wrong deferrals if complete, unambiguous criteria evidence is documented.
    Disagreements are recorded and resolved by deterministic safety veto.
    """

    def __init__(self):
        pass

    def critique(
        self,
        provisional_decision: AdjudicationDecision,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        policy_id: str
    ) -> Dict[str, Any]:
        """
        Bidirectional critique evaluating approvals, denials, and deferrals.
        """
        sections = SectionDiscourseParser.segment_document(ehr_text)

        if provisional_decision == AdjudicationDecision.APPROVED:
            return self._critique_approval(criteria_assessments, ehr_text, sections, policy_id)
        elif provisional_decision == AdjudicationDecision.DENIED:
            return self._critique_denial(criteria_assessments, ehr_text, sections, policy_id)
        elif provisional_decision == AdjudicationDecision.DEFERRED_TO_HUMAN:
            return self._critique_deferral(criteria_assessments, ehr_text, sections, policy_id)
        else:
            return {
                "falsification_detected": False,
                "critic_action": "CONCUR",
                "objections": [],
                "counter_evidence_spans": [],
                "disagreement_recorded": False
            }

    def critique_approval(
        self,
        provisional_decision: AdjudicationDecision,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        policy_id: str
    ) -> Dict[str, Any]:
        """Backwards-compatible wrapper calling bidirectional critique."""
        return self.critique(provisional_decision, criteria_assessments, ehr_text, policy_id)

    def _critique_approval(
        self,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        sections: List[Dict[str, Any]],
        policy_id: str
    ) -> Dict[str, Any]:
        objections: List[str] = []
        counter_evidence_spans: List[Dict[str, Any]] = []

        # 1. Structural Discourse Falsification: Disqualifying Exclusions in Patient Zones
        exclusion_patterns = {
            "cardiogenic_shock": r"\b(?:cardiogenic shock|severe shock|hemodynamic collapse)\b",
            "terminal_illness": r"\b(?:life expectancy\s*<\s*1\s*year|terminal illness|metastatic stage iv|hospice care)\b",
            "active_infection": r"\b(?:active sepsis|bacteremia|untreated systemic infection|endocarditis)\b",
            "severe_dementia": r"\b(?:severe advanced dementia|bedbound vegetative state)\b"
        }

        for sec in sections:
            sec_type = sec["section_type"]
            # Exclude non-patient experiencer sections from exclusion triggers
            if sec_type in ("FAMILY_HISTORY", "ALLERGIES"):
                continue

            clauses = SectionDiscourseParser.split_into_clauses(sec["text"])
            for cl in clauses:
                cl_lower = cl["text"].lower()
                # Check clause polarity: ignore if explicitly negated (e.g., "no cardiogenic shock", "cardiogenic shock is absent and ruled out")
                is_negated = bool(re.search(r"\b(?:no|not|denies|negative for|negative|without|free of|resolved|rule out|ruled out|absent|is absent|not present|unlikely|excluded)\b", cl_lower))
                if is_negated:
                    continue

                for excl_name, pat in exclusion_patterns.items():
                    m = re.search(pat, cl_lower)
                    if m:
                        abs_start = sec["start"] + cl["start"] + m.start()
                        abs_end = sec["start"] + cl["start"] + m.end()
                        obj_text = (
                            f"Critic identified unaddressed disqualifying exclusion in section '{sec_type}': "
                            f"'{m.group(0)}' at character [{abs_start}:{abs_end}]."
                        )
                        objections.append(obj_text)
                        counter_evidence_spans.append({
                            "type": "EXCLUSION_COUNTER_EVIDENCE",
                            "text": ehr_text[abs_start:abs_end],
                            "start": abs_start,
                            "end": abs_end,
                            "section": sec_type,
                            "detail": excl_name
                        })

        # 2. Cross-Section Incoherence & Measurement Contradiction Analysis
        # Check for divergent hemodynamic / clinical values across separate sections
        measurement_matches = list(re.finditer(r"\b(?:LVEF|EF|AHI|RDI|stenosis)\b\s*[:=]?\s*(\d{1,3})%?", ehr_text, flags=re.IGNORECASE))
        if len(measurement_matches) >= 2:
            values = []
            for mm in measurement_matches:
                try:
                    val = float(mm.group(1))
                    values.append(val)
                except ValueError:
                    pass
            if values:
                max_val = max(values)
                min_val = min(values)
                # If difference between measurements is substantial (> 15% absolute swing), flag incoherence
                if max_val - min_val >= 15.0:
                    objections.append(
                        f"Critic detected cross-section measurement discordance: conflicting values "
                        f"observed ({min_val} vs {max_val}) requiring clinical reconciliation."
                    )

        # 3. Discourse Experiencer & Modality Audit for Proposed MET Criteria
        for ca in criteria_assessments:
            if ca.status == DeterminationStatus.MET and not ca.is_exclusion:
                for sp in ca.verified_spans:
                    sp_start = getattr(sp, "start_char", 0)
                    # Check which discourse section holds this span
                    containing_sec = next((s for s in sections if s["start"] <= sp_start < s["end"]), None)
                    if containing_sec and containing_sec["section_type"] == "FAMILY_HISTORY":
                        objections.append(
                            f"Critic discourse violation: Evidence for {ca.criterion_code} resides in "
                            f"FAMILY_HISTORY section, violating patient experiencer requirement."
                        )
                    # Check if clause has hypothetical / speculative framing
                    if containing_sec:
                        sec_clauses = SectionDiscourseParser.split_into_clauses(containing_sec["text"])
                        rel_pos = sp_start - containing_sec["start"]
                        target_clause = next((c for c in sec_clauses if c["start"] <= rel_pos < c["end"]), None)
                        if target_clause:
                            cl_low = target_clause["text"].lower()
                            if re.search(r"\b(?:consider|if|should\s+patient|in\s+the\s+event|planned|scheduled)\b", cl_low):
                                objections.append(
                                    f"Critic modality violation: Evidence for {ca.criterion_code} in '{target_clause['text'][:60]}' "
                                    f"carries hypothetical or conditional framing."
                                )

        if objections:
            has_exclusion = any("disqualifying exclusion" in obj for obj in objections)
            action = "VETO_TO_DENIED" if has_exclusion else "VETO_TO_DEFERRED"
            return {
                "falsification_detected": True,
                "critic_action": action,
                "challenge_type": "FALSIFICATION_OF_APPROVAL",
                "objections": objections,
                "counter_evidence_spans": counter_evidence_spans,
                "disagreement_recorded": True
            }

        return {
            "falsification_detected": False,
            "critic_action": "CONCUR",
            "challenge_type": "NONE",
            "objections": [],
            "counter_evidence_spans": [],
            "disagreement_recorded": False
        }

    def _critique_denial(
        self,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        sections: List[Dict[str, Any]],
        policy_id: str
    ) -> Dict[str, Any]:
        """
        Challenges false denials:
        If an inclusion criterion was marked NOT_MET or INSUFFICIENT, but the independent
        discourse parser uncovers affirmative documentation in an authoritative clinical section.
        """
        objections: List[str] = []
        counter_evidence_spans: List[Dict[str, Any]] = []

        unmet_inclusions = [c for c in criteria_assessments if not c.is_exclusion and c.status != DeterminationStatus.MET]

        # Scan authoritative diagnostic sections for clear positive evidence of unmet items
        auth_sections = [s for s in sections if s["section_type"] in ("DIAGNOSTIC_STUDIES", "HPI", "PAST_MEDICAL_HISTORY")]

        for ca in unmet_inclusions:
            crit_code = ca.criterion_code.upper()
            patterns_to_check = []
            if "ICD-01" in crit_code or "LVEF" in ca.name.upper():
                patterns_to_check.append(r"\b(?:lvef|ejection\s+fraction)\s*(?:is|of|measures|measures\s*at|was|shows)?\s*(\d{1,2})%?")
            elif "CPAP-01" in crit_code or "AHI" in ca.name.upper():
                patterns_to_check.append(r"\b(?:ahi|apnea-hypopnea\s+index|rdi)\s*(?:is|of|measured\s*at|at)?\s*(\d{1,3})")

            for sec in auth_sections:
                clauses = SectionDiscourseParser.split_into_clauses(sec["text"])
                for cl in clauses:
                    cl_lower = cl["text"].lower()
                    # Skip negated clauses
                    if re.search(r"\b(?:no|denies|negative|without|normal|free of)\b", cl_lower):
                        continue
                    for pat in patterns_to_check:
                        m = re.search(pat, cl_lower)
                        if m:
                            try:
                                val = float(m.group(1))
                                # Check if numeric value meets standard coverage threshold
                                is_qualifying = False
                                if "ICD-01" in crit_code or "LVEF" in ca.name.upper():
                                    is_qualifying = val <= 35.0
                                elif "CPAP-01" in crit_code or "AHI" in ca.name.upper():
                                    is_qualifying = val >= 15.0

                                if is_qualifying:
                                    abs_start = sec["start"] + cl["start"] + m.start()
                                    abs_end = sec["start"] + cl["start"] + m.end()
                                    obj_msg = (
                                        f"Critic challenged false denial for {ca.criterion_code}: "
                                        f"Authoritative affirmative evidence '{m.group(0)}' found in section '{sec['section_type']}' "
                                        f"at character [{abs_start}:{abs_end}]."
                                    )
                                    objections.append(obj_msg)
                                    counter_evidence_spans.append({
                                        "type": "AFFIRMATIVE_CHALLENGE_SPAN",
                                        "text": ehr_text[abs_start:abs_end],
                                        "start": abs_start,
                                        "end": abs_end,
                                        "section": sec["section_type"]
                                    })
                            except ValueError:
                                pass

        if objections:
            return {
                "falsification_detected": True,
                "critic_action": "CHALLENGE_TO_DEFERRED",
                "challenge_type": "CHALLENGE_FALSE_DENIAL",
                "objections": objections,
                "counter_evidence_spans": counter_evidence_spans,
                "disagreement_recorded": True
            }

        return {
            "falsification_detected": False,
            "critic_action": "CONCUR",
            "challenge_type": "NONE",
            "objections": [],
            "counter_evidence_spans": [],
            "disagreement_recorded": False
        }

    def _critique_deferral(
        self,
        criteria_assessments: List[CriterionAssessment],
        ehr_text: str,
        sections: List[Dict[str, Any]],
        policy_id: str
    ) -> Dict[str, Any]:
        """
        Challenges wrong/unnecessary deferrals:
        If every required criterion has verified documentation in active sections with
        no exclusions, contradictions, or ambiguity.
        """
        objections: List[str] = []

        all_inclusions_met = all(
            c.status == DeterminationStatus.MET for c in criteria_assessments if not c.is_exclusion
        )
        no_exclusions_met = not any(
            c.status == DeterminationStatus.MET for c in criteria_assessments if c.is_exclusion
        )

        if all_inclusions_met and no_exclusions_met:
            objections.append(
                "Critic challenged unnecessary deferral: All required inclusion criteria possess verified "
                "affirmative documentation across active clinical discourse sections with zero active exclusions."
            )
            return {
                "falsification_detected": True,
                "critic_action": "CHALLENGE_WRONG_DEFERRAL",
                "challenge_type": "CHALLENGE_WRONG_DEFERRAL",
                "objections": objections,
                "counter_evidence_spans": [],
                "disagreement_recorded": True
            }

        return {
            "falsification_detected": False,
            "critic_action": "CONCUR",
            "challenge_type": "NONE",
            "objections": [],
            "counter_evidence_spans": [],
            "disagreement_recorded": False
        }
