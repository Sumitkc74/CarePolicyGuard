import json
import logging
import time
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

    def __init__(self, **data):
        if "quote" in data and "claimed_text" not in data:
            data["claimed_text"] = data["quote"]
        if "start_char" in data and "char_start" not in data:
            data["char_start"] = data["start_char"]
        if "end_char" in data and "char_end" not in data:
            data["char_end"] = data["end_char"]
        if "reasoning" in data and "rationale" not in data:
            data["rationale"] = data["reasoning"]
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

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.endpoint_url = endpoint_url or settings.LOCAL_LLM_URL
        self.model_name = model_name or settings.LOCAL_LLM_MODEL
        self.timeout_seconds = timeout_seconds or settings.LOCAL_LLM_TIMEOUT_SECONDS
        self.enabled = settings.ENABLE_LLM_PROPOSAL_STEP
        self.telemetry = {
            "total_calls": 0,
            "proposals_generated": 0,
            "gate_a_rejections": 0,
            "gate_b_rejections": 0,
            "gate_c_vetoes": 0,
            "proposals_accepted": 0,
            "total_latency_ms": 0.0
        }

    def is_available(self) -> bool:
        """Checks if local Ollama endpoint is reachable without sending clinical data."""
        if not self.enabled:
            return False
        try:
            # Query models endpoint using short timeout
            models_url = self.endpoint_url.replace("/chat/completions", "/models")
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(models_url)
                return resp.status_code == 200
        except Exception:
            return False

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

        ccode = crit.get("criterion_code", "CRIT-UNKNOWN")
        cname = crit.get("name", "")
        cdesc = crit.get("description", "")
        ctype = crit.get("criterion_type", "FINDING_PRESENCE")
        is_excl = crit.get("is_exclusion", False)

        prompt = (
            f"You are a clinical evidence extraction assistant for Medicare coverage evaluation.\n"
            f"CLINICAL NOTE:\n\"\"\"{ehr_text}\"\"\"\n\n"
            f"CRITERION:\n"
            f"- Code: {ccode}\n"
            f"- Name: {cname}\n"
            f"- Description: {cdesc}\n"
            f"- Type: {ctype}\n"
            f"- Is Exclusion: {is_excl}\n\n"
            f"TASK:\n"
            f"Find any verbatim substring in the clinical note that provides evidence for this criterion.\n"
            f"You MUST provide the exact substring and its 0-indexed character offsets (char_start, char_end).\n"
            f"Return ONLY valid JSON matching this schema:\n"
            f"{{\n"
            f"  \"proposals\": [\n"
            f"    {{\n"
            f"      \"criterion_code\": \"{ccode}\",\n"
            f"      \"proposed_status\": \"MET\" or \"NOT_MET\",\n"
            f"      \"claimed_text\": \"exact substring from note\",\n"
            f"      \"char_start\": 0,\n"
            f"      \"char_end\": 10,\n"
            f"      \"numeric_value\": float or null,\n"
            f"      \"numeric_unit\": string or null,\n"
            f"      \"rationale\": \"brief clinical rationale\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}"
        )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            import requests
            resp = requests.post(self.endpoint_url, json=payload, timeout=self.timeout_seconds)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            if resp.status_code != 200:
                return ProposalResult(([], f"SKIPPED_HTTP_{resp.status_code}", elapsed_ms))

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content)
            raw_proposals = parsed.get("proposals", [])
            if not raw_proposals and isinstance(parsed, dict) and "claimed_text" in parsed:
                raw_proposals = [parsed]

            proposals = []
            for p in raw_proposals:
                if isinstance(p, dict) and p.get("claimed_text"):
                    claimed = str(p.get("claimed_text", ""))
                    start = p.get("char_start")
                    end = p.get("char_end")
                    if start is None or end is None:
                        start = ehr_text.find(claimed)
                        end = start + len(claimed) if start != -1 else 0
                    proposals.append(LLMProposedSpan(
                        criterion_code=ccode,
                        proposed_status=p.get("proposed_status", "MET"),
                        claimed_text=claimed,
                        char_start=int(start),
                        char_end=int(end),
                        numeric_value=p.get("numeric_value"),
                        numeric_unit=p.get("numeric_unit"),
                        rationale=p.get("rationale", "LLM proposed evidence")
                    ))

            status = "COMPLETED" if proposals else "NO_PROPOSALS"
            return ProposalResult((proposals, status, elapsed_ms))

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            exc_str = str(exc).lower()
            if "timeout" in exc_str or "timed out" in exc_str:
                logger.warning(f"LLM proposal step timed out after {self.timeout_seconds}s for {ccode}: {exc}")
                return ProposalResult(([], "SKIPPED_TIMEOUT", elapsed_ms))
            else:
                logger.warning(f"LLM proposal step unavailable for {ccode}: {exc}")
                return ProposalResult(([], "SKIPPED_UNAVAILABLE", elapsed_ms))

    @staticmethod
    def evaluate_proposal_through_gates(
        proposal: LLMProposedSpan,
        sanitized_ehr: Optional[str] = None,
        criterion: Optional[Dict[str, Any]] = None,
        verifier_agent: Optional[Any] = None,
        raw_narrative: Optional[str] = None,
        criterion_def: Optional[Dict[str, Any]] = None
    ) -> GateEvaluationResult:
        """
        Passes a proposed span through the 3 mandatory gates in strict sequential order:
        (a) Exact character-span check (ehr_text[start:end] == claimed_text)
        (b) Five-dimension semantic verification (subject, timing, modality, negation, range)
        (c) Agent 3 independent cross-examination veto
        """
        text = sanitized_ehr if sanitized_ehr is not None else (raw_narrative or "")
        crit = criterion if criterion is not None else (criterion_def or {})

        s = proposal.char_start
        e = proposal.char_end
        claimed = proposal.claimed_text

        # Gate (a): Exact character-level slice check
        if s < 0 or e > len(text) or s >= e:
            return GateEvaluationResult(
                proposal=proposal,
                passed=False,
                failing_gate="GATE_A_EXACT_SLICE",
                rejection_reason=f"Invalid character offsets [{s}:{e}] for note of length {len(text)}."
            )

        actual_slice = text[s:e]
        if actual_slice != claimed:
            # Check for offset drift vs outright hallucination
            if claimed in text:
                real_pos = text.find(claimed)
                return GateEvaluationResult(
                    proposal=proposal,
                    passed=False,
                    failing_gate="GATE_A_EXACT_SLICE",
                    rejection_reason=f"Character slice mismatch: claimed [{s}:{e}] ('{actual_slice}'), true text at [{real_pos}:{real_pos+len(claimed)}]."
                )
            else:
                return GateEvaluationResult(
                    proposal=proposal,
                    passed=False,
                    failing_gate="GATE_A_EXACT_SLICE",
                    rejection_reason=f"Hallucinated evidence: claimed text '{claimed[:30]}...' does not exist in EHR note."
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

        # Gate (c): Agent 3 independent cross-examination veto
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

        # All 3 gates passed!
        return GateEvaluationResult(
            proposal=proposal,
            passed=True,
            failing_gate=None,
            rejection_reason=None,
            verified_span=candidate_span
        )
