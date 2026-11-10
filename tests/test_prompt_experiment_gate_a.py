"""
Unit tests for Gate A evaluation check in prompt experiment (Task 1).
Proves that the check accurately distinguishes Gate A failures from passes:
- A proposal whose quote is not in the clinical note must count as a FAIL (failing_gate == 'GATE_A_EXACT_SLICE').
- A proposal whose quote is present verbatim in the note must count as a PASS (failing_gate != 'GATE_A_EXACT_SLICE').
- Tests backward compatibility and production prompt configuration.
"""

import pytest
from app.agents.llm_proposer import (
    LLMProposalAgent,
    LLMProposedSpan,
    GateEvaluationResult,
)


def evaluate_gate_a(proposal: LLMProposedSpan, narrative: str, criterion_dict: dict, agent: LLMProposalAgent) -> bool:
    """
    Unified Gate A evaluation function used identically across both arms of the prompt experiment.
    """
    gate_res = agent.evaluate_proposal_through_gates(
        proposal=proposal,
        sanitized_ehr=narrative,
        criterion=criterion_dict
    )
    return gate_res.failing_gate != "GATE_A_EXACT_SLICE"


def test_gate_a_check_passes_when_claimed_text_is_verbatim_in_note():
    agent = LLMProposalAgent()
    narrative = "Patient has severe refractory right knee osteoarthritis with medial joint space narrowing."
    crit_dict = {
        "criterion_code": "CRIT-KNEE-01",
        "name": "Osteoarthritis Severity",
        "description": "Severe joint space narrowing",
        "criterion_type": "FINDING_PRESENCE",
        "is_exclusion": False
    }

    start, end = agent.locate_claimed_span(narrative, "medial joint space narrowing")
    assert start != -1 and end != -1

    proposal = LLMProposedSpan(
        criterion_code="CRIT-KNEE-01",
        proposed_status="MET",
        claimed_text="medial joint space narrowing",
        char_start=start,
        char_end=end,
        rationale="Exact phrase from physical note"
    )

    gate_a_passed = evaluate_gate_a(proposal, narrative, crit_dict, agent)
    gate_res = agent.evaluate_proposal_through_gates(proposal, narrative, crit_dict)

    assert gate_a_passed is True
    assert gate_res.failing_gate != "GATE_A_EXACT_SLICE"


def test_gate_a_check_fails_when_claimed_text_is_paraphrased_or_hallucinated():
    agent = LLMProposalAgent()
    narrative = "Patient has severe refractory right knee osteoarthritis with medial joint space narrowing."
    crit_dict = {
        "criterion_code": "CRIT-KNEE-01",
        "name": "Osteoarthritis Severity",
        "description": "Severe joint space narrowing",
        "criterion_type": "FINDING_PRESENCE",
        "is_exclusion": False
    }

    # Model returns paraphrased phrase not appearing in note
    paraphrased_quote = "narrowing of the joint space on the right side"
    start, end = agent.locate_claimed_span(narrative, paraphrased_quote)
    assert start == -1 and end == -1

    proposal = LLMProposedSpan(
        criterion_code="CRIT-KNEE-01",
        proposed_status="MET",
        claimed_text=paraphrased_quote,
        char_start=0,
        char_end=0,
        rationale="Paraphrased clinical concept"
    )

    gate_a_passed = evaluate_gate_a(proposal, narrative, crit_dict, agent)
    gate_res = agent.evaluate_proposal_through_gates(proposal, narrative, crit_dict)

    assert gate_a_passed is False
    assert gate_res.failing_gate == "GATE_A_EXACT_SLICE"
    assert "hallucinated" in gate_res.rejection_reason.lower() or "not exist" in gate_res.rejection_reason.lower()


def test_gate_a_check_fails_on_empty_claimed_text():
    agent = LLMProposalAgent()
    narrative = "Patient has severe refractory right knee osteoarthritis."
    crit_dict = {
        "criterion_code": "CRIT-KNEE-01",
        "name": "Osteoarthritis Severity",
        "description": "Severe joint space narrowing",
        "criterion_type": "FINDING_PRESENCE",
        "is_exclusion": False
    }

    proposal = LLMProposedSpan(
        criterion_code="CRIT-KNEE-01",
        proposed_status="MET",
        claimed_text="",
        char_start=0,
        char_end=0,
        rationale="Empty proposal"
    )

    gate_a_passed = evaluate_gate_a(proposal, narrative, crit_dict, agent)
    gate_res = agent.evaluate_proposal_through_gates(proposal, narrative, crit_dict)

    assert gate_a_passed is False
    assert gate_res.failing_gate == "GATE_A_EXACT_SLICE"


def test_production_prompt_default_and_v1_legacy_prompt_preserved():
    """
    Tests that:
    1. Default production prompt is v2_verbatim_worked_example containing verbatim instructions and worked example.
    2. Legacy v1 prompt behavior is strictly preserved under prompt_version='v1_legacy'.
    """
    agent = LLMProposalAgent()
    note = "Patient has severe dyspnea, NYHA class III."

    v2_prompt = agent.build_prompt(
        ehr_text=note,
        ccode="CRIT-TEST-01",
        cname="Heart Failure Symptoms",
        cdesc="NYHA Class III/IV",
        ctype="FINDING_PRESENCE",
        is_excl=False
    )
    assert "CRITICAL INSTRUCTION: You must quote the note exactly." in v2_prompt
    assert "WORKED EXAMPLE:" in v2_prompt
    assert "NYHA class III functional status" in v2_prompt

    v1_prompt = agent.build_prompt(
        ehr_text=note,
        ccode="CRIT-TEST-01",
        cname="Heart Failure Symptoms",
        cdesc="NYHA Class III/IV",
        ctype="FINDING_PRESENCE",
        is_excl=False,
        prompt_version="v1_legacy"
    )
    assert "CRITICAL INSTRUCTION: You must quote the note exactly." not in v1_prompt
    assert "WORKED EXAMPLE:" not in v1_prompt
    assert "You MUST provide the exact verbatim substring (claimed_text) copied directly from the clinical note." in v1_prompt
