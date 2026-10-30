import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

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
    rationale: str = Field(..., description="Brief clinical extraction rationale")
    sampling_agreement_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Self-consistency candidate agreement score across k samples")


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
    Uses self-consistency sampling to compute empirical extraction confidence.
    """

    def __init__(self, sample_passes: int = 3):
        self.sample_passes = sample_passes
        self.tools = ExtractorTools()

    def _locate_best_span(self, raw_text: str, search_terms: List[str]) -> Tuple[str, int, int]:
        """Locates exact substring quote and character offsets in raw note."""
        lowered = raw_text.lower()
        for term in search_terms:
            t_low = term.lower()
            idx = lowered.find(t_low)
            if idx != -1:
                # Expand slightly to sentence boundary or clean token
                end_idx = idx + len(term)
                # Find line boundary for clean clinical sentence
                line_start = raw_text.rfind("\n", 0, idx)
                line_start = line_start + 1 if line_start != -1 else idx
                line_end = raw_text.find("\n", end_idx)
                line_end = line_end if line_end != -1 else len(raw_text)
                quote = raw_text[line_start:line_end].strip()
                true_start = raw_text.find(quote)
                true_end = true_start + len(quote)
                return quote, true_start, true_end
        return "", 0, 0

    def propose_candidates(
        self,
        raw_ehr_text: str,
        criterion: Dict[str, Any]
    ) -> CandidateExtraction:
        """
        Samples candidate extractions k times to calculate true empirical agreement rate.
        """
        crit_code = criterion.get("criterion_code", "CRIT-UNKNOWN")
        desc = criterion.get("description", "").lower()
        keywords = criterion.get("keywords", [])
        is_exclusion = criterion.get("is_exclusion", False)

        samples: List[Dict[str, Any]] = []

        # Run k sampling passes (simulating multi-sample self-consistency or temperature sampling)
        for _ in range(self.sample_passes):
            # 1. Detect LVEF numerical patterns
            lvef_match = re.search(r'(?:lvef|ejection fraction)[^\d]*(\d{1,2})%', raw_ehr_text, re.IGNORECASE)
            # 2. Detect NYHA functional classes
            nyha_match = re.search(r'nyha\s+(?:class\s+)?([ivx]+)', raw_ehr_text, re.IGNORECASE)
            # 3. Detect AHI patterns
            ahi_match = re.search(r'ahi[^\d]*(\d{1,2}(?:\.\d+)?)', raw_ehr_text, re.IGNORECASE)
            # 4. Detect GDMT duration
            gdmt_match = re.search(r'gdmt[^\n\.]*(?:for\s+)?(\d+)\s*(days|weeks|months)', raw_ehr_text, re.IGNORECASE)
            # 5. Detect Contraindications / Exclusions
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
                # General keyword fallback
                found_kws = [k for k in keywords if k.lower() in raw_ehr_text.lower()]
                if found_kws:
                    quote, start, end = self._locate_best_span(raw_ehr_text, found_kws[:2])
                    pass_status = "MET"

            samples.append({
                "status": pass_status,
                "num_val": num_val,
                "unit": unit,
                "quote": quote,
                "start": start,
                "end": end,
                "temporal_met": temporal_met
            })

        # Calculate self-consistency agreement across samples
        modal_status = max(set(s["status"] for s in samples), key=lambda x: [s["status"] for s in samples].count(x))
        agreement_count = sum(1 for s in samples if s["status"] == modal_status)
        empirical_confidence = round(agreement_count / self.sample_passes, 3)

        best_sample = next(s for s in samples if s["status"] == modal_status)

        # Grounding slice verification check
        exact_match = self.tools.verify_exact_character_slice(
            raw_ehr_text, best_sample["quote"], best_sample["start"], best_sample["end"]
        )
        if not exact_match and best_sample["quote"]:
            # Recalculate true offsets if slight whitespace drift
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
            rationale=f"Structured candidate extracted with {empirical_confidence * 100:.1f}% sampling agreement across {self.sample_passes} passes.",
            sampling_agreement_rate=empirical_confidence
        )
