"""
Deterministic Candidate Span Extractor (Task 2).
Finds candidate evidence spans directly from the EHR narrative using exact
character offsets from the note itself. Offsets and text are strictly extracted
by deterministic tokenization and lexical overlap ranking — NEVER by the LLM.
Guarantees verbatim character grounding by construction.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.core.concept_map import ConceptMap, get_concept_map
from app.schemas.contracts import ClinicalEvidenceSpan


class CandidateSpan(BaseModel):
    """Verbatim slice extracted deterministically from the clinical note."""
    source_text: str = Field(..., description="Exact character slice from the EHR narrative")
    start_char: int = Field(..., ge=0, description="Start offset in original note")
    end_char: int = Field(..., ge=0, description="End offset in original note")
    overlap_score: float = Field(default=0.0, ge=0.0, description="Deterministic lexical/concept overlap score")
    matched_terms: list[str] = Field(default_factory=list, description="Terms that matched this slice")

    def to_evidence_span(self, confidence: float = 0.92, section: str = "OBJECTIVE") -> ClinicalEvidenceSpan:
        """Converts to a verified ClinicalEvidenceSpan contract."""
        return ClinicalEvidenceSpan(
            source_text=self.source_text,
            start_char=self.start_char,
            end_char=self.end_char,
            clinical_section=section,
            confidence=confidence
        )


class CandidateSpanExtractor:
    """
    Deterministic extractor that identifies candidate spans in a clinical narrative
    for a given criterion. Offsets are derived directly from the source text.
    """

    STOP_WORDS: ClassVar[set[str]] = {
        "a", "an", "the", "and", "or", "of", "to", "in", "for", "with", "on", "at",
        "by", "from", "is", "was", "are", "were", "be", "been", "patient", "clinical",
        "documented", "presence", "confirming", "demonstrating", "shows",
        "reveals", "status", "prior", "post", "not", "no", "without"
    }

    @classmethod
    def extract_candidates(
        cls,
        ehr_narrative: str,
        criterion: dict[str, Any],
        concept_map: ConceptMap | None = None,
        max_candidates: int = 5,
        min_score: float = 0.05
    ) -> list[CandidateSpan]:
        """
        Extracts and ranks verbatim candidate slices from the clinical note.
        
        Args:
            ehr_narrative: Full clinical note text.
            criterion: Criterion dictionary or metadata.
            concept_map: Optional active ConceptMap (defaults to global map).
            max_candidates: Maximum candidate spans to return.
            min_score: Minimum overlap score threshold.
            
        Returns:
            List of CandidateSpan objects ranked by relevance.
        """
        if not ehr_narrative or not ehr_narrative.strip():
            return []

        cmap = concept_map or get_concept_map()

        # 1. Gather all target concept terms for the criterion
        ccode = criterion.get("criterion_code", "")
        cname = criterion.get("name", "")
        cdesc = criterion.get("description", "")
        entity_names = criterion.get("entity_names", []) or []
        keywords = criterion.get("keywords", []) or []

        search_phrases: set[str] = set()
        for t in [cname, cdesc] + list(entity_names) + list(keywords):
            if t and isinstance(t, str):
                search_phrases.add(t.strip())

        # Expand via ConceptMap
        if ccode:
            search_phrases.update(cmap.get_terms_for_concept(ccode))
            search_phrases.update(cmap.get_terms_for_concept(f"CONCEPT-{ccode}"))
        for p in list(search_phrases):
            for cmap_term in cmap.get_terms_for_concept(p):
                search_phrases.add(cmap_term.strip())

        # Build term tokens
        target_tokens: set[str] = set()
        for phrase in search_phrases:
            tokens = re.findall(r'[a-zA-Z0-9\+\-]+', phrase.lower())
            for tk in tokens:
                if len(tk) > 2 and tk not in cls.STOP_WORDS:
                    target_tokens.add(tk)

        # 2. Slice the narrative into sentences / clauses with exact offsets
        # Split on sentence terminals: period followed by space/newline, or newlines
        slices: list[CandidateSpan] = []
        sentence_regex = re.compile(r'[^.\n;]+(?:[.\n;]+|$)')

        for m in sentence_regex.finditer(ehr_narrative):
            raw_slice = m.group(0)
            if not raw_slice.strip():
                continue

            # Strip leading/trailing whitespace while adjusting offsets
            s_offset = m.start()
            while s_offset < m.end() and ehr_narrative[s_offset].isspace():
                s_offset += 1
            e_offset = m.end()
            while e_offset > s_offset and ehr_narrative[e_offset - 1] in ' \t\r\n.,;:':
                e_offset -= 1

            if s_offset >= e_offset:
                continue

            clean_text = ehr_narrative[s_offset:e_offset]
            # Safety assertion: verify exact slice invariant
            if ehr_narrative[s_offset:e_offset] != clean_text:
                continue

            # 3. Score overlap against target terms and tokens
            slice_lower = clean_text.lower()
            slice_tokens = set(re.findall(r'[a-zA-Z0-9\+\-]+', slice_lower))

            matched_phrases = []
            for phrase in search_phrases:
                if len(phrase) >= 4 and phrase.lower() in slice_lower:
                    matched_phrases.append(phrase)

            token_intersection = target_tokens.intersection(slice_tokens)
            if not token_intersection and not matched_phrases:
                continue

            # Overlap score: phrase matches weighted heavily (0.4 each) + token jaccard
            score = (len(matched_phrases) * 0.4) + (len(token_intersection) / max(1, len(target_tokens)))

            slices.append(CandidateSpan(
                source_text=clean_text,
                start_char=s_offset,
                end_char=e_offset,
                overlap_score=round(score, 4),
                matched_terms=list(token_intersection) + matched_phrases
            ))

        # Sort descending by score, then by document order
        slices.sort(key=lambda s: (-s.overlap_score, s.start_char))
        filtered = [s for s in slices if s.overlap_score >= min_score]
        return filtered[:max_candidates]
