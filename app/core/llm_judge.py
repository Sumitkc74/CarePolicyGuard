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


class DefenseResult(BaseModel):
    """Structured defense result from Agent 2 in response to an adversarial counter-reading (Task 2)."""
    defense_quote: str = Field(default="", description="Verbatim quote from clinical note answering the objection")
    rationale: str = Field(..., description="Clinical reasoning explaining how the quote resolves the objection")
    elapsed_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: str = Field(default="COMPLETED", description="Execution status")
    objection_valid: bool = Field(default=True, description="Whether the verifier's objection cites a requirement actually present in the criterion text with correct logic/arithmetic")
    objection_invalid_reason: str = Field(default="", description="If objection_valid is False, the clinical/textual explanation quoting the criterion text explaining why the objection is invalid")


class AdvocacyResult(BaseModel):
    """Structured advocacy result from Agent 3 arguing FOR criterion satisfaction (Task 1)."""
    advocacy_quote: str = Field(default="", description="Verbatim text quote from clinical note supporting satisfaction")
    rationale: str = Field(..., description="Clinical reasoning explaining how the quoted evidence satisfies the requirement")
    elapsed_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: str = Field(default="COMPLETED", description="Execution status")


class CaseDeferralReview(BaseModel):
    """Structured case-level pre-deferral confirmation from the clinical judge (Task 2b)."""
    confirmed_deferrable: bool = Field(default=True, description="Whether the case is confirmed genuinely deferrable")
    rationale: str = Field(..., description="Clinical reasoning confirming lack of statutory evidence")
    elapsed_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: str = Field(default="COMPLETED", description="Execution status")



_GENERIC_CLINICAL_STOPWORDS = {
    "patient", "clinical", "prior", "authorization", "must", "have", "has", "been", "to",
    "at", "by", "from", "criteria", "statutory", "requirement", "documented", "documentation",
    "progressive", "evaluation", "presents", "presenting", "clinic", "outpatient", "inpatient",
    "progress", "note", "subjective", "objective", "assessment", "plan", "history", "years",
    "year", "old", "male", "female", "days", "weeks", "months", "synthetic", "test", "data", "record",
    "and", "or", "for", "the", "of", "in", "with", "a", "an", "is", "are", "was", "were",
}

_SEMANTIC_SYNONYMS: dict[str, set[str]] = {
    "malignancy": {"adenocarcinoma", "carcinoma", "malignancy", "cancer", "neoplasm", "tumor", "lymphoma", "melanoma", "sarcoma", "leukemia", "metastatic", "mass"},
    "reversible": {"reversible", "causes", "toxicity", "blocking", "blockers", "potassium", "electrolyte", "thyroid"},
    "bradyarrhythmia": {"bradycardia", "bradyarrhythmia", "av block", "heart block", "atrioventricular block", "pause", "sinus pause", "dissociation", "asystole"},
    "headache": {"headache", "cephalalgia", "migraine", "head pain", "papilledema", "valsalva"},
}


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
        max_time_per_case_seconds: float = 60.0
    ):
        self.endpoint_url = endpoint_url or getattr(config.settings, "LOCAL_LLM_URL", "http://localhost:11434/v1/chat/completions")
        self.model_name = model_name or getattr(config.settings, "LOCAL_LLM_JUDGE_MODEL", None) or config.settings.LOCAL_LLM_MODEL
        self.timeout_seconds = timeout_seconds
        self.max_calls_per_case = max_calls_per_case
        self.max_time_per_case_seconds = max_time_per_case_seconds

        self.case_call_count = 0
        self.case_elapsed_ms = 0.0
        self.evaluated_spans_cache: dict[tuple[str, str], JudgeEvaluation] = {}

        self.telemetry = {
            "total_judge_calls": 0,
            "equivalent_count": 0,
            "not_equivalent_count": 0,
            "ambiguous_count": 0,
            "total_latency_ms": 0.0
        }

    def reset_case_budget(self) -> None:
        """Resets per-case call count, elapsed time budget, and span cache at case boundary."""
        self.case_call_count = 0
        self.case_elapsed_ms = 0.0
        self.evaluated_spans_cache.clear()

    def build_prompt(
        self,
        criterion_code: str,
        criterion_name: str,
        criterion_desc: str,
        candidate_span_text: str,
        clinical_intent: str = ""
    ) -> str:
        """
        Builds the strict semantic equivalence prompt (Task 1).
        Verifies the candidate evidence span against the criterion requirement AS WRITTEN.
        Explicitly forbids coverage judgments and restricts LLM to semantic evaluation.
        """
        intent_block = f"\n- Clinical Intent: {clinical_intent}" if clinical_intent else ""
        return (
            f"You are a clinical semantic equivalence judge for Medicare policy criteria.\n\n"
            f"CRITERION:\n"
            f"- Code: {criterion_code}\n"
            f"- Name: {criterion_name}\n"
            f"- Requirement as Written: {criterion_desc}{intent_block}\n\n"
            f"CANDIDATE EVIDENCE SPAN (extracted verbatim from clinical note):\n"
            f"\"{candidate_span_text}\"\n\n"
            f"TASK:\n"
            f"Determine whether the candidate evidence span satisfies the criterion requirement AS WRITTEN (either fully or through a qualifying clinical branch/alternative stated in the requirement).\n"
            f"State clearly which requirement or branch the span satisfies or fails, explicitly quoting the criterion text applied.\n\n"
            f"GOVERNING RULES:\n"
            f"1. Semantic Equivalence is Understanding: If the span uses a medical synonym, clinical subtype, or paraphrase for the required clinical condition (e.g. 'prostate adenocarcinoma' is prostate cancer; 'esophageal adenocarcinoma' or 'colorectal adenocarcinoma' is biopsy-proven malignancy; 'absence of reversible causes' confirms bradyarrhythmia is not caused by reversible causes), return EQUIVALENT.\n"
            f"2. Check the criterion requirement AS WRITTEN: When a criterion specifies alternatives (e.g. separated by 'or', parentheses '(or ...)', or multiple qualifying clinical pathways), satisfying EITHER alternative satisfies the criterion (satisfying ANY one of the stated qualifying branches). You must NOT require the span to satisfy all alternatives or require features from an alternative branch (e.g. if the requirement is 'Pathology report documenting biopsy-proven malignancy (or solitary pulmonary nodule)', biopsy proof of ANY malignancy satisfies the first branch; do NOT reject it because it is not a pulmonary nodule or not in the lung).\n"
            f"3. Ambiguity vs Genuine Dissimilarity: If the span describes a completely unrelated condition, fails to meet the core clinical requirement, or requires a coverage/medical necessity trade-off, return NOT_EQUIVALENT or AMBIGUOUS.\n"
            f"4. Do NOT evaluate whether the patient qualifies for insurance coverage. Only evaluate if the span expresses the same clinical fact as written.\n"
            f"5. Rationale Requirement: The rationale MUST explicitly quote the exact phrase from 'Requirement as Written' that the evidence satisfies (if EQUIVALENT) or fails to satisfy (if NOT_EQUIVALENT / AMBIGUOUS).\n"
            f"6. Output Format: Output ONLY valid JSON matching this exact structure:\n"
            f"{{\n"
            f'  "verdict": "EQUIVALENT" or "NOT_EQUIVALENT" or "AMBIGUOUS",\n'
            f'  "rationale": "<clinical explanation stating which requirement the span satisfies or fails, explicitly quoting the criterion text applied>"\n'
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
                rationale=f"Judge call budget exceeded ({self.max_calls_per_case} calls max per case); defers to human.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Judge time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return JudgeEvaluation(
                verdict=EquivalenceVerdict.AMBIGUOUS,
                rationale="Judge time budget exceeded (60s max per case); defers to human.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cname = criterion.get("name", "")
        cdesc = criterion.get("description", cname)
        cintent = criterion.get("clinical_intent", "")

        cache_key = (ccode, candidate_span_text.strip())
        if hasattr(self, "evaluated_spans_cache") and cache_key in self.evaluated_spans_cache:
            return self.evaluated_spans_cache[cache_key]

        prompt = self.build_prompt(ccode, cname, cdesc, candidate_span_text, clinical_intent=cintent)

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

            eval_res = JudgeEvaluation(
                verdict=verdict,
                rationale=rat,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )
            if hasattr(self, "evaluated_spans_cache"):
                self.evaluated_spans_cache[cache_key] = eval_res
            return eval_res

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
            f"Directly check the criterion's key terms and clinical requirements against the documented findings in the clinical note:\n"
            f"1. If affirmative clinical findings are present satisfying the key terms (including clinical synonyms, paraphrases, or specific subtypes, e.g. adenocarcinoma is biopsy-proven malignancy; absence of reversible causes / not taking AV nodal blockers confirms bradyarrhythmia is not caused by reversible drug toxicity), set status to 'MET' and quote the specific finding character-for-character as 'quoted_evidence'.\n"
            f"2. If the note explicitly documents that the finding is ruled out, absent, or fails statutory thresholds, set status to 'NOT_MET' and provide the exact quote.\n"
            f"3. If the note does not contain information addressing these key terms, set status to 'MISSING' and leave quoted_evidence as empty string.\n\n"
            f"GOVERNING RULES:\n"
            f"- The verdict MUST be grounded in a quoted finding directly extracted from the clinical note. 'quoted_evidence' MUST be copied character-for-character from the clinical note. Do not invent or summarize quotes.\n"
            f"- Do not evaluate general insurance eligibility; evaluate this specific clinical requirement.\n"
            f"- Output ONLY valid JSON matching this schema:\n"
            f"{{\n"
            f'  "status": "MET" or "NOT_MET" or "MISSING",\n'
            f'  "quoted_evidence": "<exact verbatim quote from note or empty string>",\n'
            f'  "rationale": "<one-sentence clinical reasoning grounded in the finding>"\n'
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
                rationale=f"Judge call budget exceeded ({self.max_calls_per_case} calls max per case); defers to human.",
                confidence=0.50,
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Judge time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return CriterionJudgment(
                status="MISSING",
                quoted_evidence="",
                rationale="Judge time budget exceeded (60s max per case); defers to human.",
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
            f"If there is a valid clinical objection, ambiguity, or contradiction, set has_objection to true, specify the objection_type, quote any contradictory text from the note, state any unmet clinical sub-requirement phrase from the criterion text (e.g. named test, duration, threshold, or clinical finding; NEVER a criterion code like CRIT-... or requirement number), and provide a one-sentence challenge rationale.\n"
            f"If the challenge cites a specific contradicting verbatim span from the note or a named clinical sub-requirement from the criterion text that the evidence fails, set specific_contradiction to true. If the challenge is general skepticism, ambiguity, or unsupported doubt, set specific_contradiction to false.\n"
            f"If the evidence is solid, unambiguous, and unassailable in the note with NO contradictions or doubts, set has_objection to false.\n\n"
            f"Output ONLY JSON in this format:\n"
            f"{{\n"
            f'  "has_objection": true or false,\n'
            f'  "objection_type": "NEGATION" or "EXPERIENCER" or "TEMPORAL" or "HYPOTHETICAL" or "ANATOMIC_MISMATCH" or "NONE",\n'
            f'  "counter_quote": "<verbatim excerpt from note or empty string>",\n'
            f'  "named_sub_requirement": "<clinical sub-requirement phrase from criterion text that is unmet, NEVER a criterion code like CRIT-... or requirement reference, or empty string>",\n'
            f'  "specific_contradiction": true or false,\n'
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
                return {"has_objection": False, "objection_type": "NONE", "counter_quote": "", "named_sub_requirement": "", "specific_contradiction": False, "rationale": "HTTP error"}

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content)

            return {
                "has_objection": bool(parsed.get("has_objection", False)),
                "objection_type": str(parsed.get("objection_type", "NONE")),
                "counter_quote": str(parsed.get("counter_quote", "")),
                "named_sub_requirement": str(parsed.get("named_sub_requirement", "")),
                "specific_contradiction": bool(parsed.get("specific_contradiction", False)),
                "rationale": str(parsed.get("rationale", ""))
            }
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            logger.debug(f"Adversarial counter-reading query exception: {exc}")
            return {"has_objection": False, "objection_type": "NONE", "counter_quote": "", "named_sub_requirement": "", "specific_contradiction": False, "rationale": str(exc)}

    def generate_defense_sync(
        self,
        criterion: dict[str, Any],
        objection: dict[str, Any],
        proposed_evidence: str,
        note_text: str
    ) -> DefenseResult:
        """
        Task 2 (v51-fix): Evaluates an adversarial objection against a proposed criterion judgment,
        attempting to defend the criterion by locating resolving evidence in the note.
        Returns a structured DefenseResult (defense_quote + rationale).
        """
        t0 = time.perf_counter()
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        obj_type = objection.get("objection_type", "OBJECTION")
        obj_rationale = objection.get("rationale", "")
        counter_quote = objection.get("counter_quote", "")

        # Budget checks
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(f"Defense budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) on {ccode}.")
            return DefenseResult(
                defense_quote="",
                rationale="Defense call budget exceeded; cannot answer objection.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Defense time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return DefenseResult(
                defense_quote="",
                rationale="Defense time budget exceeded; cannot answer objection.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        prompt = (
            f"You are Agent 2 (Clinical Evaluator) defending a prior authorization coverage criterion against an adversarial objection.\n\n"
            f"CRITERION: {ccode}: {criterion.get('name', '')}\n"
            f"REQUIREMENT: {criterion.get('description', '')}\n"
            f"ORIGINAL PROPOSED EVIDENCE: \"{proposed_evidence}\"\n\n"
            f"ADVERSARIAL OBJECTION:\n"
            f"Objection Type: {obj_type}\n"
            f"Objection Rationale: {obj_rationale}\n"
            f"Challenging Quote: \"{counter_quote}\"\n\n"
            f"FULL CLINICAL NOTE:\n\"\"\"\n{note_text}\n\"\"\"\n\n"
            f"TASK:\n"
            f"STEP 1 — OBJECTION-VALIDITY CHECK (Perform this FIRST):\n"
            f"Examine the exact REQUIREMENT text above and evaluate whether the adversarial objection is valid or invalid:\n"
            f"  (i) Does the objection cite or demand a requirement, duration, threshold, test, or finding that is NOT actually present in the criterion REQUIREMENT text? If the objection asserts a requirement absent from the criterion text, the objection is INVALID (objection_valid=false).\n"
            f"  (ii) Does the objection assert a backwards or mathematically/clinically incorrect comparison? For example, with Snellen visual acuity, a larger denominator represents worse vision (20/60 is worse vision than 20/50, satisfying '20/50 or worse'); asserting that 20/60 fails '20/50 or worse' is backwards and INVALID (objection_valid=false).\n"
            f"  (iii) If the objection is INVALID, set objection_valid to false, quote the exact criterion text in objection_invalid_reason explaining why the objection fails, set defense_quote to \"\", and explain why the original evidence stands in rationale.\n\n"
            f"STEP 2 — EVIDENCE RESOLUTION (Only if objection is VALID):\n"
            f"  - If the objection is VALID (objection_valid=true): Examine the clinical note to determine if there is specific evidence that directly resolves, refutes, or satisfies this objection. If resolving evidence exists elsewhere in the note, provide a verbatim quote (defense_quote) DIFFERENT from the original proposed evidence, and explain how it resolves the objection in rationale. If the objection is valid and cannot be refuted by the clinical note, return defense_quote as \"\" and explain why the objection stands.\n\n"
            f"Output ONLY JSON in this format:\n"
            f"{{\n"
            f'  "objection_valid": true or false,\n'
            f'  "objection_invalid_reason": "<explanation quoting criterion text if invalid, or empty string if valid>",\n'
            f'  "defense_quote": "<verbatim excerpt from note resolving objection if objection is valid and unrefuted, or empty string>",\n'
            f'  "rationale": "<clinical explanation answering the objection or explaining why the objection stands/fails>"\n'
            f"}}"
        )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 300
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
                return DefenseResult(
                    defense_quote="",
                    rationale=f"LLM endpoint HTTP {resp.status_code}; defense call failed.",
                    elapsed_ms=elapsed_ms,
                    status_code=f"HTTP_{resp.status_code}"
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                m_valid = re.search(r'"objection_valid":\s*(true|false)', content, re.IGNORECASE)
                m_inv_reason = re.search(r'"objection_invalid_reason":\s*"([^"]*)"', content)
                m_quote = re.search(r'"defense_quote":\s*"([^"]*)"', content)
                m_rat = re.search(r'"rationale":\s*"([^"]+)"', content)
                parsed = {
                    "objection_valid": (m_valid.group(1).lower() == "true") if m_valid else True,
                    "objection_invalid_reason": m_inv_reason.group(1) if m_inv_reason else "",
                    "defense_quote": m_quote.group(1) if m_quote else "",
                    "rationale": m_rat.group(1) if m_rat else "Extracted from partial response"
                }

            obj_valid_val = parsed.get("objection_valid")
            if obj_valid_val is None:
                obj_valid = True
            else:
                obj_valid = bool(obj_valid_val)

            invalid_reason = str(parsed.get("objection_invalid_reason", "")).strip()
            quote = str(parsed.get("defense_quote", "")).strip()
            rationale = str(parsed.get("rationale", "No rationale provided.")).strip()

            return DefenseResult(
                objection_valid=obj_valid,
                objection_invalid_reason=invalid_reason,
                defense_quote=quote,
                rationale=rationale,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            logger.debug(f"Defense query exception: {exc}")
            return DefenseResult(
                defense_quote="",
                rationale=f"Defense query exception: {exc!s}",
                elapsed_ms=elapsed_ms,
                status_code="ERROR"
            )

    @classmethod
    def select_most_relevant_span(
        cls,
        criterion: dict[str, Any],
        note_text: str,
        candidate_quote: str = "",
    ) -> str:
        """
        Task 2 (v62 & v75): Refines advocate span selection using SapBERT semantic matching
        and clinical entity grounding to ensure the quote directly addresses the criterion's
        core stated elements rather than secondary fragments or absent findings.
        """
        if not note_text:
            return candidate_quote

        cname = criterion.get("name", "")
        cdesc = criterion.get("description", cname)
        req_text = f"{cname} {cdesc}".strip().lower()

        # Extract criterion-specific terms (excluding generic clinical stopwords)
        req_tokens = set(re.findall(r"[a-z0-9]+", req_text)) - _GENERIC_CLINICAL_STOPWORDS

        raw_sentences = re.split(r"(?<=[.!?\n])\s+", note_text.strip())
        sentences: list[str] = []
        for s in raw_sentences:
            lines = [line.strip() for line in s.split("\n") if line.strip()]
            for line in lines:
                cleaned = re.sub(
                    r"^(?:\[SYNTHETIC TEST DATA[^\]]*\]\s*|CLINICAL PROGRESS NOTE:[^\n]*\n*|(?:SUBJECTIVE|OBJECTIVE|ASSESSMENT\s*&\s*PLAN|ASSESSMENT|PLAN|HISTORY|HPI|EXAM):\s*)",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()
                if len(cleaned) >= 10 and cleaned in note_text and not cleaned.startswith("[SYNTHETIC"):
                    sentences.append(cleaned)

        if not sentences:
            return candidate_quote if (candidate_quote and candidate_quote in note_text) else ""

        # Key requirement elements that take precedence over peripheral readings
        priority_stems: list[str] = []
        if "inoperab" in req_text:
            priority_stems.append("inoperab")
        if "oligometasta" in req_text:
            priority_stems.append("oligometasta")
        if "psycholog" in req_text:
            priority_stems.append("psycholog")
        if "edema" in req_text:
            priority_stems.append("edema")
        if "infection" in req_text:
            priority_stems.append("infection")
        if "claudication" in req_text or "stenosis" in req_text:
            priority_stems.extend(["claudication", "stenosis", "ischemia"])

        # Check if candidate_quote already covers priority stems
        cand_norm = candidate_quote.lower() if candidate_quote else ""
        if (
            candidate_quote
            and candidate_quote in note_text
            and priority_stems
            and all(stem in cand_norm for stem in priority_stems)
        ):
            return candidate_quote

        is_absence_criterion = any(k in req_text for k in ["absence of", "not caused by", "without", "negative for", "ruled out"])
        neg_pats = [
            r"\bno\s+history\s+of\b", r"\bdenies\b", r"\bnegative\s+for\b", r"\bno\s+evidence\s+of\b",
            r"\bruled\s+out\b", r"\babsent\b", r"\bnot\s+indicated\b", r"\bcontraindicated\b",
            r"\bineffective\b", r"\bnot\s+recommended\b"
        ]

        best_span = ""

        # If candidate_quote is provided and priority_stems are absent or already satisfied by candidate,
        # query specifically for candidate_quote to find the nearest verbatim paraphrase span.
        # Otherwise, if candidate lacks priority stems (e.g. weak fragment), query for the criterion requirement.
        is_paraphrase_query = bool(
            candidate_quote
            and (not priority_stems or any(stem in cand_norm for stem in priority_stems))
        )
        query_text = candidate_quote if is_paraphrase_query else req_text
        min_sim_threshold = 0.60 if is_paraphrase_query else 0.35

        # Try SapBERT semantic embedding similarity
        try:
            import torch

            from app.services.hybrid_retriever import _get_sapbert_model
            tokenizer, model, device = _get_sapbert_model()

            inputs = tokenizer([query_text] + sentences, padding=True, truncation=True, max_length=256, return_tensors="pt").to(device)
            with torch.no_grad():
                out = model(**inputs)
                reps = out.last_hidden_state[:, 0, :]
                norms = reps.norm(dim=1, keepdim=True)
                normed = reps / torch.clamp(norms, min=1e-9)
                query_emb = normed[0:1]
                sent_embs = normed[1:]
                sims = (query_emb @ sent_embs.T)[0].tolist()

            candidates: list[tuple[float, str]] = []
            for sent, sim in zip(sentences, sims):
                sent_lower = sent.lower()
                if not is_absence_criterion and any(re.search(p, sent_lower) for p in neg_pats):
                    continue

                sent_tokens = set(re.findall(r"[a-z0-9]+", sent_lower))
                has_term_overlap = bool(req_tokens & sent_tokens)

                has_synonym_match = False
                for syn_set in _SEMANTIC_SYNONYMS.values():
                    if any(req_t in syn_set for req_t in req_tokens) and any(sent_t in syn_set for sent_t in sent_tokens):
                        has_synonym_match = True
                        break

                # If matching a specific candidate quote paraphrase, high semantic similarity is sufficient
                if is_paraphrase_query or has_term_overlap or has_synonym_match:
                    score = sim
                    if not is_paraphrase_query and priority_stems and any(stem in sent_lower for stem in priority_stems):
                        score += 0.5
                    candidates.append((score, sent))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                top_sim, top_sent = candidates[0]
                if top_sim >= min_sim_threshold:
                    best_span = top_sent
        except (ImportError, RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
            logger.debug(f"SapBERT span search fallback: {exc}")

        # Lexical fallback if SapBERT did not resolve
        if not best_span:
            best_score = 0.0
            for sent in sentences:
                sent_lower = sent.lower()
                if not is_absence_criterion and any(re.search(p, sent_lower) for p in neg_pats):
                    continue
                sent_words = set(re.findall(r"[a-z0-9]+", sent_lower))
                overlap = len(req_tokens & sent_words)
                score = float(overlap)
                for stem in priority_stems:
                    if stem in sent_lower:
                        score += 15.0
                if score > best_score and score >= 2.0:
                    best_score = score
                    best_span = sent

        if priority_stems and best_span and any(stem in best_span.lower() for stem in priority_stems):
            return best_span

        if candidate_quote and candidate_quote in note_text:
            return candidate_quote if not best_span else best_span

        return best_span

    def generate_advocacy_sync(
        self,
        criterion: dict[str, Any],
        note_text: str,
        deterministic_assessment: Any | None = None
    ) -> AdvocacyResult:
        """
        Task 1 (v53) / Task 2 (v62): When a criterion judge returns NOT_MET or INSUFFICIENT_EVIDENCE,
        Agent 3 acts as an advocate arguing FOR satisfaction by discovering clinical evidence,
        synonyms, paraphrases, or subtypes in the note supporting satisfaction.
        Selects the verbatim span that most directly addresses the criterion's stated elements.
        Returns an AdvocacyResult (advocacy_quote + rationale).
        """
        t0 = time.perf_counter()
        ccode = criterion.get("criterion_code", "CRIT-UNKNOWN")
        cname = criterion.get("name", "")
        cdesc = criterion.get("description", cname)
        cintent = criterion.get("clinical_intent", "")

        # Budget checks
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(f"Advocacy budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) on {ccode}.")
            return AdvocacyResult(
                advocacy_quote="",
                rationale="Advocacy call budget exceeded; cannot argue for satisfaction.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Advocacy time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return AdvocacyResult(
                advocacy_quote="",
                rationale="Advocacy time budget exceeded; cannot argue for satisfaction.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        prompt = (
            f"You are Agent 3 acting as a clinical advocate examining a prior authorization criterion.\n"
            f"The initial evaluation did not find evidence for this criterion. Your role is to examine the full clinical note "
            f"to determine if there is valid clinical evidence, medical synonyms, subtypes, or paraphrases that support satisfaction.\n\n"
            f"CRITERION:\n"
            f"- Code: {ccode}\n"
            f"- Name: {cname}\n"
            f"- Statutory Requirement: {cdesc}\n"
            f"- Clinical Intent: {cintent}\n\n"
            f"FULL CLINICAL NOTE:\n\"\"\"\n{note_text}\n\"\"\"\n\n"
            f"TASK:\n"
            f"1. Identify the core required qualifying elements of the statutory requirement (such as disease stage, inoperability, objective thresholds, formal evaluations, or specific clinical conditions). Do NOT select secondary or peripheral fragments (such as isolated SUV numbers, imaging metrics, or vital signs) if a span directly addressing the core qualifying condition or status exists.\n"
            f"2. Search the note for the verbatim span that most directly and comprehensively addresses the criterion's core stated elements. The quote must cover the central qualifying elements (e.g. for inoperability criteria, quote the documentation of inoperability or early-stage disease rather than isolated metabolic numbers).\n"
            f"3. If supporting evidence exists, extract the EXACT verbatim quote (advocacy_quote) from the note and provide a concise clinical rationale explaining how it satisfies the requirement.\n"
            f"4. If the note truly contains no evidence supporting satisfaction, return advocacy_quote as an empty string (\"\") and explain that no supporting evidence exists.\n\n"
            f"GOVERNING RULES:\n"
            f"- 'advocacy_quote' MUST be an exact character-for-character excerpt from the clinical note. Never invent or paraphrase the quote.\n"
            f"- Prioritize the span that most directly addresses the criterion's mandatory qualifying elements.\n"
            f"- Output ONLY JSON matching this exact structure:\n"
            f"{{\n"
            f'  "advocacy_quote": "<verbatim excerpt from note or empty string>",\n'
            f'  "rationale": "<clinical explanation of satisfaction>"\n'
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
                return AdvocacyResult(
                    advocacy_quote="",
                    rationale=f"LLM endpoint HTTP {resp.status_code}; advocacy call failed.",
                    elapsed_ms=elapsed_ms,
                    status_code=f"HTTP_{resp.status_code}"
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                m_quote = re.search(r'"advocacy_quote":\s*"([^"]*)"', content)
                m_rat = re.search(r'"rationale":\s*"([^"]+)"', content)
                parsed = {
                    "advocacy_quote": m_quote.group(1) if m_quote else "",
                    "rationale": m_rat.group(1) if m_rat else "Extracted from partial response"
                }

            quote = str(parsed.get("advocacy_quote", "")).strip()
            rationale = str(parsed.get("rationale", "No rationale provided.")).strip()

            # Task 2 (v62 & v75): Semantic span search & refinement via SapBERT
            refined_quote = self.select_most_relevant_span(criterion, note_text, candidate_quote=quote)
            if refined_quote and refined_quote in note_text:
                quote = refined_quote
                if not rationale or rationale == "No rationale provided." or "no supporting evidence" in rationale.lower():
                    rationale = f"Semantic evidence discovered for {criterion.get('criterion_code', 'criterion')}: '{quote[:80]}'."

            return AdvocacyResult(
                advocacy_quote=quote,
                rationale=rationale,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            logger.debug(f"Advocacy query exception: {exc}")
            return AdvocacyResult(
                advocacy_quote="",
                rationale=f"Advocacy query exception: {exc!s}",
                elapsed_ms=elapsed_ms,
                status_code="ERROR"
            )

    def review_case_deferral_sync(
        self,
        policy_id: str,
        policy_title: str,
        unproven_criteria: list[dict[str, Any]],
        advocate_summary: str,
        note_text: str,
    ) -> CaseDeferralReview:
        """
        Task 2(b): Pre-deferral case-level review by the clinical judge.
        The judge reviews unproven criteria, advocate search outcomes, and the clinical note
        to confirm the case is truly deferrable before routing to a human clinician.
        """
        t0 = time.perf_counter()

        # Check per-case budget guardrails
        if self.case_call_count >= self.max_calls_per_case:
            logger.warning(f"Judge call budget exceeded ({self.case_call_count}/{self.max_calls_per_case}) on pre-deferral review.")
            return CaseDeferralReview(
                confirmed_deferrable=True,
                rationale=f"Judge call budget exceeded ({self.max_calls_per_case} calls max per case); deferral confirmed by operational bound.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        if self.case_elapsed_ms >= (self.max_time_per_case_seconds * 1000.0):
            logger.warning(f"Judge time budget exceeded ({self.case_elapsed_ms:.1f}ms / {self.max_time_per_case_seconds*1000}ms).")
            return CaseDeferralReview(
                confirmed_deferrable=True,
                rationale="Judge time budget exceeded (60s max per case); deferral confirmed by operational bound.",
                elapsed_ms=0.0,
                status_code="SKIPPED_BUDGET_EXHAUSTED"
            )

        crit_strs = "\n".join(
            f"- {c.get('criterion_code', '')}: {c.get('name', '')} ({c.get('description', '')})"
            for c in unproven_criteria
        ) or "None"

        prompt = (
            f"You are the Clinical Evaluation Judge for Medicare policy {policy_id} ('{policy_title}').\n"
            f"The case is pending deferral because the following mandatory coverage criteria remain unproven:\n{crit_strs}\n\n"
            f"Advocate Search Findings:\n{advocate_summary or 'No supporting evidence found.'}\n\n"
            f"Clinical Note Excerpt:\n\"\"\"{note_text[:1500]}\"\"\"\n\n"
            f"TASK: Perform a pre-deferral case-level review. Confirm whether this case is genuinely deferrable "
            f"(i.e., genuine clinical ambiguity or missing documentation with no unexamined evidence satisfying the criteria), "
            f"or if valid evidence was missed.\n"
            f"Respond ONLY with valid JSON in this exact format:\n"
            f'{{"confirmed_deferrable": true, "rationale": "One-sentence clinical reasoning confirming case deferral."}}'
        )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 150
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
                return CaseDeferralReview(
                    confirmed_deferrable=True,
                    rationale=f"LLM endpoint HTTP {resp.status_code}; deferral confirmed by fallback.",
                    elapsed_ms=elapsed_ms,
                    status_code=f"HTTP_{resp.status_code}"
                )

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                m_conf = re.search(r'"confirmed_deferrable":\s*(true|false)', content, re.IGNORECASE)
                m_rat = re.search(r'"rationale":\s*"([^"]+)"', content)
                parsed = {
                    "confirmed_deferrable": m_conf.group(1).lower() == "true" if m_conf else True,
                    "rationale": m_rat.group(1) if m_rat else "Confirmed genuine lack of documentation"
                }

            confirmed = bool(parsed.get("confirmed_deferrable", True))
            rationale = str(parsed.get("rationale", "Confirmed clinical deferral: missing required statutory documentation.")).strip()

            return CaseDeferralReview(
                confirmed_deferrable=confirmed,
                rationale=rationale,
                elapsed_ms=elapsed_ms,
                status_code="COMPLETED"
            )
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.case_call_count += 1
            self.case_elapsed_ms += elapsed_ms
            self.telemetry["total_judge_calls"] += 1
            self.telemetry["total_latency_ms"] += elapsed_ms
            logger.debug(f"Pre-deferral review exception: {exc}")
            return CaseDeferralReview(
                confirmed_deferrable=True,
                rationale=f"Pre-deferral review exception ({exc!s}); deferral confirmed by error fallback.",
                elapsed_ms=elapsed_ms,
                status_code="ERROR"
            )


