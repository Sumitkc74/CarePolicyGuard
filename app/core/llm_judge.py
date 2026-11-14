"""
Clinical Semantic Equivalence Judge (Task 2).
Uses local LLM strictly as an equivalence judge on deterministically extracted spans.
The judge is asked ONLY: "Does this candidate evidence span state the same clinical fact as the criterion?"
It is NEVER asked whether the patient qualifies for coverage.
The judge produces NO character offsets and NO spans.
"""

from __future__ import annotations

import json
import logging
import re
import time
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core import config

logger = logging.getLogger(__name__)


class EquivalenceVerdict(str, Enum):
    """Recognized clinical semantic equivalence verdicts."""
    EQUIVALENT = "EQUIVALENT"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    AMBIGUOUS = "AMBIGUOUS"


class JudgeEvaluation(BaseModel):
    """Structured verdict from the semantic equivalence judge."""
    verdict: EquivalenceVerdict = Field(..., description="Equivalence determination")
    rationale: str = Field(..., description="One-line clinical reasoning for the verdict")
    elapsed_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: str = Field(default="COMPLETED", description="Execution status")


class CriterionJudgment(BaseModel):
    """Structured judgment from the criterion-level clinical judge (Task 2)."""
    status: str = Field(..., description="Judgment status: MET, NOT_MET, or MISSING")
    quoted_evidence: str = Field(default="", description="Verbatim text quote from clinical note supporting judgment")
    rationale: str = Field(..., description="One-sentence clinical explanation for the judgment")
    confidence: float = Field(default=0.90, description="Confidence score for the judgment")
    elapsed_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: str = Field(default="COMPLETED", description="Execution status")


class ClinicalEquivalenceJudge:
    """
    Evaluates semantic equivalence between a criterion and a deterministically extracted span.
    Enforces local-only inference, budget limits, and strict absence of coverage judgments.
    """

    EQUIVALENCE_QUESTION = (
        "Does this candidate evidence span state the same clinical fact (as a synonym, "
        "clinical subtype, paraphrase, or standard medical abbreviation) as the criterion?"
    )

    def __init__(
        self,
        endpoint_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 30.0,
        max_calls_per_case: int = 3,
        max_time_per_case_seconds: float = 30.0
    ):
        self.endpoint_url = endpoint_url or getattr(config.settings, "LOCAL_LLM_URL", "http://localhost:11434/v1/chat/completions")
        self.model_name = model_name or getattr(config.settings, "LOCAL_LLM_JUDGE_MODEL", None) or config.settings.LOCAL_LLM_MODEL
        self.timeout_seconds = timeout_seconds
        self.max_calls_per_case = max_calls_per_case
        self.max_time_per_case_seconds = max_time_per_case_seconds

        self.case_call_count = 0
        self.case_elapsed_ms = 0.0

        self.telemetry = {
            "total_judge_calls": 0,
            "equivalent_count": 0,
            "not_equivalent_count": 0,
            "ambiguous_count": 0,
            "total_latency_ms": 0.0
        }

    def reset_case_budget(self) -> None:
        """Resets per-case call count and elapsed time budget at case boundary."""
        self.case_call_count = 0
        self.case_elapsed_ms = 0.0

    def build_prompt(
        self,
        criterion_code: str,
        criterion_name: str,
        criterion_desc: str,
        candidate_span_text: str
    ) -> str:
        """
        Builds the strict semantic equivalence prompt.
        Explicitly forbids coverage judgments and restricts LLM to semantic evaluation.
        """
        return (
            f"You are a clinical semantic equivalence judge for Medicare policy criteria.\n\n"
            f"CRITERION:\n"
            f"- Code: {criterion_code}\n"
            f"- Name: {criterion_name}\n"
            f"- Clinical Fact Required: {criterion_desc}\n\n"
            f"CANDIDATE EVIDENCE SPAN (extracted verbatim from clinical note):\n"
            f"\"{candidate_span_text}\"\n\n"
            f"EVALUATION QUESTION:\n"
            f"{self.EQUIVALENCE_QUESTION}\n\n"
            f"GOVERNING RULES:\n"
            f"1. Semantic equivalence is understanding: If the span uses a medical synonym, subtype, or paraphrase for the SAME clinical concept (e.g. 'prostate adenocarcinoma' is prostate cancer), return EQUIVALENT.\n"
            f"2. Genuine ambiguity is a deferral: If the span discusses a different organ, a clinical trade-off, or requires a coverage judgment (e.g. whether rectal sparing substitutes for spinal cord proximity), return AMBIGUOUS.\n"
            f"3. Do NOT evaluate whether the patient qualifies for insurance coverage. Only evaluate if the span expresses the same clinical fact.\n"
            f"4. Do NOT output character offsets or spans. Output ONLY valid JSON.\n\n"
            f"Return JSON matching this exact structure:\n"
            f"{{\n"
            f'  "verdict": "EQUIVALENT" or "NOT_EQUIVALENT" or "AMBIGUOUS",\n'
            f'  "rationale": "<concise one-line clinical explanation>"\n'
            f"}}"
        )

    def judge_equivalence_sync(
        self,
        criterion: dict[str, Any],
        candidate_span_text: str
    ) -> JudgeEvaluation:
        """
        Synchronously queries the local LLM judge to determine semantic equivalence.
        """
        t0 = time.perf_counter()

        # Check per-case budget guardrails
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(f"Judge call budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) for case.")
            return JudgeEvaluation(
                verdict=EquivalenceVerdict.AMBIGUOUS,
                rationale="Judge call budget exceeded (3 calls max per case); defers to human.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Judge time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return JudgeEvaluation(
                verdict=EquivalenceVerdict.AMBIGUOUS,
                rationale="Judge time budget exceeded (30s max per case); defers to human.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cname = criterion.get("name", "")
        cdesc = criterion.get("description", cname)

        prompt = self.build_prompt(ccode, cname, cdesc, candidate_span_text)

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 200
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(self.endpoint_url, json=payload)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms

            if resp.status_code != 200:
                return JudgeEvaluation(
                    verdict=EquivalenceVerdict.AMBIGUOUS,
                    rationale=f"LLM endpoint HTTP {resp.status_code}; falling back to AMBIGUOUS.",
                    elapsed_ms=elapsed_ms,
                    status_code=f"HTTP_{resp.status_code}"
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                m_verdict = re.search(r'"verdict":\s*"(EQUIVALENT|NOT_EQUIVALENT|AMBIGUOUS)"', content)
                m_rat = re.search(r'"rationale":\s*"([^"]+)"', content)
                parsed = {
                    "verdict": m_verdict.group(1) if m_verdict else "AMBIGUOUS",
                    "rationale": m_rat.group(1) if m_rat else "Extracted from partial response"
                }

            v_str = str(parsed.get("verdict", "AMBIGUOUS")).strip().upper()
            if v_str == "EQUIVALENT":
                verdict = EquivalenceVerdict.EQUIVALENT
                self.telemetry["equivalent_count"] += 1
            elif v_str == "NOT_EQUIVALENT":
                verdict = EquivalenceVerdict.NOT_EQUIVALENT
                self.telemetry["not_equivalent_count"] += 1
            else:
                verdict = EquivalenceVerdict.AMBIGUOUS
                self.telemetry["ambiguous_count"] += 1

            rat = str(parsed.get("rationale", "No explanation provided.")).strip()

            return JudgeEvaluation(
                verdict=verdict,
                rationale=rat,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )

        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            logger.warning(f"Judge execution error for {ccode}: {exc}")
            return JudgeEvaluation(
                verdict=EquivalenceVerdict.AMBIGUOUS,
                rationale=f"Inference exception: {exc!s}",
                elapsed_ms=elapsed_ms,
                status_code="ERROR"
            )

    def build_criterion_prompt(
        self,
        criterion: dict[str, Any],
        note_text: str,
        deterministic_assessment: Any | None = None
    ) -> str:
        """
        Builds the structured criterion evaluation prompt for the LLM judge (Task 2).
        Explicitly asks for MET / NOT_MET / MISSING, verbatim quoted evidence, and clinical rationale.
        """
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cname = criterion.get("name", "")
        cdesc = criterion.get("description", cname)
        cintent = criterion.get("clinical_intent", "")
        is_excl = criterion.get("is_exclusion", False)

        det_status = (
            deterministic_assessment.status.value
            if deterministic_assessment and hasattr(deterministic_assessment.status, "value")
            else (str(deterministic_assessment.status) if deterministic_assessment else "INSUFFICIENT_EVIDENCE")
        )
        det_rationale = (
            deterministic_assessment.clinical_rationale
            if deterministic_assessment and getattr(deterministic_assessment, "clinical_rationale", None)
            else "None"
        )

        return (
            f"You are a clinical evaluation judge for Medicare prior authorization criteria.\n\n"
            f"CRITERION:\n"
            f"- Code: {ccode}\n"
            f"- Name: {cname}\n"
            f"- Type: {'EXCLUSION' if is_excl else 'INCLUSION'}\n"
            f"- Statutory Requirement: {cdesc}\n"
            f"- Clinical Intent: {cintent}\n\n"
            f"PREVIOUS DETERMINISTIC EVALUATION ATTEMPT:\n"
            f"- Status: {det_status}\n"
            f"- Reason: {det_rationale}\n\n"
            f"FULL PATIENT CLINICAL NOTE:\n"
            f'"""\n{note_text}\n"""\n\n'
            f"TASK:\n"
            f"Evaluate whether the clinical note provides documented clinical evidence satisfying this criterion.\n"
            f"1. If affirmative evidence is present (including clinical synonyms, paraphrases, or specific subtypes), set status to 'MET' and provide the EXACT verbatim quote from the note.\n"
            f"2. If the note explicitly documents that the finding is ruled out or absent, set status to 'NOT_MET' and provide the exact quote.\n"
            f"3. If the note does not contain information addressing this requirement, set status to 'MISSING' and leave quoted_evidence as empty string.\n\n"
            f"GOVERNING RULES:\n"
            f"- 'quoted_evidence' MUST be copied character-for-character from the clinical note. Do not invent or summarize quotes.\n"
            f"- Do not evaluate general insurance eligibility; evaluate this specific clinical requirement.\n"
            f"- Output ONLY valid JSON matching this schema:\n"
            f"{{\n"
            f'  "status": "MET" or "NOT_MET" or "MISSING",\n'
            f'  "quoted_evidence": "<exact verbatim quote from note or empty string>",\n'
            f'  "rationale": "<one-sentence clinical reasoning>"\n'
            f"}}"
        )

    def judge_criterion_sync(
        self,
        criterion: dict[str, Any],
        note_text: str,
        deterministic_assessment: Any | None = None
    ) -> CriterionJudgment:
        """
        Task 2: Synchronously evaluates a whole criterion against the clinical note using the local LLM.
        Returns a structured CriterionJudgment with status, quoted evidence, and clinical rationale.
        """
        t0 = time.perf_counter()
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")

        # Budget checks
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(f"Judge call budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) on {ccode}.")
            return CriterionJudgment(
                status="MISSING",
                quoted_evidence="",
                rationale="Judge call budget exceeded (3 calls max per case); defers to human.",
                confidence=0.50,
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Judge time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return CriterionJudgment(
                status="MISSING",
                quoted_evidence="",
                rationale="Judge time budget exceeded (30s max per case); defers to human.",
                confidence=0.50,
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        prompt = self.build_criterion_prompt(criterion, note_text, deterministic_assessment)

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 250
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(self.endpoint_url, json=payload)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms

            if resp.status_code != 200:
                return CriterionJudgment(
                    status="MISSING",
                    quoted_evidence="",
                    rationale=f"LLM endpoint HTTP {resp.status_code}; falling back to MISSING.",
                    confidence=0.50,
                    elapsed_ms=elapsed_ms,
                    status_code=f"HTTP_{resp.status_code}"
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                m_stat = re.search(r'"status":\s*"(MET|NOT_MET|MISSING)"', content, re.IGNORECASE)
                m_quote = re.search(r'"quoted_evidence":\s*"([^"]*)"', content)
                m_rat = re.search(r'"rationale":\s*"([^"]+)"', content)
                parsed = {
                    "status": m_stat.group(1).upper() if m_stat else "MISSING",
                    "quoted_evidence": m_quote.group(1) if m_quote else "",
                    "rationale": m_rat.group(1) if m_rat else "Extracted from partial response"
                }

            raw_stat = str(parsed.get("status", "MISSING")).strip().upper()
            if raw_stat not in ("MET", "NOT_MET", "MISSING"):
                raw_stat = "MISSING"

            quote = str(parsed.get("quoted_evidence", "")).strip()
            rationale = str(parsed.get("rationale", "No rationale provided.")).strip()

            return CriterionJudgment(
                status=raw_stat,
                quoted_evidence=quote,
                rationale=rationale,
                confidence=0.92 if raw_stat == "MET" else 0.85,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )

        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            logger.warning(f"Judge criterion execution error for {ccode}: {exc}")
            return CriterionJudgment(
                status="MISSING",
                quoted_evidence="",
                rationale=f"Inference exception: {exc!s}",
                confidence=0.50,
                elapsed_ms=elapsed_ms,
                status_code="ERROR"
            )

    def generate_adversarial_counter_reading_sync(
        self,
        criterion: dict[str, Any],
        proposed_evidence: str,
        note_text: str
    ) -> dict[str, Any]:
        """
        Task 3: Queries the LLM as an adversarial advocate to find the strongest counter-reading
        or clinical contradiction in the clinical note for a proposed evidence span.
        """
        t0 = time.perf_counter()
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")

        if self.case_call_count >= self.max_calls_per_case or self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            return {
                "has_objection": False,
                "objection_type": "NONE",
                "counter_quote": "",
                "rationale": "Adversarial budget bound reached."
            }

        prompt = (
            f"You are an adversarial clinical auditor challenging prior authorization claims.\n\n"
            f"CRITERION: {ccode}: {criterion.get('name', '')}\n"
            f"REQUIREMENT: {criterion.get('description', '')}\n"
            f"PROPOSED SUPPORTING EVIDENCE: \"{proposed_evidence}\"\n\n"
            f"FULL CLINICAL NOTE:\n\"\"\"\n{note_text}\n\"\"\"\n\n"
            f"TASK:\n"
            f"Formulate the strongest potential counter-reading, clinical objection, or ambiguity against accepting this evidence. Specifically check for:\n"
            f"1. Negation (is the finding negated elsewhere, e.g. 'denies', 'resolved', 'no evidence of')?\n"
            f"2. Wrong experiencer (does the finding belong to family history or someone else)?\n"
            f"3. Temporal/duration mismatch (did conservative therapy last < required weeks, or is it outdated)?\n"
            f"4. Hypothetical / speculative (is the finding merely a differential, rule-out, or future consideration)?\n"
            f"5. Anatomic / organ mismatch (is it a different anatomic site or unrelated condition)?\n\n"
            f"If there is a valid clinical objection, ambiguity, or contradiction, set has_objection to true, specify the objection_type, quote the contradictory text from the note, and provide a one-sentence challenge rationale.\n"
            f"If the evidence is completely solid, unambiguous, and unassailable in the note with NO contradictions or doubts, set has_objection to false.\n\n"
            f"Output ONLY JSON in this format:\n"
            f"{{\n"
            f'  "has_objection": true or false,\n'
            f'  "objection_type": "NEGATION" or "EXPERIENCER" or "TEMPORAL" or "HYPOTHETICAL" or "ANATOMIC_MISMATCH" or "NONE",\n'
            f'  "counter_quote": "<verbatim excerpt from note or empty string>",\n'
            f'  "rationale": "<one-sentence explanation of the challenge>"\n'
            f"}}"
        )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 200
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(self.endpoint_url, json=payload)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms

            if resp.status_code != 200:
                return {"has_objection": False, "objection_type": "NONE", "counter_quote": "", "rationale": "HTTP error"}

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content)

            return {
                "has_objection": bool(parsed.get("has_objection", False)),
                "objection_type": str(parsed.get("objection_type", "NONE")),
                "counter_quote": str(parsed.get("counter_quote", "")),
                "rationale": str(parsed.get("rationale", ""))
            }
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            logger.debug(f"Adversarial counter-reading query exception: {exc}")
            return {"has_objection": False, "objection_type": "NONE", "counter_quote": "", "rationale": str(exc)}
