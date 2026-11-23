"""
Test Suite for Prompt v78: Judge-in-the-Loop Span Verification, Sub-Requirement Specificity,
SBRT Paraphrase Normalization, and Redundant Verification Elimination.

Pins:
(i)   Judge equivalence on PET-ONC biopsy span returns EQUIVALENT and the rationale quotes the criterion requirement.
(ii)  Judge equivalence on a non-satisfying span returns NOT_EQUIVALENT and the rationale quotes the requirement.
(iii) Criterion codes and primary requirement branches/clauses are rejected by _is_valid_clinical_sub_requirement.
(iv)  SBRT paraphrase query normalizes to the verbatim note sentence via select_most_relevant_span (sim >= 0.65).
(v)   Redundant advocate verification on an already-MET/settled criterion is skipped, preserving MET determination.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agents.pipeline import (
    MultiAgentVerificationPipeline,
    _is_valid_clinical_sub_requirement,
)
from app.core.agentic_guardrails import AgenticGuardrails
from app.core.llm_judge import (
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    EquivalenceVerdict,
)
from app.schemas.contracts import AdjudicationDecision


def test_v78_judge_verifies_pet_onc_biopsy_span():
    """
    Condition (i): Judge equivalence on PET-ONC biopsy span returns EQUIVALENT
    and the rationale quotes the criterion requirement as written.
    """
    judge = ClinicalEquivalenceJudge()

    criterion_text = (
        "Documented biopsy-proven malignancy OR solitary pulmonary nodule > 8 mm on CT scan "
        "requiring characterization prior to planned intervention"
    )
    span = (
        "Pathology confirms invasive ductal carcinoma, estrogen receptor positive, "
        "biopsy-proven malignancy of the left breast."
    )

    # Test prompt generation contains the instruction and requirement
    prompt = judge.build_prompt(
        criterion_code="CRIT-PTONC-01",
        criterion_name="Biopsy-proven Malignancy",
        criterion_desc=criterion_text,
        candidate_span_text=span,
        clinical_intent=criterion_text,
    )
    assert "CRIT-PTONC-01" in prompt
    assert "requirement AS WRITTEN" in prompt
    assert "solitary pulmonary nodule" in prompt
    assert "MUST explicitly quote the exact phrase" in prompt

    # Verify verdict parsing with rationale quoting the criterion text
    mock_payload = {
        "verdict": "EQUIVALENT",
        "rationale": "The criterion requires 'biopsy-proven malignancy OR solitary pulmonary nodule > 8 mm'. The candidate evidence states 'biopsy-proven malignancy of the left breast', which satisfies the first disjunctive branch.",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_payload)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = judge.judge_equivalence_sync(
            criterion={
                "criterion_code": "CRIT-PTONC-01",
                "name": "Biopsy-proven Malignancy",
                "description": criterion_text,
                "clinical_intent": criterion_text,
            },
            candidate_span_text=span,
        )
        assert res.verdict == EquivalenceVerdict.EQUIVALENT
        assert "biopsy-proven malignancy" in res.rationale


def test_v78_judge_rejects_unsatisfying_span_with_quoted_rationale():
    """
    Condition (ii): Judge equivalence on a span that does NOT satisfy the criterion requirement
    returns NOT_EQUIVALENT and the rationale quotes what the criterion required (negative control).
    """
    judge = ClinicalEquivalenceJudge()

    criterion_text = (
        "Documented biopsy-proven malignancy OR solitary pulmonary nodule > 8 mm on CT scan "
        "requiring characterization prior to planned intervention"
    )
    unrelated_span = "Patient reports mild seasonal allergies managed with over-the-counter cetirizine."

    mock_payload = {
        "verdict": "NOT_EQUIVALENT",
        "rationale": "The criterion requires 'Documented biopsy-proven malignancy OR solitary pulmonary nodule > 8 mm'. The evidence discusses seasonal allergies, which has no relationship to biopsy or pulmonary nodules.",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_payload)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = judge.judge_equivalence_sync(
            criterion={
                "criterion_code": "CRIT-PTONC-01",
                "name": "Biopsy-proven Malignancy",
                "description": criterion_text,
                "clinical_intent": criterion_text,
            },
            candidate_span_text=unrelated_span,
        )
        assert res.verdict == EquivalenceVerdict.NOT_EQUIVALENT
        assert "Documented biopsy-proven malignancy" in res.rationale


def test_v78_criterion_code_not_specific_sub_requirement():
    """
    Condition (iii): Criterion codes (CRIT-CAT-01, CRIT-PTONC-01, CRIT-SBRT-01, REQUIREMENT 2.1)
    and full criterion descriptions are rejected by _is_valid_clinical_sub_requirement.
    Valid clinical sub-requirement phrases (distinct tests/findings) pass.
    """
    primary_cat_req = (
        "Documented best-corrected Snellen distance visual acuity of 20/50 or worse in affected eye "
        "attributable to cataract, or 20/40 or better with disabling glare"
    )

    # Criterion codes and references must be rejected
    assert not _is_valid_clinical_sub_requirement("CRIT-CAT-01", "CRIT-CAT-01", primary_cat_req)
    assert not _is_valid_clinical_sub_requirement("CRIT-CAT-02", "CRIT-CAT-02", primary_cat_req)
    assert not _is_valid_clinical_sub_requirement("CRIT-PTONC-01", "CRIT-PTONC-01")
    assert not _is_valid_clinical_sub_requirement("CRIT-SBRT-01", "CRIT-SBRT-01")
    assert not _is_valid_clinical_sub_requirement("REQUIREMENT 2.1.1.1.1", "CRIT-CAT-01")
    assert not _is_valid_clinical_sub_requirement("2.1.1.1.1", "CRIT-CAT-01")
    assert not _is_valid_clinical_sub_requirement(primary_cat_req, "CRIT-CAT-01", primary_cat_req)

    # Valid clinical sub-requirement phrase (narrow distinct test/finding) should pass
    assert _is_valid_clinical_sub_requirement("contrast sensitivity test", "CRIT-CAT-01", primary_cat_req)
    assert _is_valid_clinical_sub_requirement("potential acuity meter testing", "CRIT-CAT-01", primary_cat_req)
    assert _is_valid_clinical_sub_requirement("formal SLP evaluation and device trial", "CRIT-SGD-02")


def test_v78_sbrt_paraphrase_normalization():
    """
    Condition (iv): SBRT paraphrase query normalizes to the verbatim note sentence
    via select_most_relevant_span (sim >= 0.65 threshold).
    """
    ehr_text = (
        "CLINICAL NOTE: 74yo patient with severe COPD on 2L supplemental oxygen, FEV1 38% predicted. "
        "ASSESSMENT & PLAN: Medically inoperable early-stage non-small cell lung cancer, stage T1cN0M0. "
        "Referred for stereotactic body radiation therapy (SBRT)."
    )
    paraphrase_query = (
        "The patient is diagnosed with medically inoperable early-stage non-small cell lung cancer "
        "Stage I or Stage IIA with no nodal involvement."
    )

    criterion = {
        "id": "CRIT-SBRT-01",
        "description": paraphrase_query,
        "clinical_intent": paraphrase_query,
    }

    span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=criterion,
        note_text=ehr_text,
    )
    assert span is not None
    assert "Medically inoperable early-stage non-small cell lung cancer" in span
    # Verify it is an exact sentence in the note
    assert span in ehr_text


def test_v78_redundant_verification_skip_preserves_decision():
    """
    Condition (v): Redundant advocate verification on an already-MET/settled criterion
    is skipped (the skip branch executes, the promotion is not re-attempted, and the
    existing MET determination is preserved).
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    ehr = (
        "PATIENT RECORD: 68-year-old female with persistent lower back pain. "
        "Conservative management completed with 8 weeks of physical therapy and NSAIDs without relief."
    )
    quote = "Conservative management completed with 8 weeks of physical therapy and NSAIDs without relief."

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Conservative therapy criterion satisfied",
        confidence=0.94,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "adversarial_counter_reading": False,
             "has_objection": False,
             "objection_type": "NONE",
             "counter_quote": "",
             "named_sub_requirement": "none",
             "specific_contradiction": False,
             "rationale": "No objection",
         }), \
         patch.object(ClinicalEquivalenceJudge, "judge_equivalence_sync") as mock_judge_equiv:

        # Adjudicate a policy where CRIT-01 is judged MET
        res = pipeline.adjudicate_sync(
            patient_id="PT-V78-REDUNDANT-SKIP",
            policy_id="LCD-L35452",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

        # Because criteria settled as MET during debate, advocate verification MUST NOT call judge_equivalence_sync
        assert mock_judge_equiv.call_count == 0
        assert res.adjudication_decision in (AdjudicationDecision.APPROVED, AdjudicationDecision.DEFERRED_TO_HUMAN)
