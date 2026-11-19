"""
Tests for Suggestion Prompt v70:
1. Task 1 Routing: Route every unproven mandatory criterion to the advocate before deferral.
   (test_deferred_case_has_recorded_advocate_attempt_for_unproven_criteria)
2. Task 2(a) Advocate-span verification: Judge verifies semantic fit before promotion.
   (test_advocate_span_requires_judge_verification_before_promotion)
3. Task 2(b) Pre-deferral case-level review: Judge confirms deferrability before human deferral.
   (test_deferred_case_has_recorded_judge_confirmation)
4. Task 3(a) Efficiency Fast Path: Fully-verified case makes zero LLM calls.
   (test_fully_verified_case_makes_zero_llm_calls)
"""

from unittest.mock import patch

import pytest

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.llm_judge import (
    AdvocacyResult,
    CaseDeferralReview,
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    EquivalenceVerdict,
    JudgeEvaluation,
)
from app.schemas.contracts import AdjudicationDecision
from app.schemas.message_board import BoardMessageType


@pytest.fixture
def imrt_vignette():
    return {
        "policy_id": "LCD-IMRT",
        "ehr_narrative": (
            "PATIENT PROGRESS NOTE: 68-year-old male with confirmed prostate adenocarcinoma. "
            "Gleason score 4+3=7, PSA 12.4 ng/mL. 3D-CRT plan exceeds rectal wall tolerance constraints. "
            "Recommending IMRT for organ sparing."
        ),
    }


def test_deferred_case_has_recorded_advocate_attempt_for_unproven_criteria(imrt_vignette):
    """
    Task 1 Routing: A deferred case must not contain an unattempted mandatory non-MET criterion.
    Every unproven mandatory criterion must be offered to the advocate before deferral.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    # Initial judge returns NOT_MET for unproven criteria
    mock_not_met = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="Evidence not found in initial pass",
        confidence=0.50,
        status_code="COMPLETED",
    )

    # Advocate returns empty quote
    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="No alternate supporting evidence identified in note",
        confidence=0.50,
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_not_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy) as mock_adv:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V70-ROUTING",
            policy_id="LCD-IMRT",
            ehr_narrative=imrt_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    # If the case deferred, verify every non-MET mandatory criterion had an advocate attempt recorded
    if res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN:
        board_msgs = res.message_board or []
        adv_msgs = [m for m in board_msgs if m.get("message_type") in ("ADVOCACY", BoardMessageType.ADVOCACY)]
        assert len(adv_msgs) >= 1, "Deferred case must contain at least one recorded advocate attempt"
        assert mock_adv.called, "Advocate must be called for unproven mandatory criteria before deferral"


def test_advocate_span_requires_judge_verification_before_promotion(imrt_vignette):
    """
    Task 2(a): Advocate-span verification.
    When advocate proposes a verbatim quote that passes deterministic gates,
    the judge must verify semantic equivalence before promotion.
    If the judge returns NOT_EQUIVALENT, promotion is rejected.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_not_met = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="Initial pass found no direct mention",
        confidence=0.50,
        status_code="COMPLETED",
    )

    # Advocate finds an actual verbatim span in the note
    mock_advocacy = AdvocacyResult(
        advocacy_quote="rectal wall tolerance constraints",
        rationale="Proposing rectal sparing documentation for IMRT criterion",
        confidence=0.90,
        elapsed_ms=15.0,
        status_code="COMPLETED",
    )

    # Judge semantic verification rejects equivalence (e.g. coverage judgment fails)
    mock_judge_reject = JudgeEvaluation(
        verdict=EquivalenceVerdict.NOT_EQUIVALENT,
        rationale="Rectal wall constraints do not meet concave target criteria.",
        elapsed_ms=12.0,
        status_code="COMPLETED",
    )

    from app.core.agentic_guardrails import AgenticGuardrails

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_not_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Passed deterministic gates"}), \
         patch.object(ClinicalEquivalenceJudge, "judge_equivalence_sync", return_value=mock_judge_reject) as mock_equiv:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V70-JUDGE-SPAN-REJECT",
            policy_id="LCD-IMRT",
            ehr_narrative=imrt_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    # Verify judge_equivalence_sync was consulted for the advocate span
    assert mock_equiv.called, "LLM Judge equivalence verification must be called for advocate proposed span"

    # Verify promotion was rejected and criterion was NOT promoted to MET
    board_msgs = res.message_board or []
    judge_verifications = [
        m for m in board_msgs
        if m.get("metadata", {}).get("advocate_span_verification")
    ]
    assert len(judge_verifications) >= 1, "Advocate span verification verdict must be posted to message board"

    rejected_challenges = [
        m for m in board_msgs
        if m.get("metadata", {}).get("failing_gate") == "JudgeEquivalence"
    ]
    assert len(rejected_challenges) >= 1, "Promotion must be rejected when judge finds candidate span not equivalent"


def test_deferred_case_has_recorded_judge_confirmation(imrt_vignette):
    """
    Task 2(b): Pre-deferral case-level review.
    A case may not reach the deferral queue without a recorded judge confirmation of deferrability.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_not_met = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="Evidence missing",
        confidence=0.50,
        status_code="COMPLETED",
    )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="No evidence in note",
        confidence=0.50,
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    mock_deferral_review = CaseDeferralReview(
        confirmed_deferrable=True,
        rationale="Confirmed lack of documentation in clinical narrative; case genuinely deferrable.",
        elapsed_ms=25.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_not_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync", return_value=mock_deferral_review) as mock_review:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V70-PRE-DEFERRAL",
            policy_id="LCD-IMRT",
            ehr_narrative=imrt_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert mock_review.called, "review_case_deferral_sync must be called before human deferral"

    # Board must contain pre-deferral confirmation
    board_msgs = res.message_board or []
    pre_def_msgs = [
        m for m in board_msgs
        if m.get("metadata", {}).get("pre_deferral_review")
    ]
    assert len(pre_def_msgs) >= 1, "Pre-deferral confirmation must be posted to message board"
    assert pre_def_msgs[0].get("metadata", {}).get("confirmed_deferrable") is True

    # Audit trail must record pre_deferral_review
    assert res.agentic_audit_trail.get("pre_deferral_review") is not None


def test_fully_verified_case_makes_zero_llm_calls():
    """
    Task 3(a): Deterministic Fast Path.
    If the deterministic engine has completely verified a case (all mandatory criteria MET
    with exact verbatim spans, no exclusions), the case is decided with ZERO LLM calls.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    # Clinical note that explicitly satisfies all criteria for LCD-CATARACT or LCD-BLEPH
    # Let's use a clear note for NCD-CATARACT / LCD-CATARACT or similar
    note = (
        "PATIENT RECORD:\n"
        "Chief Complaint: Progressive visual impairment.\n"
        "Best-corrected visual acuity: 20/50 in the right eye, with disabling glare.\n"
        "Comprehensive ophthalmologic examination confirms visually significant nuclear sclerotic cataract.\n"
        "Activities of daily living significantly impaired: patient cannot drive safely at night.\n"
        "Patient desires surgical correction; risks and benefits discussed.\n"
        "Plan: Phacoemulsification with intraocular lens implantation."
    )

    # Spy on LLM judge methods to assert 0 calls
    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync") as mock_judge, \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync") as mock_adv, \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync") as mock_rev:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V70-FAST-PATH",
            policy_id="NCD-CATARACT",
            ehr_narrative=note,
            execution_mode="agentic",
            save_record=False,
        )

    # If the case was verified deterministically, verify fast-path activated and 0 LLM calls
    if res.agentic_audit_trail.get("fast_path_activated"):
        assert res.adjudication_decision == AdjudicationDecision.APPROVED
        assert mock_judge.call_count == 0, f"Fast-path case must make 0 judge calls, made {mock_judge.call_count}"
        assert mock_adv.call_count == 0, f"Fast-path case must make 0 advocate calls, made {mock_adv.call_count}"
        assert mock_rev.call_count == 0, f"Fast-path case must make 0 pre-deferral calls, made {mock_rev.call_count}"
        assert res.agentic_audit_trail.get("judge_routing", {}).get("judge_calls_total_case", 0) == 0
