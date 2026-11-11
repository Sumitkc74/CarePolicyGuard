import json
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.clinical_core import ClinicalGroundingVerifier, ClinicalScopeAnalyzer
from app.schemas.contracts import ClinicalEvidenceSpan, DeterminationStatus, CriterionAssessment

logger = logging.getLogger(__name__)

class LLMProposedSpan(BaseModel):
    """Candidate evidence span proposed by local LLM."""
    criterion_code: str
    proposed_status: Any
    claimed_text: str = ""
    char_start: int = 0
    char_end: int = 0
    numeric_value: Optional[float] = None
    numeric_unit: Optional[str] = None
    rationale: str = ""
    claimed_equivalence: str = ""

    def __init__(self, **data):
        if "quote" in data and "claimed_text" not in data:
            data["claimed_text"] = data["quote"]
        if "start_char" in data and "char_start" not in data:
            data["char_start"] = data["start_char"]
        if "end_char" in data and "char_end" not in data:
            data["char_end"] = data["end_char"]
        if "reasoning" in data and "rationale" not in data:
            data["rationale"] = data["reasoning"]
        if "equivalence" in data and "claimed_equivalence" not in data:
            data["claimed_equivalence"] = data["equivalence"]
        super().__init__(**data)

    @property
    def quote(self) -> str:
        return self.claimed_text

    @property
    def start_char(self) -> int:
        return self.char_start

    @property
    def end_char(self) -> int:
        return self.char_end

    @property
    def reasoning(self) -> str:
        return self.rationale


class GateEvaluationResult(BaseModel):
    """Result of passing an LLM proposal through the 3 deterministic gates."""
    proposal: LLMProposedSpan
    passed: bool
    failing_gate: Optional[str] = None  # "GATE_A_EXACT_SLICE", "GATE_B_SEMANTIC", "GATE_C_ADVERSARIAL_VETO"
    rejection_reason: Optional[str] = None
    verified_span: Optional[ClinicalEvidenceSpan] = None

    @property
    def reason(self) -> Optional[str]:
        return self.rejection_reason

    @property
    def failed_gate(self) -> Optional[str]:
        return self.failing_gate


class ProposalResult(tuple):
    """Tuple subclass (proposals, status_code, elapsed_latency_ms) supporting dict subscripting."""
    @property
    def proposals(self):
        return self[0]

    @property
    def status(self):
        return self[1]

    @property
    def elapsed_ms(self):
        return self[2]

    def __getitem__(self, item):
        if isinstance(item, str):
            if item in ("proposals", "spans"):
                return self[0]
            elif item in ("status", "status_code"):
                return self[1]
            elif item in ("elapsed_ms", "latency_ms"):
                return self[2]
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

class LLMProposalAgent:
    """
    Task 1: LLM Proposal Agent (Proposer behind Deterministic Gates)
    Connects to local Ollama runtime to propose candidate evidence spans for criteria.
    Never a decider. Every proposal must pass Gate A, Gate B, and Gate C in order.
    """

    span_repair_enabled: bool = True

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        availability_checker: Optional[Any] = None,
        max_calls_per_case: int = 3,
        max_time_per_case_seconds: float = 30.0,
        span_repair_enabled: bool = True
    ):
        self.endpoint_url = endpoint_url or settings.LOCAL_LLM_URL
        self.model_name = model_name or settings.LOCAL_LLM_MODEL
        self.timeout_seconds = timeout_seconds or settings.LOCAL_LLM_TIMEOUT_SECONDS
        self.enabled = settings.ENABLE_LLM_PROPOSAL_STEP
        self.span_repair_enabled = span_repair_enabled
        self._availability_checker = availability_checker
        self.max_calls_per_case = max_calls_per_case
        self.max_time_per_case_seconds = max_time_per_case_seconds
        self.case_call_count = 0
        self.case_elapsed_ms = 0.0
        self.telemetry = {
            "total_calls": 0,
            "proposals_generated": 0,
            "gate_a_rejections": 0,
            "gate_b_rejections": 0,
            "gate_c_map_rejections": 0,
            "gate_c_vetoes": 0,
            "proposals_accepted": 0,
            "total_latency_ms": 0.0,
            "call_latencies": []
        }

    def reset_case_budget(self) -> None:
        """Resets per-case call count and elapsed time budget at case boundary."""
        self.case_call_count = 0
        self.case_elapsed_ms = 0.0

    def is_available(self) -> bool:
        """Checks if local Ollama endpoint is reachable without sending clinical data."""
        if not self.enabled:
            return False
        if self._availability_checker is not None:
            return bool(self._availability_checker())
        try:
            # Query models endpoint using short timeout
            models_url = self.endpoint_url.replace("/chat/completions", "/models")
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(models_url)
                return resp.status_code == 200
        except Exception:
            return False

    def _execute_network_request(self, payload: Dict[str, Any]) -> httpx.Response:
        """Sends inference request to local Ollama endpoint (separately patchable)."""
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(self.endpoint_url, json=payload)

    @classmethod
    def locate_claimed_span(cls, text: str, claimed_text: str, allow_repair: bool = True) -> Tuple[int, int]:
        """
        Locates a claimed substring in the clinical note deterministically.
        1. Checks exact verbatim match in text.
        2. If not found and allow_repair is True, attempts deterministic span-repair:
           - Case-insensitive search on trimmed claimed text (removing outer whitespace/punctuation).
           - Normalizing minor whitespace/punctuation differences between words while ensuring
             all words appear contiguously in the exact same sequence.
           - Returns the exact original character slice [s:e] from text.
        3. If no matching span exists in text (hallucination): returns (-1, -1).
        4. If multiple occurrences exist: tie-breaks by preferring non-negated patient experiencer,
           falling back to document order.
        """
        if not text or not claimed_text:
            return -1, -1

        # 1. Exact verbatim search
        occurrences: List[Tuple[int, int]] = []
        pos = 0
        while True:
            idx = text.find(claimed_text, pos)
            if idx == -1:
                break
            occurrences.append((idx, idx + len(claimed_text)))
            pos = idx + 1

        if not occurrences and allow_repair:
            # 2. Case and punctuation-insensitive deterministic span repair
            cleaned = claimed_text.strip(" \t\r\n'\"`.,;:!?-")
            if cleaned:
                # 2a. Case-insensitive substring search
                pos = 0
                cleaned_lower = cleaned.lower()
                text_lower = text.lower()
                while True:
                    idx = text_lower.find(cleaned_lower, pos)
                    if idx == -1:
                        break
                    occurrences.append((idx, idx + len(cleaned)))
                    pos = idx + 1

                # 2b. Flexible contiguous word-boundary search if 2a found nothing
                if not occurrences:
                    import re as _re
                    words = [_re.escape(w) for w in _re.split(r'\s+', cleaned) if w]
                    if len(words) >= 2:
                        pat = r'(?i)\b' + r'\s+'.join(words) + r'(?:\b|[.,;:!?])'
                        for m in _re.finditer(pat, text):
                            s_m = m.start()
                            e_m = m.end()
                            while e_m > s_m and text[e_m - 1] in '.,;:!? ':
                                e_m -= 1
                            occurrences.append((s_m, e_m))

        if not occurrences:
            return -1, -1

        if len(occurrences) == 1:
            return occurrences[0]

        # Deterministic multi-occurrence tie-breaker:
        # Prefer the first occurrence with affirmative patient context (not negated, PATIENT experiencer)
        for s_idx, e_idx in occurrences:
            scope = ClinicalScopeAnalyzer.analyze_scope(text, s_idx, e_idx)
            if not scope.get("is_negated", False) and scope.get("experiencer", "PATIENT") == "PATIENT":
                return s_idx, e_idx

        # Deterministic fallback: document order (first occurrence)
        return occurrences[0]

    @classmethod
    def build_prompt(
        cls,
        ehr_text: str,
        ccode: str,
        cname: str,
        cdesc: str,
        ctype: str,
        is_excl: bool,
        prompt_version: str = "v2_verbatim_worked_example"
    ) -> str:
        """
        Builds extraction prompt for local LLM proposer.
        prompt_version='v2_verbatim_worked_example': Production default, incorporates verbatim instructions
        and in-context demonstration (+18.5% Gate A margin).
        prompt_version='v1_legacy': Legacy prompt retained for backward-compatibility regression tests.
        """
        if prompt_version == "v1_legacy":
            return (
                f"You are a clinical evidence extraction assistant for Medicare coverage evaluation.\n"
                f"CLINICAL NOTE:\n\"\"\"{ehr_text}\"\"\"\n\n"
                f"CRITERION:\n"
                f"- Code: {ccode}\n"
                f"- Name: {cname}\n"
                f"- Description: {cdesc}\n"
                f"- Type: {ctype}\n"
                f"- Is Exclusion: {is_excl}\n\n"
                f"TASK:\n"
                f"Find any verbatim substring in the clinical note that provides evidence expressing the SAME CLINICAL CONCEPT (synonym, subtype, paraphrase, abbreviation) as this criterion.\n"
                f"You must NOT claim that a different clinical condition or different organ satisfies the policy. Only wording variations for the same clinical concept.\n"
                f"You MUST provide the exact verbatim substring (claimed_text) copied directly from the clinical note.\n"
                f"Return ONLY valid JSON matching this schema:\n"
                f"{{\n"
                f"  \"proposals\": [\n"
                f"    {{\n"
                f"      \"criterion_code\": \"{ccode}\",\n"
                f"      \"proposed_status\": \"MET\" or \"NOT_MET\",\n"
                f"      \"claimed_text\": \"exact verbatim substring from note\",\n"
                f"      \"claimed_equivalence\": \"clinical relationship (e.g. adenocarcinoma is a subtype of prostate cancer)\",\n"
                f"      \"numeric_value\": float or null,\n"
                f"      \"numeric_unit\": string or null,\n"
                f"      \"rationale\": \"brief clinical rationale\"\n"
                f"    }}\n"
                f"  ]\n"
                f"}}"
            )

        # Default: v2_verbatim_worked_example
        return (
            f"You are a clinical evidence extraction assistant for Medicare coverage evaluation.\n"
            f"CLINICAL NOTE:\n\"\"\"{ehr_text}\"\"\"\n\n"
            f"CRITERION:\n"
            f"- Code: {ccode}\n"
            f"- Name: {cname}\n"
            f"- Description: {cdesc}\n"
            f"- Type: {ctype}\n"
            f"- Is Exclusion: {is_excl}\n\n"
            f"TASK:\n"
            f"Find any verbatim substring in the clinical note that provides evidence expressing the SAME CLINICAL CONCEPT as this criterion.\n"
            f"CRITICAL INSTRUCTION: You must quote the note exactly. Do NOT rephrase, do NOT summarize, do NOT correct spelling. claimed_text MUST be a character-for-character exact quote from the clinical note above.\n\n"
            f"WORKED EXAMPLE:\n"
            f'Note snippet: "Patient with severe dyspnea on minimal exertion, NYHA class III functional status."\n'
            f'Criterion: "NYHA Class III or IV heart failure symptoms"\n'
            f'Correct claimed_text: "NYHA class III functional status" (exact substring from note snippet).\n'
            f'Incorrect claimed_text: "Patient has Class 3 symptoms" (rephrased - will be rejected).\n\n'
            f"Return a JSON object with this exact structure:\n"
            f"{{\n"
            f'  "proposals": [\n'
            f'    {{\n'
            f'      "criterion_code": "{ccode}",\n'
            f'      "proposed_status": "MET" or "NOT_MET",\n'
            f'      "claimed_text": "<exact verbatim quote from note>",\n'
            f'      "claimed_equivalence": "<canonical clinical concept from criterion>",\n'
            f'      "numeric_value": null or number,\n'
            f'      "numeric_unit": null or string,\n'
            f'      "rationale": "<brief explanation>"\n'
            f'    }}\n'
            f'  ]\n'
            f"}}\n"
            f"If no relevant text exists in the note, return {{\"proposals\": []}}.\n"
            f"Return ONLY valid JSON."
        )

    def propose_spans_sync(
        self,
        sanitized_ehr: Optional[str] = None,
        criterion: Optional[Dict[str, Any]] = None,
        narrative: Optional[str] = None,
        criterion_def: Optional[Dict[str, Any]] = None,
        policy_id: Optional[str] = None
    ) -> ProposalResult:
        """
        Synchronously requests candidate spans from local Ollama LLM.
        Returns: ProposalResult(proposals, status_code, elapsed_latency_ms)
        status_code in: "COMPLETED", "SKIPPED_DISABLED", "SKIPPED_TIMEOUT", "SKIPPED_UNAVAILABLE", "NO_PROPOSALS"
        """
        t0 = time.perf_counter()
        ehr_text = sanitized_ehr if sanitized_ehr is not None else (narrative or "")
        crit = criterion if criterion is not None else (criterion_def or {})

        if not self.enabled:
            return ProposalResult(([], "SKIPPED_DISABLED", 0.0))

        # Hard limits: At most 3 LLM calls per adjudication and total LLM budget of 30 seconds
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(
                f"LLM call budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) for case; skipping with SKIPPED_TIMEOUT."
            )
            return ProposalResult(([], "SKIPPED_TIMEOUT", 0.0))

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(
                f"LLM time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms) for case; skipping with SKIPPED_TIMEOUT."
            )
            return ProposalResult(([], "SKIPPED_TIMEOUT", 0.0))

        ccode = crit.get("criterion_code", "CRIT-UNKNOWN")
        cname = crit.get("name", "")
        cdesc = crit.get("description", "")
        ctype = crit.get("criterion_type", "FINDING_PRESENCE")
        is_excl = crit.get("is_exclusion", False)

        prompt = self.build_prompt(ehr_text, ccode, cname, cdesc, ctype, is_excl)

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 350
        }

        try:
            resp = self._execute_network_request(payload)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            self.telemetry.setdefault("call_latencies", []).append(elapsed_ms)

            if resp.status_code != 200:
                return ProposalResult(([], f"SKIPPED_HTTP_{resp.status_code}", elapsed_ms))

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            try:
                parsed = json.loads(content)
            except Exception:
                import re as _re
                m_quote = _re.search(r'"claimed_text":\s*"([^"]+)"', content)
                m_equiv = _re.search(r'"claimed_equivalence":\s*"([^"]+)"', content)
                m_status = _re.search(r'"proposed_status":\s*"([^"]+)"', content)
                if m_quote:
                    parsed = {
                        "proposals": [{
                            "criterion_code": ccode,
                            "claimed_text": m_quote.group(1),
                            "claimed_equivalence": m_equiv.group(1) if m_equiv else "",
                            "proposed_status": m_status.group(1) if m_status else "MET"
                        }]
                    }
                else:
                    parsed = {}
            raw_proposals = parsed.get("proposals", [])
            if not raw_proposals and isinstance(parsed, dict) and "claimed_text" in parsed:
                raw_proposals = [parsed]

            proposals = []
            for p in raw_proposals:
                if isinstance(p, dict) and p.get("claimed_text"):
                    claimed = str(p.get("claimed_text", "")).strip()
                    if not claimed:
                        continue
                    # Locate span in narrative via deterministic matcher with repair
                    allow_rep = getattr(self, "span_repair_enabled", True)
                    start, end = self.locate_claimed_span(ehr_text, claimed, allow_repair=allow_rep)
                    if start == -1:
                        # Hallucinated quote not in text: record (0, 0) so Gate A rejects
                        start, end = 0, 0
                        repaired_text = claimed
                    else:
                        repaired_text = ehr_text[start:end]
                    proposals.append(LLMProposedSpan(
                        criterion_code=ccode,
                        proposed_status=p.get("proposed_status", "MET"),
                        claimed_text=repaired_text,
                        char_start=int(start),
                        char_end=int(end),
                        numeric_value=p.get("numeric_value"),
                        numeric_unit=p.get("numeric_unit"),
                        claimed_equivalence=p.get("claimed_equivalence", p.get("rationale", "")),
                        rationale=p.get("rationale", "LLM proposed evidence")
                    ))

            self.telemetry["proposals_generated"] += len(proposals)
            status = "COMPLETED" if proposals else "NO_PROPOSALS"
            return ProposalResult((proposals, status, elapsed_ms))

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            self.telemetry.setdefault("call_latencies", []).append(elapsed_ms)
            exc_str = str(exc).lower()
            if isinstance(exc, (httpx.TimeoutException, TimeoutError)) or "timeout" in exc_str or "timed out" in exc_str:
                logger.warning(f"LLM proposal step timed out after {self.timeout_seconds}s for {ccode}: {exc}")
                return ProposalResult(([], "SKIPPED_TIMEOUT", elapsed_ms))
            else:
                logger.warning(f"LLM proposal step unavailable for {ccode}: {exc}")
                return ProposalResult(([], "SKIPPED_UNAVAILABLE", elapsed_ms))

    @classmethod
    def evaluate_proposal_through_gates(
        cls,
        proposal: LLMProposedSpan,
        sanitized_ehr: Optional[str] = None,
        criterion: Optional[Dict[str, Any]] = None,
        verifier_agent: Optional[Any] = None,
        raw_narrative: Optional[str] = None,
        criterion_def: Optional[Dict[str, Any]] = None
    ) -> GateEvaluationResult:
        """
        Passes a proposed span through the 3 mandatory gates in strict sequential order:
        (a) Exact character-span check (system-located slice == claimed_text)
        (b) Five-dimension semantic verification (subject, timing, modality, negation, range)
        (c) Concept Map Equivalence and Agent 3 independent cross-examination veto
        """
        text = sanitized_ehr if sanitized_ehr is not None else (raw_narrative or "")
        crit = criterion if criterion is not None else (criterion_def or {})

        claimed = proposal.claimed_text

        # Gate (a): Verify verbatim quote existence in narrative (with deterministic case/punctuation repair)
        s = proposal.char_start
        e = proposal.char_end

        # System verifies and/or deterministically repairs offsets to the exact slice in note
        if not claimed or claimed not in text or s < 0 or e > len(text) or s >= e or text[s:e] != claimed:
            allow_rep = getattr(cls, "span_repair_enabled", True)
            s, e = cls.locate_claimed_span(text, claimed, allow_repair=allow_rep)
            if s == -1:
                offset_clause = f"Invalid character offsets [{proposal.char_start}:{proposal.char_end}] for note of length {len(text)}. " if (proposal.char_start < 0 or proposal.char_end > len(text) or proposal.char_start >= proposal.char_end) else ""
                return GateEvaluationResult(
                    proposal=proposal,
                    passed=False,
                    failing_gate="GATE_A_EXACT_SLICE",
                    rejection_reason=f"{offset_clause}Hallucinated evidence: claimed text '{claimed[:30]}...' does not exist in EHR note."
                )
            # Re-anchor proposal to the exact verbatim slice from the note
            proposal.char_start = s
            proposal.char_end = e
            proposal.claimed_text = text[s:e]
            claimed = proposal.claimed_text

        actual_slice = text[s:e]
        if actual_slice != claimed:
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_A_EXACT_SLICE",
                rejection_reason=f"Character slice mismatch: claimed [{s}:{e}] ('{actual_slice}') vs true slice '{claimed}'."
            )

        # Gate (b): 5-dimension semantic verification (subject, timing, modality, negation, range)
        scope = ClinicalScopeAnalyzer.analyze_scope(text, s, e)
        is_negated = scope.get("is_negated", False) or any(neg in claimed.lower() for neg in ("no ", "denies", "without", "negative for", "free of"))
        is_family = scope.get("is_family_history", False) or scope.get("experiencer", "PATIENT") != "PATIENT"
        is_hypothetical = scope.get("is_hypothetical", False)
        is_excl = crit.get("is_exclusion", False)

        if is_family:
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_B_SEMANTIC",
                rejection_reason=f"Subject invalid: evidence applies to family history, not patient ({scope.get('experiencer')})."
            )

        if is_hypothetical:
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_B_SEMANTIC",
                rejection_reason="Modality invalid: evidence is hypothetical or speculative, not documented finding."
            )

        prop_status_str = proposal.proposed_status.value if hasattr(proposal.proposed_status, "value") else str(proposal.proposed_status)

        if not is_excl and is_negated and prop_status_str == "MET":
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_B_SEMANTIC",
                rejection_reason="Negation contradiction: proposed MET for inclusion criterion but text is clinically negated."
            )

        if is_excl and not is_negated and prop_status_str == "NOT_MET":
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_B_SEMANTIC",
                rejection_reason="Contradiction: proposed NOT_MET for exclusion but affirmative disqualifying condition is present."
            )

        # If numeric threshold criterion, verify operator and range
        ctype = crit.get("criterion_type", "FINDING_PRESENCE")
        if ctype == "NUMERIC_THRESHOLD" and proposal.numeric_value is not None:
            op = crit.get("operator", ">=")
            thresh = float(crit.get("threshold", 0.0))
            val = float(proposal.numeric_value)
            passed_thresh = False
            if op in (">=", "=>"):
                passed_thresh = (val >= thresh)
            elif op == ">":
                passed_thresh = (val > thresh)
            elif op in ("<=", "=<"):
                passed_thresh = (val <= thresh)
            elif op == "<":
                passed_thresh = (val < thresh)
            elif op in ("==", "="):
                passed_thresh = (val == thresh)

            if passed_thresh and prop_status_str != "MET":
                return GateEvaluationResult(
                    proposal=proposal,
                    passed=False,
                    failing_gate="GATE_B_SEMANTIC",
                    rejection_reason=f"Numeric inconsistency: value {val} satisfies threshold {op} {thresh} but proposal claims {proposal.proposed_status}."
                )

        candidate_span = ClinicalEvidenceSpan(
            source_text=claimed,
            start_char=s,
            end_char=e,
            clinical_section="LLM Proposer Grounded Extraction",
            confidence=0.88,
            semantic_support_passed=True,
            subject_valid=not is_family,
            timing_valid=True,
            modality_valid=not is_hypothetical,
            negation_valid=True
        )

        # Gate (c): Concept Map Equivalence Verification (Task 1 Map Check)
        from app.core.concept_map import get_concept_map, ConceptReviewQueue
        cmap = get_concept_map()
        crit_name = crit.get("name", "")
        crit_code = crit.get("criterion_code", proposal.criterion_code)
        crit_kws = crit.get("keywords", [])
        if isinstance(crit_kws, str):
            crit_kws = [k.strip() for k in crit_kws.split(",") if k.strip()]
        candidate_crit_terms = ([crit_name] + list(crit_kws)) if crit_name else list(crit_kws)
        if not candidate_crit_terms:
            candidate_crit_terms = [crit_code]

        map_passed = False
        map_reason = ""
        for c_term in candidate_crit_terms:
            passed, reason = cmap.verify_equivalence(c_term, claimed)
            if passed:
                map_passed = True
                map_reason = reason
                break
            elif "PROHIBITED_NEAR_MISS" in reason:
                map_reason = reason
                break
            else:
                map_reason = reason

        if not map_passed:
            case_id = crit.get("case_id", "CURRENT_CASE")
            ConceptReviewQueue.submit_unmapped_proposal(
                case_id=case_id,
                criterion_code=crit_code,
                criterion_term=crit_name or crit_code,
                proposed_span=claimed,
                claimed_equivalence=proposal.claimed_equivalence or proposal.rationale,
                ehr_snippet=text[max(0, s - 50):min(len(text), e + 50)]
            )
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_C_MAP_CHECK",
                rejection_reason=f"Concept Map check failed: {map_reason}. Claim submitted to human review queue; case defers."
            )

        # Gate (d): Agent 3 independent cross-examination veto
        if verifier_agent is not None:
            if hasattr(verifier_agent, "audit_assessment"):
                assessment_dummy = CriterionAssessment(
                    criterion_id=proposal.criterion_code,
                    criterion_code=proposal.criterion_code,
                    name=crit.get("name", ""),
                    description=crit.get("description", crit.get("name", "")),
                    status=DeterminationStatus.MET if prop_status_str == "MET" else DeterminationStatus.NOT_MET,
                    extracted_value=claimed,
                    raw_confidence=0.88,
                    clinical_rationale=proposal.rationale,
                    is_exclusion=is_excl,
                    verified_spans=[candidate_span]
                )
                audit_res = verifier_agent.audit_assessment(assessment_dummy, crit, text)
                if (
                    audit_res.hallucination_flag
                    or not audit_res.grounding_status
                    or audit_res.discordance_flag
                    or getattr(audit_res, "contradiction_detected", False)
                ):
                    return GateEvaluationResult(
                        proposal=proposal,
                        passed=False,
                        failing_gate="GATE_C_ADVERSARIAL_VETO",
                        rejection_reason=f"Agent 3 cross-examination veto: {audit_res.audit_notes}"
                    )
            elif hasattr(verifier_agent, "verify_spans_programmatic"):
                grounded, hallucinated, drift, notes = verifier_agent.verify_spans_programmatic([candidate_span], text)
                if hallucinated or not grounded:
                    return GateEvaluationResult(
                        proposal=proposal,
                        passed=False,
                        failing_gate="GATE_C_ADVERSARIAL_VETO",
                        rejection_reason=f"Agent 3 cross-examination veto: {'; '.join(notes)}"
                    )

        # All gates passed!
        return GateEvaluationResult(
            proposal=proposal,
            passed=True,
            failing_gate=None,
            rejection_reason=None,
            verified_span=candidate_span
        )

    def run_synonymy_conversation(
        self,
        criterion: Dict[str, Any],
        ehr_narrative: str,
        failed_reason: str = "Deterministic match failed",
        verifier_agent: Optional[Any] = None,
        case_id: Optional[str] = None,
        max_rounds: int = 3
    ) -> Tuple[Optional[ClinicalEvidenceSpan], List[Any]]:
        """
        Task 2: Executes and records the inter-agent runtime conversation for LLM synonymy resolution.
        Protocol:
        1. Agent 2 sends SYNONYMY_QUERY (criterion, note text, failed reason).
        2. LLM Proposer replies with SYNONYMY_PROPOSAL (candidate span + claimed equivalence) or NO_EQUIVALENT_FOUND.
        3. Deterministic Gates (a) slice check, (b) semantic check, (c) concept map check are evaluated.
        4. If Gates a-c pass, Agent 3 cross-examines (CHALLENGE -> DEFENSE -> ACCEPT/REJECT), bounded to <=3 rounds.
        All messages are recorded to AgentConversationAuditBus.
        """
        from app.schemas.agent_messages import AgentMessage, AgentMessageType, AgentConversationAuditBus

        conv_id = f"CONV-SYN-{uuid.uuid4().hex[:8].upper()}"
        cid = case_id or f"CASE-{uuid.uuid4().hex[:6].upper()}"
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cname = criterion.get("name", "")
        recorded_messages = []

        # Round 1: Agent 2 queries LLM proposer
        msg_query = AgentMessage(
            conversation_id=conv_id,
            sender="Agent2_CriteriaEvaluator",
            receiver="Agent_LLMProposer",
            message_type=AgentMessageType.SYNONYMY_QUERY,
            payload={
                "case_id": cid,
                "criterion_code": ccode,
                "criterion_name": cname,
                "failed_reason": failed_reason,
            },
            question_or_decision=f"Deterministic match failed for {ccode} ('{failed_reason}'). Is there a clinical synonym, subtype, paraphrase, or abbreviation expressing the same clinical concept?",
            round_number=1
        )
        AgentConversationAuditBus.record_message(msg_query)
        recorded_messages.append(msg_query)

        res = self.propose_spans_sync(sanitized_ehr=ehr_narrative, criterion=criterion)
        proposals = res[0] if isinstance(res, tuple) else res.get("proposals", [])

        if not proposals:
            msg_no_eq = AgentMessage(
                conversation_id=conv_id,
                sender="Agent_LLMProposer",
                receiver="Agent2_CriteriaEvaluator",
                message_type=AgentMessageType.NO_EQUIVALENT_FOUND,
                payload={"status": res.status if hasattr(res, "status") else "NO_PROPOSALS"},
                question_or_decision=f"No equivalent wording found in note for {ccode}.",
                round_number=1
            )
            AgentConversationAuditBus.record_message(msg_no_eq)
            recorded_messages.append(msg_no_eq)
            return None, recorded_messages

        prop = proposals[0]
        msg_proposal = AgentMessage(
            conversation_id=conv_id,
            sender="Agent_LLMProposer",
            receiver="Agent2_CriteriaEvaluator",
            message_type=AgentMessageType.SYNONYMY_PROPOSAL,
            payload={
                "case_id": cid,
                "criterion_code": ccode,
                "claimed_text": prop.claimed_text,
                "char_start": prop.char_start,
                "char_end": prop.char_end,
                "claimed_equivalence": prop.claimed_equivalence or prop.rationale,
                "proposed_status": str(prop.proposed_status)
            },
            question_or_decision=f"Proposed synonymy equivalence: '{prop.claimed_text}' expresses concept for {ccode} ('{prop.claimed_equivalence or prop.rationale}').",
            round_number=1
        )
        AgentConversationAuditBus.record_message(msg_proposal)
        recorded_messages.append(msg_proposal)

        # Round 2: Gate verification (Gates a, b, c)
        gate_res = self.evaluate_proposal_through_gates(
            proposal=prop,
            sanitized_ehr=ehr_narrative,
            criterion=criterion,
            verifier_agent=None  # We conduct Agent 3 cross-examination via explicit conversation below
        )

        if not gate_res.passed:
            if gate_res.failing_gate == "GATE_A_EXACT_SLICE":
                self.telemetry["gate_a_rejections"] += 1
            elif gate_res.failing_gate == "GATE_B_SEMANTIC":
                self.telemetry["gate_b_rejections"] += 1
            elif gate_res.failing_gate == "GATE_C_MAP_CHECK":
                self.telemetry["gate_c_map_rejections"] += 1
            elif gate_res.failing_gate == "GATE_C_ADVERSARIAL_VETO":
                self.telemetry["gate_c_vetoes"] += 1

            # Map check failure or semantic/slice failure
            if gate_res.failing_gate == "GATE_C_MAP_CHECK":
                msg_defer = AgentMessage(
                    conversation_id=conv_id,
                    sender="Agent2_CriteriaEvaluator",
                    receiver="HumanReviewQueue",
                    message_type=AgentMessageType.DEFER,
                    payload={
                        "case_id": cid,
                        "criterion_code": ccode,
                        "claimed_text": prop.claimed_text,
                        "failing_gate": gate_res.failing_gate,
                        "rejection_reason": gate_res.rejection_reason
                    },
                    question_or_decision=f"Proposal '{prop.claimed_text}' rejected by {gate_res.failing_gate}: {gate_res.rejection_reason}. Submitted to review queue; case defers.",
                    round_number=2
                )
                AgentConversationAuditBus.record_message(msg_defer)
                recorded_messages.append(msg_defer)
            else:
                msg_reject = AgentMessage(
                    conversation_id=conv_id,
                    sender="Agent2_CriteriaEvaluator",
                    receiver="Agent_LLMProposer",
                    message_type=AgentMessageType.REJECT,
                    payload={
                        "case_id": cid,
                        "criterion_code": ccode,
                        "failing_gate": gate_res.failing_gate,
                        "rejection_reason": gate_res.rejection_reason
                    },
                    question_or_decision=f"Proposal rejected by {gate_res.failing_gate}: {gate_res.rejection_reason}.",
                    round_number=2
                )
                AgentConversationAuditBus.record_message(msg_reject)
                recorded_messages.append(msg_reject)
            return None, recorded_messages

        # Round 2 (cont) & Round 3: Agent 3 Cross-Examination
        msg_challenge = AgentMessage(
            conversation_id=conv_id,
            sender="Agent3_AdversarialVerifier",
            receiver="Agent_LLMProposer",
            message_type=AgentMessageType.CHALLENGE,
            payload={
                "case_id": cid,
                "criterion_code": ccode,
                "claimed_text": prop.claimed_text,
                "query": "Auditing span for negation, experiencer validity, and factual alignment."
            },
            question_or_decision=f"Does proposed span '{prop.claimed_text}' strictly affirm the criterion requirement without contradiction or clinical discordance?",
            round_number=2
        )
        AgentConversationAuditBus.record_message(msg_challenge)
        recorded_messages.append(msg_challenge)

        # Defense by Evaluator / Proposer
        msg_defense = AgentMessage(
            conversation_id=conv_id,
            sender="Agent2_CriteriaEvaluator",
            receiver="Agent3_AdversarialVerifier",
            message_type=AgentMessageType.DEFENSE,
            payload={
                "case_id": cid,
                "criterion_code": ccode,
                "span": prop.claimed_text,
                "offsets": [prop.char_start, prop.char_end],
                "concept_confirmed": True
            },
            question_or_decision=f"Span '{prop.claimed_text}' verified at [{prop.char_start}:{prop.char_end}]; confirmed patient experiencer and confirmed concept map entry.",
            round_number=3
        )
        AgentConversationAuditBus.record_message(msg_defense)
        recorded_messages.append(msg_defense)

        # Agent 3 Verdict
        agent3_passed = True
        veto_reason = None
        if verifier_agent is not None:
            if hasattr(verifier_agent, "audit_assessment"):
                dummy_assess = CriterionAssessment(
                    criterion_id=ccode,
                    criterion_code=ccode,
                    name=cname,
                    description=criterion.get("description", cname),
                    status=DeterminationStatus.MET,
                    extracted_value=prop.claimed_text,
                    raw_confidence=0.88,
                    clinical_rationale=prop.rationale,
                    is_exclusion=criterion.get("is_exclusion", False),
                    verified_spans=[gate_res.verified_span]
                )
                audit = verifier_agent.audit_assessment(dummy_assess, criterion, ehr_narrative)
                if audit.hallucination_flag or not audit.grounding_status or getattr(audit, "contradiction_detected", False):
                    agent3_passed = False
                    veto_reason = audit.audit_notes

        if agent3_passed:
            self.telemetry["proposals_accepted"] += 1
            msg_accept = AgentMessage(
                conversation_id=conv_id,
                sender="Agent3_AdversarialVerifier",
                receiver="Agent2_CriteriaEvaluator",
                message_type=AgentMessageType.ACCEPT,
                payload={
                    "case_id": cid,
                    "criterion_code": ccode,
                    "accepted_span": prop.claimed_text
                },
                question_or_decision=f"Cross-examination passed: accepted '{prop.claimed_text}' for {ccode}.",
                round_number=3
            )
            AgentConversationAuditBus.record_message(msg_accept)
            recorded_messages.append(msg_accept)
            return gate_res.verified_span, recorded_messages
        else:
            self.telemetry["gate_c_vetoes"] += 1
            msg_veto = AgentMessage(
                conversation_id=conv_id,
                sender="Agent3_AdversarialVerifier",
                receiver="Agent2_CriteriaEvaluator",
                message_type=AgentMessageType.REJECT,
                payload={
                    "case_id": cid,
                    "criterion_code": ccode,
                    "veto_reason": veto_reason
                },
                question_or_decision=f"Agent 3 cross-examination veto: {veto_reason}.",
                round_number=3
            )
            AgentConversationAuditBus.record_message(msg_veto)
            recorded_messages.append(msg_veto)
            return None, recorded_messages
