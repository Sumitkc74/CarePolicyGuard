"""
Tests for Suggestion Prompt v73:
1. Task 2: Narrow the pre-deferral review.
   - test_pre_deferral_review_runs_when_mandatory_criterion_met:
     Pre-deferral review runs when deferred case has >= 1 mandatory criterion MET.
   - test_pre_deferral_review_skipped_when_no_mandatory_criterion_met:
     Pre-deferral review is skipped when criteria_met_count == 0, with narrowing reason recorded.
2. Task 2 & Task 4: Explicit board / audit trail record:
   - Skipped review recorded as INFORM with narrowing_rule_applied: True and explicit reason.
3. Task 4: Core judge work unchanged:
   - Criterion judgment and span advocacy verification operate identically.
4. Task 3: Measurement script baseline reuse validity checker.
"""

import json
import subprocess
from pathlib import Path
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
from scripts.run_agentic_v59_three_mode_measurement import (
    verify_baseline_reuse_validity,
)


@pytest.fixture
def imrt_narrative():
    return (
        "PATIENT PROGRESS NOTE: 68-year-old male with confirmed prostate adenocarcinoma. "
        "Gleason score 4+3=7, PSA 12.4 ng/mL. 3D-CRT plan exceeds rectal wall tolerance constraints. "
        "Recommending IMRT for organ sparing."
    )


def test_pre_deferral_review_runs_when_mandatory_criterion_met(imrt_narrative):
    """
    Task 2(a): Review RUNS when deferred case has >= 1 mandatory criterion MET.
    In LCD-IMRT, CRIT-IMRT-01 (prostate cancer) is MET, but CRIT-IMRT-02 is NOT_MET.
    The pre-deferral review must execute and record VERDICT on the board.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    def mock_judge_side_effect(criterion=None, ehr_narrative=None, *args, **kwargs):
        if criterion is None and args:
            criterion = args[0]
        ccode = criterion.get("criterion_code") if isinstance(criterion, dict) else getattr(criterion, "criterion_code", None)
        if ccode == "CRIT-IMRT-01":
            return CriterionJudgment(
                status="MET",
                quoted_evidence="confirmed prostate adenocarcinoma",
                rationale="Prostate adenocarcinoma matches criterion",
                confidence=0.95,
                status_code="COMPLETED",
            )
        return CriterionJudgment(
            status="NOT_MET",
            quoted_evidence="",
            rationale="Concave target geometry not established",
            confidence=0.50,
            status_code="COMPLETED",
        )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="No alternate evidence in narrative",
        confidence=0.50,
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    mock_deferral_review = CaseDeferralReview(
        confirmed_deferrable=True,
        rationale="Confirmed lack of documentation for concave geometry; case is genuinely deferrable.",
        elapsed_ms=20.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_judge_side_effect), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync", return_value=mock_deferral_review) as mock_review:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V73-RUN-REVIEW",
            policy_id="LCD-IMRT",
            ehr_narrative=imrt_narrative,
            execution_mode="agentic",
            save_record=False,
        )

    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert mock_review.called, "Pre-deferral review must run when criteria_met_count >= 1"

    # Board must contain VERDICT pre-deferral review
    board_msgs = res.message_board or []
    pre_def_verdicts = [
        m for m in board_msgs
        if m.get("metadata", {}).get("pre_deferral_review")
    ]
    assert len(pre_def_verdicts) == 1, "Must post exactly 1 VERDICT pre-deferral review message"
    assert pre_def_verdicts[0]["metadata"].get("confirmed_deferrable") is True

    # Audit trail verification
    audit = res.agentic_audit_trail or {}
    routing_meta = audit.get("judge_routing", {})
    assert routing_meta.get("pre_deferral_review_completed") is True
    assert routing_meta.get("pre_deferral_review_skipped_by_narrowing") is False


def test_pre_deferral_review_skipped_when_no_mandatory_criterion_met():
    """
    Task 2(b): Review is SKIPPED when criteria_met_count == 0.
    When all mandatory criteria are unproven / NOT_MET, review_case_deferral_sync
    must NOT be called.
    An INFORM message must be posted to the board with explicit skip reason.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    empty_narrative = "Patient presented for general consultation. Routine review."

    mock_not_met = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="No relevant clinical documentation in note",
        confidence=0.50,
        status_code="COMPLETED",
    )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="No supporting evidence identified in note",
        confidence=0.50,
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_not_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync") as mock_review:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V73-SKIP-REVIEW",
            policy_id="LCD-IMRT",
            ehr_narrative=empty_narrative,
            execution_mode="agentic",
            save_record=False,
        )

    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert not mock_review.called, "Pre-deferral review must be SKIPPED when criteria_met_count == 0"

    # Board must contain INFORM message with explicit reason
    board_msgs = res.message_board or []
    skip_msgs = [
        m for m in board_msgs
        if m.get("metadata", {}).get("pre_deferral_review_skipped")
    ]
    assert len(skip_msgs) == 1, "Must post exactly 1 INFORM message recording skipped review"
    skip_meta = skip_msgs[0]["metadata"]
    assert skip_meta.get("narrowing_rule_applied") is True
    assert "No mandatory criteria met" in skip_meta.get("reason", "")
    assert "skipped by narrowing rule" in skip_msgs[0].get("content", "").lower()

    # Audit trail verification
    audit = res.agentic_audit_trail or {}
    routing_meta = audit.get("judge_routing", {})
    assert routing_meta.get("pre_deferral_review_completed") is False
    assert routing_meta.get("pre_deferral_review_skipped_by_narrowing") is True


def test_judge_core_work_unchanged(imrt_narrative):
    """
    Task 4: Pin that the judge's core work (criterion judgments, advocate span verification, defenses)
    operates identically and has not been weakened or bypassed.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judge = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="Initial pass found no match",
        confidence=0.50,
        status_code="COMPLETED",
    )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="rectal wall tolerance constraints",
        rationale="Advocate span found in note",
        confidence=0.90,
        elapsed_ms=12.0,
        status_code="COMPLETED",
    )

    mock_verification = JudgeEvaluation(
        verdict=EquivalenceVerdict.EQUIVALENT,
        rationale="Rectal wall constraints satisfy the clinical intent",
        elapsed_ms=15.0,
        status_code="COMPLETED",
    )

    from app.core.agentic_guardrails import AgenticGuardrails

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judge) as m_judge, \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy) as m_adv, \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Gate passed"}), \
         patch.object(ClinicalEquivalenceJudge, "judge_equivalence_sync", return_value=mock_verification) as m_equiv:
        pipeline.adjudicate_sync(
            patient_id="PT-V73-CORE-UNCHANGED",
            policy_id="LCD-IMRT",
            ehr_narrative=imrt_narrative,
            execution_mode="agentic",
            save_record=False,
        )

    assert m_judge.called, "Initial criterion judge must be called"
    assert m_adv.called, "Advocate must be called"
    assert m_equiv.called, "Advocate span verification must be called"


def test_baseline_reuse_validation_mechanism(tmp_path: Path):
    """
    Task 3: Baseline reuse validity check.
    Reuse vs v72 (41350ec) is invalid since v91 (3c6006a) modified app/data/policies_extended/.
    Positive case: reuse against the current live HEAD passes (empty diff).
    Fails when previous run JSON does not exist.
    """
    v72_path = Path("app/data/benchmarks/agentic_v72_three_mode_run.json")
    if v72_path.exists():
        # Reuse vs the v72 baseline is invalid since the v91 policy changes under app/data/policies_extended/
        with pytest.raises(RuntimeError):
            verify_baseline_reuse_validity(v72_path)

        # Positive case: pin that the reuse mechanism returns True when compared against live HEAD
        current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        v72_data = json.loads(v72_path.read_text(encoding="utf-8"))
        v72_data.setdefault("metadata", {})["git_head"] = current_head
        v72_data["metadata"]["git_head_full"] = current_head
        tmp_run_path = tmp_path / "live_head_reuse.json"
        tmp_run_path.write_text(json.dumps(v72_data), encoding="utf-8")
        assert verify_baseline_reuse_validity(tmp_run_path) is True

    # Non-existent file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        verify_baseline_reuse_validity(Path("app/data/benchmarks/non_existent_run.json"))
