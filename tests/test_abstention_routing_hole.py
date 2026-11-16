"""
Regression tests for Task 1: Closing the routing hole on deterministic abstentions.

Asserts that when the deterministic engine abstains on a case
(INSUFFICIENT_EVIDENCE on a mandatory criterion or omission-bound),
the coordinator routes the case through the agentic loop
(judge and advocate get their chance before Agent 4 defers).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.llm_judge import (
    AdvocacyResult,
    ClinicalEquivalenceJudge,
    CriterionJudgment,
)
from app.schemas.contracts import AdjudicationDecision


@pytest.fixture
def synthetic_abstaining_fixture():
    """
    Synthetic clinical note and policy context where preliminary deterministic
    evaluation abstains due to INSUFFICIENT_EVIDENCE on a mandatory criterion.
    """
    return {
        "policy_id": "NCD-PET-ONC",
        "ehr_narrative": (
            "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
            "CLINICAL PROGRESS NOTE: Oncology Clinic\n"
            "SUBJECTIVE: Patient with progressive dysphagia and weight loss.\n"
            "OBJECTIVE: CT chest shows distal esophageal wall thickening. "
            "Endoscopic biopsy reveals adenocarcinoma.\n"
            "ASSESSMENT & PLAN: Distal esophageal mass; requesting FDG-PET scan for initial staging."
        ),
    }


def test_abstention_routing_hole_calls_judge_and_advocate(synthetic_abstaining_fixture):
    """
    Asserts that an abstention-bound case (with INSUFFICIENT_EVIDENCE on CRIT-PTONC-01)
    does not bypass the LLM judge: judge_calls > 0 and advocacy is attempted.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MISSING",
        quoted_evidence="",
        rationale="Synthetic mock judge: evidence missing in narrative.",
        confidence=0.85,
        elapsed_ms=15.0,
        status_code="COMPLETED",
    )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="Synthetic mock advocate: no grounded quote found.",
        confidence=0.80,
        elapsed_ms=12.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment) as mock_judge, \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy) as mock_advocate:

        res = pipeline.adjudicate_sync(
            patient_id="PT-SYNTHETIC-ABSTAIN",
            policy_id=synthetic_abstaining_fixture["policy_id"],
            ehr_narrative=synthetic_abstaining_fixture["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

        # 1. Assert LLM judge was called (routing hole closed)
        assert mock_judge.called, "LLM judge must be called when deterministic engine abstains"
        assert mock_judge.call_count >= 1, f"Expected judge_calls >= 1, got {mock_judge.call_count}"

        # 2. Assert advocacy was attempted when judge did not promote
        assert mock_advocate.called, "Agent 3 advocacy must be attempted when judge returns non-MET"

        # 3. Assert board messages record PLAN and JUDGMENT
        board_msgs = res.message_board or []
        mtypes = [m.get("message_type") for m in board_msgs]
        assert "PLAN" in mtypes, "Board must contain PLAN message"
        assert "JUDGMENT" in mtypes, "Board must contain JUDGMENT message from judge"
        assert "ADVOCACY" in mtypes, "Board must contain ADVOCACY message from advocate"

        # 4. Assert coordinator routed the criterion to needs_judge
        agent2_plans = [m for m in board_msgs if m.get("agent") == "Agent 2: Clinical Evaluator" and m.get("message_type") == "PLAN"]
        assert len(agent2_plans) >= 1
        plan_meta = agent2_plans[0].get("metadata", {})
        needs_judge = plan_meta.get("needs_judge", [])
        assert "CRIT-PTONC-01" in needs_judge, "CRIT-PTONC-01 must be routed to needs_judge"

        # 5. Case still safely defers when evidence is truly missing
        assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN


def test_omission_bound_criterion_routes_to_judge():
    """
    Asserts that an omission-bound exclusion or criterion is routed through the LLM judge.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    synthetic_note = (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Pulmonary Sleep Medicine\n"
        "SUBJECTIVE: 46-year-old with daytime somnolence and heavy snoring.\n"
        "OBJECTIVE: Polysomnography reveals uncomplicated obstructive sleep apnea with AHI 22 events/hr. "
        "Daytime arterial blood gas shows completely normal PaCO2 of 38 mmHg without hypoventilation.\n"
        "ASSESSMENT & PLAN: Moderate obstructive sleep apnea without respiratory failure. "
        "Advanced non-invasive ventilator with backup rate is contraindicated for uncomplicated sleep apnea."
    )

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence="Advanced non-invasive ventilator with backup rate is contraindicated for uncomplicated sleep apnea",
        rationale="Synthetic mock judge: statutory exclusion verified present.",
        confidence=0.92,
        elapsed_ms=18.0,
        status_code="COMPLETED",
    )

    mock_challenge = {
        "has_objection": False,
        "objection_type": "NONE",
        "rationale": "No disqualifying contradiction in note.",
    }

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment) as mock_judge, \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge):
        res = pipeline.adjudicate_sync(
            patient_id="PT-SYNTHETIC-OMISSION",
            policy_id="LCD-RAD-NIV",
            ehr_narrative=synthetic_note,
            execution_mode="agentic",
            save_record=False,
        )

        assert mock_judge.called, "LLM judge must be called for omission-bound criterion"
        # Since exclusion was proven MET by the judge, the case is denied (not deferred)
        assert res.adjudication_decision == AdjudicationDecision.DENIED
        assert not res.abstention_status
