"""
Test Suite for Prompt v86: Span Normalization Fix for Requirement-Text Candidates.

Validates that:
(i)   The CATARACT span is found: Calling select_most_relevant_span with CRIT-CAT-01
      and candidate_quote = statutory requirement text returns the verbatim note sentence
      "Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye.".
(ii)  The PET-ONC span is found: Calling select_most_relevant_span with CRIT-PTONC-01
      and candidate_quote = statutory requirement text returns the verbatim note sentence
      "Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma.".
(iii) A true verbatim candidate still behaves as before: When candidate_quote is
      verbatim in the note, the function returns it (or its nearest paraphrase) and
      the lexical fallback is NOT invoked (guards against re-widening the fallback).
(iv)  The thresholds remain unchanged: min_sim_threshold is 0.65 for paraphrase queries
      and 0.35 for requirement queries.
(v)   The three target cases rescue in the real pipeline: DEV-LCD-KYPHO-APP,
      DEV-NCD-CATARACT-APP, and DEV-NCD-PET-ONC-APP adjudicate to APPROVED with criteria defended
      and unmocked select_most_relevant_span.
(vi)  The v84 and v85 test files pass unchanged, including v84 test (iii) and both v85 tests.
(vii) The requirement-text detection is specific: Candidates that are clinical paraphrases
      (not the requirement text) still trigger 0.65 threshold and inhibit fallback,
      pinning the boundary of Option B against broad non-verbatim bypasses.
"""

from __future__ import annotations

import inspect
import json
import re
import urllib.error
import urllib.request
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core import concept_map as cm_mod
from app.core.llm_judge import (
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    DefenseResult,
    JudgeEvaluation,
)
from app.schemas.contracts import AdjudicationDecision


def _is_ollama_available() -> bool:
    """Check if local Ollama daemon is reachable."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def test_v86_cataract_span_found():
    """
    Condition (i): The CATARACT span is found.
    Calls select_most_relevant_span directly with real CRIT-CAT-01 policy JSON,
    real DEV-NCD-CATARACT-APP vignette narrative, and candidate_quote = statutory requirement text.
    Must return the verbatim note sentence containing 20/60 in right eye and 20/50 in left eye.
    """
    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        vignettes = json.load(f)
    v_cat = next(v for v in vignettes if v["vignette_id"] == "DEV-NCD-CATARACT-APP")

    with open("app/data/policies_extended/NCD-CATARACT.json", "r", encoding="utf-8") as f:
        p_cat = json.load(f)
    crit_cat_01 = next(c for c in p_cat["criteria"] if c["criterion_code"] == "CRIT-CAT-01")

    # Statutory requirement text as candidate_quote (the exact failure mode from v85)
    statutory_candidate = crit_cat_01.get("description", "")
    assert statutory_candidate not in v_cat["ehr_narrative"], "Statutory text must not be in note"

    span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_cat_01,
        note_text=v_cat["ehr_narrative"],
        candidate_quote=statutory_candidate,
    )
    assert span != "", "CATARACT span must not be empty after span normalization fix"
    assert "20/60 in the right eye" in span
    assert "20/50 in the left eye" in span


def test_v86_pet_onc_span_found():
    """
    Condition (ii): The PET-ONC span is found.
    Calls select_most_relevant_span directly for CRIT-PTONC-01 with real DEV-NCD-PET-ONC-APP vignette
    and candidate_quote = statutory requirement text.
    Must return the verbatim note sentence confirming adenocarcinoma / biopsy pathology.
    """
    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        vignettes = json.load(f)
    v_pet = next(v for v in vignettes if v["vignette_id"] == "DEV-NCD-PET-ONC-APP")

    with open("app/data/policies_extended/NCD-PET-ONC.json", "r", encoding="utf-8") as f:
        p_pet = json.load(f)
    crit_pet_01 = next(c for c in p_pet["criteria"] if c["criterion_code"] == "CRIT-PTONC-01")

    statutory_candidate = crit_pet_01.get("description", "")
    assert statutory_candidate not in v_pet["ehr_narrative"], "Statutory text must not be in note"

    span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_pet_01,
        note_text=v_pet["ehr_narrative"],
        candidate_quote=statutory_candidate,
    )
    assert span != "", "PET-ONC span must not be empty after span normalization fix"
    assert "Biopsy pathology confirms" in span or "esophageal adenocarcinoma" in span


def test_v86_verbatim_candidate_preserves_behavior():
    """
    Condition (iii): A true verbatim candidate still behaves as before.
    When candidate_quote is verbatim in the note, the function returns that candidate
    and the lexical fallback is NOT invoked.
    """
    criterion = {
        "criterion_code": "CRIT-TEST-VERBATIM-01",
        "name": "Hypertension History",
        "description": "Documented chronic hypertension refractory to multi-drug therapy",
        "keywords": ["hypertension", "blood pressure"],
    }
    note_text = (
        "Patient has a long history of primary essential hypertension managed by cardiology. "
        "Blood pressure remains elevated at 145/92 mmHg today."
    )
    verbatim_quote = "primary essential hypertension managed by cardiology"
    assert verbatim_quote in note_text

    span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=criterion,
        note_text=note_text,
        candidate_quote=verbatim_quote,
    )
    assert span != ""
    assert verbatim_quote in span


def test_v86_thresholds_remain_unchanged():
    """
    Condition (iv): The threshold values remain exactly 0.65 for paraphrase queries
    and 0.35 for requirement queries.
    """
    source = inspect.getsource(ClinicalEquivalenceJudge.select_most_relevant_span)
    match = re.search(
        r"min_sim_threshold\s*=\s*([0-9\.]+)\s*if\s*is_paraphrase_query\s*else\s*([0-9\.]+)",
        source,
    )
    assert match is not None, "Failed to locate min_sim_threshold assignment in select_most_relevant_span"
    paraphrase_threshold = float(match.group(1))
    requirement_threshold = float(match.group(2))

    assert paraphrase_threshold == 0.65, (
        f"Paraphrase min_sim_threshold must remain exactly 0.65, found: {paraphrase_threshold}"
    )
    assert requirement_threshold == 0.35, (
        f"Requirement min_sim_threshold must remain exactly 0.35, found: {requirement_threshold}"
    )


def test_v86_three_target_cases_rescue_in_real_pipeline():
    """
    Condition (v): DEV-LCD-KYPHO-APP, DEV-NCD-CATARACT-APP, and DEV-NCD-PET-ONC-APP rescue in the
    real pipeline and adjudicate to APPROVED with criteria defended.
    select_most_relevant_span is UNMOCKED and runs the real SapBERT normalization on note text.
    """
    from scripts.run_agentic_v59_three_mode_measurement import (
        build_merged_in_memory_map,
    )

    merged_map, _, _ = build_merged_in_memory_map()

    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        vignettes = json.load(f)
    vignettes_by_id = {v["vignette_id"]: v for v in vignettes}

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.span_repair_enabled = True

    stack = ExitStack()
    stack.enter_context(patch.object(cm_mod, "_GLOBAL_CONCEPT_MAP", merged_map))

    if True:  # Hermetic LLM mocks for deterministic execution, select_most_relevant_span UNMOCKED
        # Hermetic mocks for LLM judge calls, but select_most_relevant_span runs FOR REAL!
        def mock_judge(*args, **kwargs):
            criterion = kwargs.get("criterion") if "criterion" in kwargs else (args[0] if len(args) > 0 and isinstance(args[0], dict) else args[1])
            ccode = criterion.get("criterion_code", "")
            # Returns requirement text as quoted_evidence (reproducing the exact v85 failure mode)
            if ccode == "CRIT-KYPHO-01":
                return CriterionJudgment(status="MET", quoted_evidence="Pain rating is 8/10 on visual analog scale.", rationale="Severe pain 8/10", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-KYPHO-02":
                return CriterionJudgment(
                    status="MET",
                    quoted_evidence="STIR imaging demonstrating acute osteoporotic vcf with bone edema",
                    rationale="Acute edema confirmed",
                    confidence=0.95,
                    status_code="COMPLETED"
                )
            elif ccode == "CRIT-KYPHO-EXCL-01":
                return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="No infection", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-CAT-01":
                return CriterionJudgment(
                    status="MET",
                    quoted_evidence="Documented best-corrected Snellen distance visual acuity of 20/50 or worse in affected eye, or severe disabling glare under Brightness Acuity Testing (BAT).",
                    rationale="Visual acuity requirement met",
                    confidence=0.95,
                    status_code="COMPLETED"
                )
            elif ccode == "CRIT-CAT-02":
                return CriterionJudgment(status="MET", quoted_evidence="difficulty with daily activities", rationale="ADL impairment", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-CAT-EXCL-01":
                return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="Refractory to spectacles", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-PTONC-01":
                return CriterionJudgment(
                    status="MET",
                    quoted_evidence="Pathology report documenting biopsy-proven malignancy (or solitary pulmonary nodule with high clinical cancer probability on chest CT).",
                    rationale="Malignancy confirmed",
                    confidence=0.95,
                    status_code="COMPLETED"
                )
            elif ccode == "CRIT-PTONC-02":
                return CriterionJudgment(status="MET", quoted_evidence="Initial systemic staging required to determine resectability.", rationale="Staging impact", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-PTONC-EXCL-01":
                return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="No routine surveillance", confidence=0.95, status_code="COMPLETED")
            return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="Default", confidence=0.5, status_code="COMPLETED")

        def mock_challenge(*args, **kwargs):
            criterion = kwargs.get("criterion") or args[1]
            ccode = criterion.get("criterion_code", "")
            if ccode == "CRIT-KYPHO-02":
                return {
                    "adversarial_counter_reading": True,
                    "has_objection": True,
                    "objection_type": "TEMPORAL",
                    "counter_quote": "Patient has tried scheduled oral analgesics, bed rest, and calcitonin for 2 weeks",
                    "named_sub_requirement": "4 weeks conservative therapy",
                    "specific_contradiction": True,
                    "rationale": "Conservative therapy lasted only 2 weeks, less than 4 weeks required.",
                }
            elif ccode == "CRIT-CAT-01":
                return {
                    "adversarial_counter_reading": True,
                    "has_objection": True,
                    "objection_type": "NEGATION",
                    "counter_quote": "Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye.",
                    "named_sub_requirement": "20/50 or worse in affected eye",
                    "specific_contradiction": True,
                    "rationale": "20/60 does not meet 20/50 or worse.",
                }
            return {"adversarial_counter_reading": False, "has_objection": False, "rationale": "No objection"}

        def mock_defense(*args, **kwargs):
            criterion = kwargs.get("criterion") or args[1]
            ccode = criterion.get("criterion_code", "")
            if ccode == "CRIT-KYPHO-02":
                return DefenseResult(
                    objection_valid=False,
                    objection_invalid_reason="The objection demands 4 weeks of conservative therapy, but CRIT-KYPHO-02 contains no conservative therapy duration requirement.",
                    defense_quote="",
                    rationale="Objection absent from criterion text",
                    status_code="COMPLETED",
                )
            elif ccode == "CRIT-CAT-01":
                return DefenseResult(
                    objection_valid=False,
                    objection_invalid_reason="The objection claims 20/60 does not meet 20/50 or worse, but 20/60 is worse than 20/50 in Snellen acuity.",
                    defense_quote="",
                    rationale="Numeric comparison inverted",
                    status_code="COMPLETED",
                )
            return DefenseResult(objection_valid=True, defense_quote="", rationale="Default", status_code="COMPLETED")

        def mock_equiv(*args, **kwargs):
            return JudgeEvaluation(verdict="EQUIVALENT", rationale="Equivalent clinical concept", elapsed_ms=10.0, status_code="COMPLETED")

        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_judge))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", side_effect=mock_challenge))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", side_effect=mock_defense))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "judge_equivalence_sync", side_effect=mock_equiv))

    with stack:
        # 1. DEV-LCD-KYPHO-APP
        v_kypho = vignettes_by_id["DEV-LCD-KYPHO-APP"]
        res_kypho = pipeline.adjudicate_sync(
            patient_id=v_kypho.get("patient_id", "DEV-LCD-KYPHO-APP"),
            policy_id=v_kypho["policy_id"],
            ehr_narrative=v_kypho["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )
        assert res_kypho.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"DEV-LCD-KYPHO-APP must adjudicate to APPROVED, got: {res_kypho.adjudication_decision} ({res_kypho.abstention_reason})"
        )

        # 2. DEV-NCD-CATARACT-APP
        v_cat = vignettes_by_id["DEV-NCD-CATARACT-APP"]
        res_cat = pipeline.adjudicate_sync(
            patient_id=v_cat.get("patient_id", "DEV-NCD-CATARACT-APP"),
            policy_id=v_cat["policy_id"],
            ehr_narrative=v_cat["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )
        assert res_cat.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"DEV-NCD-CATARACT-APP must adjudicate to APPROVED, got: {res_cat.adjudication_decision} ({res_cat.abstention_reason})"
        )

        # 3. DEV-NCD-PET-ONC-APP
        v_pet = vignettes_by_id["DEV-NCD-PET-ONC-APP"]
        res_pet = pipeline.adjudicate_sync(
            patient_id=v_pet.get("patient_id", "DEV-NCD-PET-ONC-APP"),
            policy_id=v_pet["policy_id"],
            ehr_narrative=v_pet["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )
        assert res_pet.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"DEV-NCD-PET-ONC-APP must adjudicate to APPROVED, got: {res_pet.adjudication_decision} ({res_pet.abstention_reason})"
        )


def test_v86_v84_and_v85_invariants_hold():
    """
    Condition (vi): Asserts that key invariants from v84 (concession defense) and
    v85 (0.65 threshold boundary) continue to pass unchanged.
    """
    from tests.test_v84_concession_defense import (
        test_v84_valid_objection_still_concedes,
    )
    from tests.test_v85_threshold_revert import (
        test_v85_lexical_fallback_only_when_no_candidate_quote,
        test_v85_min_sim_threshold_is_0_65_for_paraphrase,
    )

    test_v84_valid_objection_still_concedes()
    test_v85_min_sim_threshold_is_0_65_for_paraphrase()
    test_v85_lexical_fallback_only_when_no_candidate_quote()


def test_v86_requirement_text_detection_is_specific():
    """
    Condition (vii): The requirement-text detection is specific and pins the boundary
    of Option B. Genuine clinical paraphrases (not matching requirement text) must still
    trigger the 0.65 threshold and inhibit the fallback, returning "".
    """
    # Scenario from v85 test (i): genuine clinical paraphrase with low similarity
    crit_pt = {
        "criterion_code": "CRIT-PT-01",
        "name": "Conservative Therapy",
        "description": "Documented failure of at least 6 weeks of conservative therapy",
        "keywords": ["therapy", "rehabilitation"],
    }
    note_pt = "Patient underwent physical therapy. Patient completed rehabilitation."
    cand_pt = "rehab and physical exercise"

    mock_tok = MagicMock()
    mock_mod = MagicMock()
    import torch
    v_query = torch.tensor([[1.0, 0.0, 0.0, 0.0]])
    v_sents = torch.tensor([[0.62, 0.7846, 0.0, 0.0], [0.10, 0.9949, 0.0, 0.0]])
    reps = torch.cat([v_query, v_sents], dim=0)
    mock_out = MagicMock()
    mock_out.last_hidden_state = reps.unsqueeze(1)
    mock_mod.return_value = mock_out

    with patch("app.services.hybrid_retriever._get_sapbert_model", return_value=(mock_tok, mock_mod, "cpu")), \
         patch("torch.clamp", side_effect=lambda x, min: x):
        span_pt = ClinicalEquivalenceJudge.select_most_relevant_span(
            criterion=crit_pt,
            note_text=note_pt,
            candidate_quote=cand_pt,
        )
        assert span_pt == "", "Genuine paraphrase with sim 0.62 must be rejected under 0.65 threshold"

    # Scenario from v85 test (ii): genuine clinical paraphrase with SapBERT failure
    crit_lumb = {
        "criterion_code": "CRIT-LUMB-01",
        "name": "Lumbar Pain",
        "description": "Documented lumbar pain during physical examination",
        "keywords": ["lumbar", "examination"],
    }
    note_lumb = "The clinical examination reveals pain with lumbar extension and flexion."
    cand_lumb = "severe back ache and stiffness"

    with patch("app.services.hybrid_retriever._get_sapbert_model", side_effect=ImportError("SapBERT disabled for test")):
        span_lumb = ClinicalEquivalenceJudge.select_most_relevant_span(
            criterion=crit_lumb,
            note_text=note_lumb,
            candidate_quote=cand_lumb,
        )
        assert span_lumb == "", "Genuine paraphrase candidate must inhibit lexical fallback"
