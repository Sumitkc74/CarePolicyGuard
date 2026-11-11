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

from app.core.config import settings

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
        self.endpoint_url = endpoint_url or getattr(settings, "LOCAL_LLM_URL", "http://localhost:11434/v1/chat/completions")
        self.model_name = model_name or settings.LOCAL_LLM_MODEL
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
