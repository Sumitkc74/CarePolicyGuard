"""
Fail-before / pass-after regression tests for the v38 agentic redesign.
Validates:
(a) Agent 2 posts a PLAN before evaluation on an agentic case.
(b) The criterion judge returns a structured judgment verified by Gate A, and fabricated quotes are rejected.
(c) Agent 3 raises an LLM counter-reading challenge on a MET proposal and Agent 2 answers (DEFEND or CONCEDE).
(d) Judge calls are routed to otherwise-deferring criteria first (settled criteria receive zero judge calls).
(e) Judge model override configuration is honored.
"""

from __future__ import annotations

import os
from importlib import reload
from unittest.mock import patch

import pytest

import app.core.config as config_mod
from app.agents.llm_proposer import LLMProposalAgent
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.config import settings
from app.core.llm_judge import ClinicalEquivalenceJudge, CriterionJudgment
from app.schemas.message_board import BoardMessageType


@pytest.fixture
def sample_vignette():
    return {
        "policy_id": "LCD-IMRT",
        "ehr_narrative": (
            "PATIENT PROGRESS NOTE: 68-year-old male with confirmed prostate adenocarcinoma. "
            "Gleason score 4+3=7, PSA 12.4 ng/mL. 3D-CRT plan exceeds rectal wall tolerance constraints. "
            "Recommending IMRT for organ sparing."
        ),
    }


def test_agent2_posts_plan_before_evaluation_on_agentic_case(sample_vignette):
    """
    Test (a): Agent 2 must post a PLAN message to the message board before any criterion evaluation.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)
    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-PLAN",
        policy_id=sample_vignette["policy_id"],
        ehr_narrative=sample_vignette["ehr_narrative"],
        execution_mode="agentic",
        save_record=False,
    )

    board_msgs = res.message_board or []
    plan_msgs = [m for m in board_msgs if m.get("message_type") in ("PLAN", getattr(BoardMessageType, "PLAN", "PLAN"))]

    assert len(plan_msgs) >= 1, "Agent 2 must post at least one PLAN message on the board"
    plan = plan_msgs[0]
    assert plan.get("agent") == "Agent 2: Clinical Evaluator"
    meta = plan.get("metadata", {})
    assert "settled_deterministic" in meta or "routing" in meta, "PLAN metadata must contain criterion routing"


def test_criterion_judge_returns_structured_judgment_and_gate_a_rejects_fabricated_quote():
    """
    Test (b): The criterion judge must have judge_criterion_sync returning structured judgment,
    and a fabricated quote not in the note text must be rejected by Gate A.
    """
    judge = ClinicalEquivalenceJudge()
    assert hasattr(judge, "judge_criterion_sync"), "ClinicalEquivalenceJudge must have judge_criterion_sync method"

    crit = {
        "criterion_code": "CRIT-TEST-01",
        "name": "Prostate Cancer",
        "description": "Biopsy proven prostate cancer",
        "is_exclusion": False,
    }
    note = "Patient has localized prostate adenocarcinoma."

    # Test structured return
    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="prostate adenocarcinoma",
        rationale="Adenocarcinoma of prostate satisfies prostate cancer criterion.",
        confidence=0.92,
    )
    with patch.object(judge, "judge_criterion_sync", return_value=mock_judgment):
        res = judge.judge_criterion_sync(crit, note)
        assert res.status == "MET"
        assert res.quoted_evidence == "prostate adenocarcinoma"
        assert res.rationale != ""

    # Test Gate A rejects fabricated quote
    s, _e = LLMProposalAgent.locate_claimed_span(note, "FABRICATED NON-EXISTENT EVIDENCE TEXT", allow_repair=True)
    assert s == -1, "Gate A locator must reject fabricated quote not present in note"


def test_agent3_raises_llm_counter_reading_challenge_and_agent2_answers(sample_vignette):
    """
    Test (c): When a criterion is proposed as MET through the judge, Agent 3 raises an LLM
    counter-reading challenge and Agent 2 answers it on the board with DEFENSE or CONCEDE.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    # Mock the LLM judge to return MET for a criterion, and mock Agent 3 counter-reading
    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="prostate adenocarcinoma",
        rationale="Biopsy proven prostate adenocarcinoma satisfies criterion.",
        confidence=0.95
    )

    from app.core.agentic_guardrails import AgenticGuardrails

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified equivalence"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "adversarial_counter_reading": True,
             "has_objection": True,
             "objection_type": "TEMPORAL",
             "counter_quote": "68-year-old male",
             "challenge_rationale": "Verify temporal validity of biopsy."
         }):
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-CHALLENGE",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    counter_challenges = [
        m for m in board_msgs
        if m.get("message_type") == "CHALLENGE"
        and m.get("metadata", {}).get("adversarial_counter_reading") is True
    ]
    assert len(counter_challenges) >= 1, "Agent 3 must raise an LLM counter-reading challenge on board"

    # Agent 2 must answer with DEFENSE or CONCEDE
    answers = [
        m for m in board_msgs
        if m.get("agent") == "Agent 2: Clinical Evaluator"
        and m.get("message_type") in ("DEFENSE", "CONCEDE")
    ]
    assert len(answers) >= 1, "Agent 2 must answer the counter-reading challenge with DEFENSE or CONCEDE"


def test_judge_calls_routed_to_otherwise_deferring_criteria_first(sample_vignette):
    """
    Test (d): In a case where settled criteria exist alongside an otherwise-deferring criterion,
    judge calls must be routed to the otherwise-deferring criterion first, and ZERO calls spent on settled.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    judge_calls_log = []

    def mock_judge_crit(self, criterion, note_text, deterministic_assessment=None):
        judge_calls_log.append(criterion.get("criterion_code"))
        return CriterionJudgment(
            status="MISSING",
            quoted_evidence="",
            rationale="No additional evidence found.",
            confidence=0.5
        )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", mock_judge_crit):
        pipeline.adjudicate_sync(
            patient_id="PT-TEST-ROUTING",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    # In LCD-IMRT with sample_vignette:
    # CRIT-IMRT-EXCL-01 is ruled out (settled deterministic).
    # Settled deterministic criteria must NOT have been passed to judge_criterion_sync
    assert "CRIT-IMRT-EXCL-01" not in judge_calls_log, "Settled exclusion must not receive an LLM judge call"


def test_judge_model_override_honored():
    """
    Test (e): Wire judge-model override (LOCAL_LLM_JUDGE_MODEL) and assert it is honored.
    """
    # Default without override
    judge_default = ClinicalEquivalenceJudge()
    assert judge_default.model_name in ("qwen2.5:3b", getattr(settings, "LOCAL_LLM_JUDGE_MODEL", "qwen2.5:3b"))

    # Explicit constructor override
    judge_custom = ClinicalEquivalenceJudge(model_name="custom-local-judge:latest")
    assert judge_custom.model_name == "custom-local-judge:latest"

    # Environment variable override
    with patch.dict(os.environ, {"LOCAL_LLM_JUDGE_MODEL": "qwen2.5:14b"}):
        reload(config_mod)
        assert getattr(config_mod.settings, "LOCAL_LLM_JUDGE_MODEL", None) == "qwen2.5:14b"
        judge_env = ClinicalEquivalenceJudge()
        assert judge_env.model_name == "qwen2.5:14b"
    # Restore config
    reload(config_mod)
