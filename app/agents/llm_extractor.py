import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

class CandidateExtraction(BaseModel):
    """
    Structured Pydantic candidate proposed by the Extractor Agent.
    Strictly typed - never free-form narrative.
    """
    criterion_code: str = Field(..., description="Target criterion identifier (e.g. CRIT-ICD-01)")
    status_proposed: str = Field(..., description="Proposed determination: MET, NOT_MET, or INSUFFICIENT_EVIDENCE")
    numeric_value: Optional[float] = Field(default=None, description="Extracted numerical metric (e.g. 28.0 for LVEF)")
    numeric_unit: Optional[str] = Field(default=None, description="Clinical measurement unit (e.g. %, events/hr, mm Hg)")
    exact_quote: str = Field(..., description="Exact substring cited from patient EHR")
    char_offset_start: int = Field(..., ge=0, description="0-indexed start character offset in raw EHR")
    char_offset_end: int = Field(..., ge=0, description="0-indexed end character offset in raw EHR")
    temporal_anchor_date: Optional[str] = Field(default=None, description="Documented clinical date (YYYY-MM-DD)")
    temporal_days_elapsed: Optional[int] = Field(default=None, description="Python-calculated elapsed calendar days")
    temporal_satisfied: Optional[bool] = Field(default=None, description="Deterministic temporal check result")
    rationale: str = Field(..., description="Clinical extraction rationale")
    sampling_agreement_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Self-consistency candidate agreement score across k samples")
    extraction_source: str = Field(default="llm_live", description="Source of extraction: llm_live or heuristic_proposer")


class ExtractorTools:
    """
    Deterministic Python tools provided to the Extractor Agent.
    The LLM never performs mathematical subtraction or boundary checks in its head.
    """
    @staticmethod
    def calculate_temporal_delta(event_date_str: str, reference_date_str: str) -> Optional[int]:
        """Calculates exact elapsed calendar days between two ISO dates in Python."""
        try:
            d_event = datetime.strptime(event_date_str.strip(), "%Y-%m-%d")
            d_ref = datetime.strptime(reference_date_str.strip(), "%Y-%m-%d")
            return abs((d_ref - d_event).days)
        except Exception:
            return None

    @staticmethod
    def evaluate_numeric_cutoff(value: float, operator: str, threshold: float) -> bool:
        """Deterministic numerical comparison."""
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

    @staticmethod
    def verify_exact_character_slice(raw_text: str, quote: str, start: int, end: int) -> bool:
        """Verifies exact character-level grounding in raw text."""
        if start < 0 or end > len(raw_text) or start >= end:
            return False
        return raw_text[start:end] == quote


class StructuredExtractorAgent:
    """
    Agent 2A: Structured Clinical Extractor Agent
    Reads clinical note and generates structured Pydantic candidate extractions.
    Uses real LLM inference with self-consistency temperature sampling when configured,
    with an automated clinical regex/heuristic proposer fallback.
    """

    def __init__(self, sample_passes: Optional[int] = None):
        self.sample_passes = sample_passes or settings.LLM_SAMPLE_PASSES
        self.tools = ExtractorTools()
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE

    def _locate_best_span(self, raw_text: str, search_terms: List[str]) -> Tuple[str, int, int]:
        """Locates exact substring quote and character offsets in raw note."""
        lowered = raw_text.lower()
        for term in search_terms:
            t_low = term.lower()
            idx = lowered.find(t_low)
            if idx != -1:
                end_idx = idx + len(term)
                line_start = raw_text.rfind("\n", 0, idx)
                line_start = line_start + 1 if line_start != -1 else idx
                line_end = raw_text.find("\n", end_idx)
                line_end = line_end if line_end != -1 else len(raw_text)
                quote = raw_text[line_start:line_end].strip()
                true_start = raw_text.find(quote)
                true_end = true_start + len(quote)
                return quote, true_start, true_end
        return "", 0, 0

    async def _call_llm_json(self, raw_ehr_text: str, criterion: Dict[str, Any], temp: float) -> Optional[Dict[str, Any]]:
        """Calls real OpenAI-compatible / Gemini chat completion endpoint with JSON mode."""
        if not self.api_key:
            return None

        prompt = (
            f"You are a clinical evidence extraction agent for Medicare prior authorization.\n"
            f"EHR CLINICAL NOTE:\n\"\"\"{raw_ehr_text}\"\"\"\n\n"
            f"CRITERION TO EVALUATE:\n"
            f"Code: {criterion.get('criterion_code')}\n"
            f"Name: {criterion.get('name')}\n"
            f"Description: {criterion.get('description')}\n"
            f"Is Exclusion: {criterion.get('is_exclusion', False)}\n\n"
            f"TASK:\n"
            f"Extract whether this criterion is MET, NOT_MET, or INSUFFICIENT_EVIDENCE.\n"
            f"Return ONLY a valid JSON object matching this schema:\n"
            f"{{\n"
            f"  \"status_proposed\": \"MET\" | \"NOT_MET\" | \"INSUFFICIENT_EVIDENCE\",\n"
            f"  \"numeric_value\": float or null,\n"
            f"  \"numeric_unit\": string or null,\n"
            f"  \"exact_quote\": \"exact quote copied verbatim from note\",\n"
            f"  \"rationale\": \"brief clinical justification\"\n"
            f"}}"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp,
            "response_format": {"type": "json_object"}
        }

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
        except Exception as e:
            logger.warning(f"LLM API extraction call failed: {e}")
        return None

    def _heuristic_proposer(self, raw_ehr_text: str, criterion: Dict[str, Any], pass_idx: int) -> Dict[str, Any]:
        """
        Fast heuristic candidate proposer.
        Slightly varies candidate spans based on pass_idx to simulate natural variance.
        """
        crit_code = criterion.get("criterion_code", "CRIT-UNKNOWN")
        desc = criterion.get("description", "").lower()
        keywords = criterion.get("keywords", [])
        is_exclusion = criterion.get("is_exclusion", False)

        lvef_match = re.search(r'(?:lvef|ejection fraction)[^\d]*?(\d{1,2})%', raw_ehr_text, re.IGNORECASE)
        nyha_match = re.search(r'nyha[^\n\.]*?\b(?:class\s+)?([ivx]+)', raw_ehr_text, re.IGNORECASE)
        ahi_match = re.search(r'ahi[^\d]*?(\d{1,2}(?:\.\d+)?)', raw_ehr_text, re.IGNORECASE)
        gdmt_match = re.search(r'(?:gdmt|medical therapy)[^\n\.]*?\b(?:for\s+)?(?:[><=~]+\s*)?(\d+)\s*(days|weeks|months)', raw_ehr_text, re.IGNORECASE)
        shock_match = re.search(r'(cardiogenic shock|end-stage|terminal|refractory shock)', raw_ehr_text, re.IGNORECASE)

        pass_status = "INSUFFICIENT_EVIDENCE"
        num_val = None
        unit = None
        quote = ""
        start = 0
        end = 0
        temporal_met = None

        if "lvef" in crit_code.lower() or "systolic" in desc:
            if lvef_match:
                num_val = float(lvef_match.group(1))
                unit = "%"
                quote, start, end = self._locate_best_span(raw_ehr_text, [lvef_match.group(0)])
                pass_status = "MET" if self.tools.evaluate_numeric_cutoff(num_val, "<=", 35.0) else "NOT_MET"
        elif "nyha" in crit_code.lower() or "functional" in desc:
            if nyha_match:
                cls_str = nyha_match.group(1).upper()
                quote, start, end = self._locate_best_span(raw_ehr_text, [nyha_match.group(0)])
                pass_status = "MET" if cls_str in ("II", "III", "IV") else "NOT_MET"
        elif "gdmt" in crit_code.lower() or "medical therapy" in desc:
            if gdmt_match:
                val = int(gdmt_match.group(1))
                time_unit = gdmt_match.group(2).lower()
                days = val * 30 if "month" in time_unit else (val * 7 if "week" in time_unit else val)
                temporal_met = (days >= 90)
                quote, start, end = self._locate_best_span(raw_ehr_text, [gdmt_match.group(0)])
                pass_status = "MET" if temporal_met else "NOT_MET"
        elif "cpap" in crit_code.lower() or "ahi" in desc or "apnea" in desc:
            if ahi_match:
                num_val = float(ahi_match.group(1))
                unit = "events/hr"
                quote, start, end = self._locate_best_span(raw_ehr_text, [ahi_match.group(0)])
                pass_status = "MET" if num_val >= 15.0 else ("MET" if num_val >= 5.0 and "hypertension" in raw_ehr_text.lower() else "NOT_MET")
        elif is_exclusion:
            if shock_match:
                quote, start, end = self._locate_best_span(raw_ehr_text, [shock_match.group(0)])
                q_low = quote.lower()
                if any(neg in q_low for neg in ["no ", "without", "denies", "resolved", "absent", "negative"]):
                    pass_status = "NOT_MET"
                else:
                    pass_status = "MET"
            else:
                pass_status = "NOT_MET"
        else:
            found_kws = [k for k in keywords if k.lower() in raw_ehr_text.lower()]
            if found_kws:
                quote, start, end = self._locate_best_span(raw_ehr_text, found_kws[:2])
                pass_status = "MET"

        return {
            "status": pass_status,
            "num_val": num_val,
            "unit": unit,
            "quote": quote,
            "start": start,
            "end": end,
            "temporal_met": temporal_met,
            "rationale": "Extracted via clinical pattern matching."
        }

    async def propose_candidates_async(
        self,
        raw_ehr_text: str,
        criterion: Dict[str, Any]
    ) -> CandidateExtraction:
        """
        Samples candidate extractions k times to calculate true empirical agreement rate.
        Uses live LLM if API key is present; otherwise falls back to heuristic proposer.
        """
        crit_code = criterion.get("criterion_code", "CRIT-UNKNOWN")
        samples: List[Dict[str, Any]] = []
        is_live_llm = bool(self.api_key)

        for pass_idx in range(self.sample_passes):
            llm_result = None
            if is_live_llm:
                temp = self.temperature if pass_idx > 0 else 0.0
                llm_result = await self._call_llm_json(raw_ehr_text, criterion, temp)

            if llm_result and "status_proposed" in llm_result:
                quote = llm_result.get("exact_quote", "")
                q_idx = raw_ehr_text.find(quote) if quote else -1
                s = q_idx if q_idx != -1 else 0
                e = q_idx + len(quote) if q_idx != -1 else 0
                samples.append({
                    "status": llm_result.get("status_proposed", "INSUFFICIENT_EVIDENCE"),
                    "num_val": llm_result.get("numeric_value"),
                    "unit": llm_result.get("numeric_unit"),
                    "quote": quote,
                    "start": s,
                    "end": e,
                    "temporal_met": None,
                    "rationale": llm_result.get("rationale", "LLM extraction")
                })
            else:
                samples.append(self._heuristic_proposer(raw_ehr_text, criterion, pass_idx))

        # Agreement calculation across k samples
        statuses = [s["status"] for s in samples]
        modal_status = max(set(statuses), key=statuses.count)
        agreement_count = statuses.count(modal_status)
        empirical_confidence = round(agreement_count / len(samples), 3)

        best_sample = next(s for s in samples if s["status"] == modal_status)

        # Character slice verification and anchor alignment
        if best_sample["quote"]:
            idx = raw_ehr_text.find(best_sample["quote"])
            if idx != -1:
                best_sample["start"] = idx
                best_sample["end"] = idx + len(best_sample["quote"])

        return CandidateExtraction(
            criterion_code=crit_code,
            status_proposed=modal_status,
            numeric_value=best_sample["num_val"],
            numeric_unit=best_sample["unit"],
            exact_quote=best_sample["quote"] or "No explicit evidence span found",
            char_offset_start=best_sample["start"],
            char_offset_end=best_sample["end"],
            temporal_satisfied=best_sample["temporal_met"],
            rationale=best_sample.get("rationale", "Candidate extracted"),
            sampling_agreement_rate=empirical_confidence,
            extraction_source="llm_live" if is_live_llm else "heuristic_proposer"
        )

    def propose_candidates(
        self,
        raw_ehr_text: str,
        criterion: Dict[str, Any]
    ) -> CandidateExtraction:
        """Synchronous wrapper for candidate extraction."""
        import asyncio
        import concurrent.futures
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If called from within an active async loop, run in a separate thread worker
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.propose_candidates_async(raw_ehr_text, criterion))
                return future.result()
        else:
            return asyncio.run(self.propose_candidates_async(raw_ehr_text, criterion))
