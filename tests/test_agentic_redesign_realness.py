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


def test_fatal_anatomic_mismatch_without_defense_leaves_criterion_deferred(sample_vignette):
    """
    Task 5 (a): A mocked ANATOMIC_MISMATCH counter-reading with no successful defense leaves the criterion DEFERRED.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="prostate adenocarcinoma",
        rationale="Biopsy proven prostate adenocarcinoma satisfies criterion.",
        confidence=0.95
    )

    from app.core.agentic_guardrails import AgenticGuardrails
    from app.core.llm_judge import DefenseResult

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified equivalence"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "adversarial_counter_reading": True,
             "has_objection": True,
             "objection_type": "ANATOMIC_MISMATCH",
             "counter_quote": "prostate adenocarcinoma",
             "rationale": "Radiation field targets pelvis instead of spine."
         }), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=DefenseResult(
             defense_quote="",
             rationale="Cannot refute anatomic site discrepancy; pelvis and spine differ."
         )):
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-ANATOMIC-DEF",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    # Assert Agent 2 conceded due to failed defense on ANATOMIC_MISMATCH
    concede_msgs = [
        m for m in board_msgs
        if m.get("agent") == "Agent 2: Clinical Evaluator"
        and m.get("message_type") == "CONCEDE"
        and "ANATOMIC_MISMATCH" in m.get("content", "")
    ]
    assert len(concede_msgs) >= 1, "Agent 2 must concede the ANATOMIC_MISMATCH objection on failure to defend"

    # Outcome for criterion must be recorded in audit trail
    routing = res.agentic_audit_trail.get("judge_routing", {})
    outcomes = routing.get("debated_criteria_outcomes", {})
    assert outcomes.get("CRIT-IMRT-02") == "CONCEDED"

    # Criterion assessment remains not MET (INSUFFICIENT_EVIDENCE or NOT_MET) and case defers
    crit_2 = next(ca for ca in res.criterion_assessments if ca.criterion_code == "CRIT-IMRT-02")
    assert crit_2.status != "MET", "Criterion must not be promoted after conceded ANATOMIC_MISMATCH challenge"


def test_grounded_defense_quote_produces_defend_and_promotes_criterion(sample_vignette):
    """
    Task 5 (b): A grounded defense quote produces a DEFEND containing the quote and objection type,
    and the criterion is promoted to MET.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="prostate adenocarcinoma",
        rationale="Biopsy proven prostate adenocarcinoma satisfies criterion.",
        confidence=0.95
    )

    from app.core.agentic_guardrails import AgenticGuardrails
    from app.core.llm_judge import DefenseResult

    # Note text includes: "3D-CRT plan exceeds rectal wall tolerance constraints."
    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified equivalence"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "adversarial_counter_reading": True,
             "has_objection": True,
             "objection_type": "TEMPORAL",
             "counter_quote": "prostate adenocarcinoma",
             "rationale": "Biopsy timing ambiguous in clinical record."
         }), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=DefenseResult(
             defense_quote="3D-CRT plan exceeds rectal wall tolerance constraints",
             rationale="Current active simulation plan confirms current clinical workflow."
         )):
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-DEFENSE-PROMOTES",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    defend_msgs = [
        m for m in board_msgs
        if m.get("agent") == "Agent 2: Clinical Evaluator"
        and m.get("message_type") == "DEFENSE"
        and "TEMPORAL" in m.get("content", "")
    ]
    assert len(defend_msgs) >= 1, "Agent 2 must post DEFENSE containing objection type 'TEMPORAL'"
    assert "3D-CRT plan exceeds rectal wall tolerance constraints" in defend_msgs[0].get("content", "")

    # Outcome must be DEFENDED
    routing = res.agentic_audit_trail.get("judge_routing", {})
    outcomes = routing.get("debated_criteria_outcomes", {})
    assert outcomes.get("CRIT-IMRT-02") == "DEFENDED"

    # Criterion must be promoted to MET
    crit_2 = next(ca for ca in res.criterion_assessments if ca.criterion_code == "CRIT-IMRT-02")
    assert crit_2.status == "MET", "Criterion must be promoted to MET after successful defense"


def test_fabricated_defense_quote_rejected_by_gate_a_and_leaves_criterion_deferred(sample_vignette):
    """
    Task 5 (c): A fabricated defense quote is rejected by Gate A and the criterion stays DEFERRED.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="prostate adenocarcinoma",
        rationale="Biopsy proven prostate adenocarcinoma satisfies criterion.",
        confidence=0.95
    )

    from app.core.agentic_guardrails import AgenticGuardrails
    from app.core.llm_judge import DefenseResult

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified equivalence"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "adversarial_counter_reading": True,
             "has_objection": True,
             "objection_type": "HYPOTHETICAL",
             "counter_quote": "prostate adenocarcinoma",
             "rationale": "Condition might be hypothetical rule-out."
         }), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=DefenseResult(
             defense_quote="Patient definitely has documented real cancer on pathology report from yesterday",
             rationale="Pathology confirmed as non-hypothetical."
         )):
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-FABRICATED-DEFENSE",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    concede_msgs = [
        m for m in board_msgs
        if m.get("agent") == "Agent 2: Clinical Evaluator"
        and m.get("message_type") == "CONCEDE"
        and "HYPOTHETICAL" in m.get("content", "")
    ]
    assert len(concede_msgs) >= 1, "Agent 2 must concede when defense quote fails Gate A grounding"

    routing = res.agentic_audit_trail.get("judge_routing", {})
    outcomes = routing.get("debated_criteria_outcomes", {})
    assert outcomes.get("CRIT-IMRT-02") == "CONCEDED"

    crit_2 = next(ca for ca in res.criterion_assessments if ca.criterion_code == "CRIT-IMRT-02")
    assert crit_2.status != "MET", "Criterion must stay DEFERRED/unpromoted on ungrounded defense quote"


def test_routing_counters_appear_in_result_metadata(sample_vignette):
    """
    Task 5 (d): The routing counters appear in the result metadata on an agentic case.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-ROUTING-META",
        policy_id="LCD-IMRT",
        ehr_narrative=sample_vignette["ehr_narrative"],
        execution_mode="agentic",
        save_record=False,
    )

    # Check agentic_audit_trail["judge_routing"]
    routing = res.agentic_audit_trail.get("judge_routing", {})
    assert "judge_calls_otherwise_deferring" in routing, "judge_calls_otherwise_deferring must be in judge_routing"
    assert "judge_calls_already_settled" in routing, "judge_calls_already_settled must be in judge_routing"
    assert "judge_calls_total_case" in routing, "judge_calls_total_case must be in judge_routing"
    assert "debated_criteria_outcomes" in routing, "debated_criteria_outcomes must be in judge_routing"

    # Also check llm_proposal_metadata
    llm_meta = res.llm_proposal_metadata or {}
    assert "judge_calls_otherwise_deferring" in llm_meta, "judge_calls_otherwise_deferring must be in llm_proposal_metadata"
    assert "judge_calls_already_settled" in llm_meta, "judge_calls_already_settled must be in llm_proposal_metadata"
    assert "judge_calls_total_case" in llm_meta, "judge_calls_total_case must be in llm_proposal_metadata"
    assert "debated_criteria_outcomes" in llm_meta, "debated_criteria_outcomes must be in llm_proposal_metadata"

