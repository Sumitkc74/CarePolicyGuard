"""
Policy Shortlist Service (Task 1, Task 2, Task 3).
Provides deterministic, criteria-grounded shortlist ranking of candidate Medicare policies.

Combines lexical BM25 and dense keyword signals from HybridPolicyRetriever with
hand-weighted title, category, and criteria keyword signals from PolicyRetrievalAgent
into one unified candidate ranking, reranks by deterministic criteria coverage,
and applies an explicit margin rule for clinician pre-selection vs manual choice.
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.agents.policy_retriever import PolicyRetrievalAgent
from app.services.declarative_engine import DeclarativePolicyEngine
from app.services.hybrid_retriever import HybridPolicyRetriever


class PolicyShortlistService:
    """
    Unified Medicare Policy Shortlist and Margin Pre-Selection Engine.

    OPERATING CHOICES (Honest Uncalibrated Operating Thresholds):
    - SCORE_MARGIN_THRESHOLD (0.08): Uncalibrated operating choice defining the
      minimum score separation between candidate #1 and candidate #2 required to
      permit automated pre-selection. If the margin is narrower, the system classifies
      the case as a close call and requires manual clinician selection.
    - MIN_PRESELECT_COVERAGE_RATIO (0.33): Uncalibrated operating choice requiring
      candidate #1 to have clinical evidence supporting at least 33% of its statutory
      criteria (and at least 1 criterion) before automated pre-selection is allowed.
    - MIN_RELEVANCE_FLOOR (0.15): Minimum unified relevance score required for a policy
      to be eligible for inclusion on the clinician's shortlist.
    - MAX_SHORTLIST_SIZE (5): Maximum candidate policies displayed on the shortlist.
    - MIN_SHORTLIST_SIZE (3): Recommended display floor for UI shortlist rendering when
      sufficient candidates clear the relevance floor.
    - Single-Candidate Rule: When exactly 1 candidate qualifies, margin is set to 1.0
      (uncontested). Pre-selection requires satisfying MIN_PRESELECT_COVERAGE_RATIO (0.33)
      and supported_criteria_count >= 1; otherwise defaults to SELECTION_REQUIRED.
    """

    SCORE_MARGIN_THRESHOLD: float = 0.08
    MIN_PRESELECT_COVERAGE_RATIO: float = 0.33
    MIN_RELEVANCE_FLOOR: float = 0.15
    MAX_SHORTLIST_SIZE: int = 5
    MIN_SHORTLIST_SIZE: int = 3

    @classmethod
    def compute_shortlist(
        cls,
        ehr_narrative: str,
        db: Session | None = None,
        top_k: int = 5
    ) -> dict[str, Any]:
        """
        Executes unified candidate scoring, criteria-coverage reranking, and margin evaluation.

        Returns structured dict matching PolicyShortlistResponse schema:
        - status: 'PRESELECTED' | 'SELECTION_REQUIRED' | 'NO_GOVERNING_POLICY'
        - preselected_policy_id: Optional[str]
        - preselected_policy_title: Optional[str]
        - preselection_margin: Optional[float]
        - preselection_coverage_ratio: Optional[float]
        - shortlist: List[Dict[str, Any]] (rank, policy_id, title, scores, coverage, matching_phrases)
        - message: str
        - margin_threshold: float
        - coverage_floor: float
        - execution_time_ms: float
        """
        start_time = time.perf_counter()
        cleaned_text = (ehr_narrative or "").strip()

        if not cleaned_text:
            return {
                "status": "NO_GOVERNING_POLICY",
                "preselected_policy_id": None,
                "preselected_policy_title": None,
                "preselection_margin": None,
                "preselection_coverage_ratio": None,
                "shortlist": [],
                "candidates": [],
                "score_margin": None,
                "runner_up_policy_id": None,
                "message": "Empty clinical narrative provided.",
                "margin_threshold": cls.SCORE_MARGIN_THRESHOLD,
                "coverage_floor": cls.MIN_PRESELECT_COVERAGE_RATIO,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
            }

        # ---------------------------------------------------------------------
        # 1. Unified Candidate Scoring (Task 1)
        # Combines Scorer 1 (HybridPolicyRetriever: BM25 + Dense Keyword RRF)
        # and Scorer 2 (PolicyRetrievalAgent: title, category, criteria keywords, taxonomy)
        # ---------------------------------------------------------------------
        hybrid_retriever = HybridPolicyRetriever(db=db)
        policy_retriever = PolicyRetrievalAgent(db=db)

        # Scorer 1: Hybrid retriever (top 30 candidate chunks)
        res_hr = hybrid_retriever.retrieve_hybrid(cleaned_text, top_k=30)
        max_hr_score = max((r.get("rrf_score", 0.0) for r in res_hr), default=1.0)
        if max_hr_score <= 0:
            max_hr_score = 1.0

        hr_ranks: dict[str, int] = {}
        hr_norm_scores: dict[str, float] = {}
        for rank, r in enumerate(res_hr, 1):
            pid = r["policy_id"]
            hr_ranks[pid] = rank
            hr_norm_scores[pid] = r.get("rrf_score", 0.0) / max_hr_score

        # Scorer 2: PolicyRetrievalAgent lexical/semantic narrative scoring
        res_pra = policy_retriever.search_policies_by_narrative(cleaned_text)
        pra_ranks: dict[str, int] = {}
        pra_norm_scores: dict[str, float] = {}
        pra_matched_terms: dict[str, list[str]] = {}

        for rank, r in enumerate(res_pra, 1):
            pid = r["policy_id"]
            rel = r.get("relevance_score", 0.0)
            if rel > 0:
                pra_ranks[pid] = rank
                pra_norm_scores[pid] = rel
                pra_matched_terms[pid] = r.get("matched_terms", [])

        # Candidate pool: union of all retrieved policies
        candidate_pids = set(hr_ranks.keys()) | set(pra_ranks.keys())
        if not candidate_pids:
            return {
                "status": "NO_GOVERNING_POLICY",
                "preselected_policy_id": None,
                "preselected_policy_title": None,
                "preselection_margin": None,
                "preselection_coverage_ratio": None,
                "shortlist": [],
                "candidates": [],
                "score_margin": None,
                "runner_up_policy_id": None,
                "message": "No governing Medicare policy matches this clinical record with sufficient evidence.",
                "margin_threshold": cls.SCORE_MARGIN_THRESHOLD,
                "coverage_floor": cls.MIN_PRESELECT_COVERAGE_RATIO,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
            }

        # Stated Combination Rule (Task 1):
        # We compute Reciprocal Rank Fusion (c=60) over both ranks:
        # RRF(p) = 1/(60 + r1) + 1/(60 + r2)
        # Scaled to [0, 1] relative to theoretical max RRF (2 / 61 = 0.0328).
        # Unified Score = 0.50 * RRF_norm + 0.25 * norm_score_hr + 0.25 * norm_score_pra
        unified_candidates = []
        for pid in candidate_pids:
            r1 = hr_ranks.get(pid, 60)
            r2 = pra_ranks.get(pid, 60)
            s1 = hr_norm_scores.get(pid, 0.0)
            s2 = pra_norm_scores.get(pid, 0.0)

            # If neither retriever found an actual match (s1 <= 0.02 and s2 == 0.0),
            # this candidate is background noise and gets zero unified score.
            if s1 <= 0.02 and s2 == 0.0:
                unified_score = 0.0
            else:
                rrf = (1.0 / (60.0 + r1)) + (1.0 / (60.0 + r2))
                rrf_norm = min(1.0, rrf / (2.0 / 61.0))
                unified_score = round(0.50 * rrf_norm + 0.25 * s1 + 0.25 * s2, 4)

            unified_candidates.append({
                "policy_id": pid,
                "unified_score": unified_score,
                "hr_rank": r1,
                "pra_rank": r2,
                "pra_terms": pra_matched_terms.get(pid, [])
            })

        unified_candidates.sort(key=lambda x: x["unified_score"], reverse=True)

        # ---------------------------------------------------------------------
        # 2. Criteria-Coverage Reranking and Matching Phrases (Task 2)
        # ---------------------------------------------------------------------
        evaluated_candidates = []
        low_text = cleaned_text.lower()

        for cand in unified_candidates[:15]:
            pid = cand["policy_id"]
            u_score = cand["unified_score"]
            if u_score < cls.MIN_RELEVANCE_FLOOR:
                continue

            policy_obj = DeclarativePolicyEngine.load_policy(pid)
            supported_criteria_count = 0
            total_criteria_count = 0
            matching_phrases: list[str] = []
            seen_phrases = set()

            if policy_obj:
                non_exclusions = [c for c in policy_obj.criteria if not c.is_exclusion]
                total_criteria_count = len(non_exclusions)

                for crit in policy_obj.criteria:
                    assessment = DeclarativePolicyEngine.evaluate(crit, cleaned_text)
                    if assessment.verified_spans:
                        if not crit.is_exclusion:
                            supported_criteria_count += 1
                        for sp in assessment.verified_spans:
                            text_snippet = sp.source_text.strip()
                            if text_snippet and text_snippet.lower() not in seen_phrases:
                                seen_phrases.add(text_snippet.lower())
                                matching_phrases.append(text_snippet)

            # Supplement matching phrases with matched clinical taxonomy / procedure terms
            for term in cand["pra_terms"]:
                clean_term = term.strip()
                if clean_term and clean_term.lower() in low_text and clean_term.lower() not in seen_phrases:
                    # Find exact case from original text
                    m = re.search(r'\b' + re.escape(clean_term) + r'\b', cleaned_text, re.IGNORECASE)
                    if m:
                        exact_snippet = m.group(0)
                        seen_phrases.add(clean_term.lower())
                        matching_phrases.append(exact_snippet)

            # TASK 2 BINDING RULE:
            # An entry with no quoted matching phrase from the note is dropped, not shown with an empty reason.
            if not matching_phrases:
                continue

            coverage_ratio = (supported_criteria_count / max(1, total_criteria_count)) if total_criteria_count > 0 else 0.0

            # Coverage Reranking Formula:
            # Baseline score preserves lexical relevance (0.85 floor), boosted up to +30% for high criteria coverage
            reranked_score = round(u_score * (0.85 + 0.30 * coverage_ratio), 4)

            # 0-Coverage Demotion Rule (Soft 0.85 Multiplier):
            # A candidate whose title/text matches lexically but whose criteria coverage is 0
            # receives a soft demotion via the (0.85 + 0.30 * 0) = 0.85 multiplier (a 15% penalty),
            # while candidates with higher coverage receive up to a 1.15 multiplier (+15% boost).
            # This demotes 0-coverage candidates below moderately matching candidates with verified criteria,
            # while preserving the candidate's unified score and explicit coverage display.
            coverage_display = f"{supported_criteria_count} of {total_criteria_count} criteria have supporting text"

            pol_title = getattr(policy_obj, "title", pid) if policy_obj else pid

            evaluated_candidates.append({
                "policy_id": pid,
                "policy_title": pol_title,
                "unified_score": u_score,
                "reranked_score": reranked_score,
                "coverage_display": coverage_display,
                "supported_criteria_count": supported_criteria_count,
                "total_criteria_count": total_criteria_count,
                "coverage_ratio": round(coverage_ratio, 3),
                "matching_phrases": matching_phrases[:6]
            })

        # Sort: Primary by reranked_score, secondary by coverage_ratio
        evaluated_candidates.sort(key=lambda x: (x["reranked_score"], x["coverage_ratio"]), reverse=True)

        # Shortlist sizing: top_k qualifying candidates
        shortlist_size = min(max(1, top_k), len(evaluated_candidates))
        selected_candidates = evaluated_candidates[:shortlist_size]

        # Re-assign sequential 1-based ranks
        shortlist: list[dict[str, Any]] = []
        for i, c in enumerate(selected_candidates, 1):
            c_copy = dict(c)
            c_copy["rank"] = i
            shortlist.append(c_copy)

        # ---------------------------------------------------------------------
        # 3. Margin Rule and Pre-Selection Logic (Task 3)
        # ---------------------------------------------------------------------
        no_candidates = len(shortlist) == 0

        if no_candidates:
            return {
                "status": "NO_GOVERNING_POLICY",
                "preselected_policy_id": None,
                "preselected_policy_title": None,
                "preselection_margin": None,
                "preselection_coverage_ratio": None,
                "shortlist": [],
                "candidates": [],
                "score_margin": None,
                "runner_up_policy_id": None,
                "message": "No governing Medicare policy matches this clinical record with sufficient evidence. Please review documentation or select manually.",
                "margin_threshold": cls.SCORE_MARGIN_THRESHOLD,
                "coverage_floor": cls.MIN_PRESELECT_COVERAGE_RATIO,
                "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
            }

        top_cand = shortlist[0]
        margin: float | None = None
        margin_satisfied = False

        if len(shortlist) == 1:
            margin = 1.0
            margin_satisfied = True
        else:
            second_cand = shortlist[1]
            margin = round(top_cand["reranked_score"] - second_cand["reranked_score"], 4)
            margin_satisfied = margin >= cls.SCORE_MARGIN_THRESHOLD

        coverage_satisfied = (
            top_cand["coverage_ratio"] >= cls.MIN_PRESELECT_COVERAGE_RATIO
            and top_cand["supported_criteria_count"] >= 1
        )

        if margin_satisfied and coverage_satisfied:
            status = "PRESELECTED"
            preselected_policy_id = top_cand["policy_id"]
            preselected_policy_title = top_cand["policy_title"]
            message = f"Policy {preselected_policy_id} pre-selected with confident margin ({margin:.3f}) and criteria coverage ({top_cand['coverage_display']})."
        else:
            status = "SELECTION_REQUIRED"
            preselected_policy_id = None
            preselected_policy_title = None
            if not coverage_satisfied:
                message = f"Clinician selection required: Top candidate ({top_cand['policy_id']}) criteria coverage ({top_cand['coverage_display']}) is below confidence threshold ({cls.MIN_PRESELECT_COVERAGE_RATIO*100:.0f}%)."
            else:
                message = f"Clinician selection required: Close match between top candidates ({top_cand['policy_id']} vs {shortlist[1]['policy_id']}, margin {margin:.3f} < {cls.SCORE_MARGIN_THRESHOLD})."

        return {
            "status": status,
            "preselected_policy_id": preselected_policy_id,
            "preselected_policy_title": preselected_policy_title,
            "preselection_margin": margin,
            "preselection_coverage_ratio": top_cand["coverage_ratio"],
            "shortlist": shortlist,
            "candidates": shortlist,
            "score_margin": margin,
            "runner_up_policy_id": shortlist[1]["policy_id"] if len(shortlist) > 1 else None,
            "message": message,
            "margin_threshold": cls.SCORE_MARGIN_THRESHOLD,
            "coverage_floor": cls.MIN_PRESELECT_COVERAGE_RATIO,
            "execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
        }
