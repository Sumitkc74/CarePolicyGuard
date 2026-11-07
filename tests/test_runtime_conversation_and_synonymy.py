"""
Tests for Task 2: Runtime Inter-Agent Conversation and LLM Synonymy Resolution.
Protocol:
- Triggered only when deterministic evaluator fails to match a criterion.
- 4 Sequential Gates: (a) exact character slice, (b) 5D semantic check, (c) concept map check, (d) Agent 3 cross-examination.
- Hard limits: at most 3 calls per adjudication, 30 seconds total time.
- All messages written to AgentConversationAuditBus.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.llm_proposer import (
    GateEvaluationResult,
    LLMProposalAgent,
    LLMProposedSpan,
    ProposalResult,
)
from app.core.concept_map import ConceptReviewQueue, get_concept_map
from app.schemas.agent_messages import (
    AgentConversationAuditBus,
    AgentMessageType,
)
from app.schemas.contracts import DeterminationStatus, VerificationAuditResult


def test_mocked_llm_correct_synonymy_proposal_accepted():
    """
    Asserts that a valid synonymy proposal (prostate adenocarcinoma for prostate cancer)
    passes all 4 gates (a: slice, b: semantic, c: concept map, d: Agent 3) and is accepted.
    """
    proposer = LLMProposalAgent()
    narrative = "[SYNTHETIC] 66yo male with intermediate-risk prostate adenocarcinoma. No metastases."
    start = narrative.find("prostate adenocarcinoma")
    end = start + len("prostate adenocarcinoma")
    claimed = narrative[start:end]

    criterion = {
        "criterion_code": "CRIT-IMRT-01",
        "name": "Prostate Cancer",
        "description": "Biopsy-proven prostate cancer",
        "keywords": ["prostate cancer"]
    }

    proposal = LLMProposedSpan(
        criterion_code="CRIT-IMRT-01",
        proposed_status=DeterminationStatus.MET,
        claimed_text=claimed,
        char_start=start,
        char_end=end,
        claimed_equivalence="Prostate adenocarcinoma is a histologic subtype of prostate cancer"
    )

    # Mock Agent 3 to affirm validity
    mock_verifier = MagicMock()
    mock_audit = VerificationAuditResult(
        criterion_code="CRIT-IMRT-01",
        grounding_status=True,
        hallucination_flag=False,
        unverified_omission_flag=False,
        offset_drift_detected=False,
        contradiction_detected=False,
        calibrated_confidence=0.92,
        audit_notes="Grounded patient fact; confirmed subtype equivalence."
    )
    mock_verifier.audit_assessment.return_value = mock_audit

    res = proposer.evaluate_proposal_through_gates(
        proposal=proposal,
        sanitized_ehr=narrative,
        criterion=criterion,
        verifier_agent=mock_verifier
    )

    assert res.passed is True
    assert res.failing_gate is None
    assert res.verified_span is not None
    assert res.verified_span.source_text == claimed


def test_mocked_llm_hallucinated_span_rejected_by_gate_a():
    """Gate A exact slice check must reject hallucinated text not in EHR."""
    proposer = LLMProposalAgent()
    narrative = "Patient denies any urinary symptoms or history of cancer."
    criterion = {"criterion_code": "CRIT-IMRT-01", "name": "Prostate Cancer"}

    proposal = LLMProposedSpan(
        criterion_code="CRIT-IMRT-01",
        proposed_status=DeterminationStatus.MET,
        claimed_text="biopsy-proven prostate adenocarcinoma",  # Hallucinated string!
        char_start=0,
        char_end=35,
        claimed_equivalence="Subtype match"
    )

    res = proposer.evaluate_proposal_through_gates(
        proposal=proposal,
        sanitized_ehr=narrative,
        criterion=criterion
    )

    assert res.passed is False
    assert res.failing_gate == "GATE_A_EXACT_SLICE"
    assert "hallucinated" in res.rejection_reason.lower() or "mismatch" in res.rejection_reason.lower()


def test_mocked_llm_cross_concept_claim_rejected_and_defers():
    """
    Gate C Map Check: If the LLM claims cross-concept equivalence (e.g. rectal sparing
    for a spinal cord criterion), Gate C must reject it, log to human review queue, and defer.
    The LLM must never silently decide a coverage judgment.
    """
    ConceptReviewQueue.clear()
    proposer = LLMProposalAgent()
    narrative = "Inverse IMRT plan delivers concave escalation with rectal wall sparing."
    start = narrative.find("rectal wall sparing")
    end = start + len("rectal wall sparing")

    criterion = {
        "criterion_code": "CRIT-IMRT-SPINAL",
        "name": "Tumours Adjacent to Spinal Cord",
        "keywords": ["adjacent to spinal cord"]
    }

    proposal = LLMProposedSpan(
        criterion_code="CRIT-IMRT-SPINAL",
        proposed_status=DeterminationStatus.MET,
        claimed_text=narrative[start:end],
        char_start=start,
        char_end=end,
        claimed_equivalence="Rectal sparing achieves equivalent normal tissue protection as spinal cord proximity"
    )

    res = proposer.evaluate_proposal_through_gates(
        proposal=proposal,
        sanitized_ehr=narrative,
        criterion=criterion
    )

    assert res.passed is False
    assert res.failing_gate == "GATE_C_MAP_CHECK"
    assert "concept map check failed" in res.rejection_reason.lower()

    # Must be recorded in review queue
    pending = ConceptReviewQueue.get_pending()
    assert len(pending) >= 1
    assert any("rectal wall sparing" in p.proposed_span for p in pending)


def test_mocked_llm_budget_limits_and_timeout():
    """
    Hard limits: At most 3 LLM calls per adjudication and 30-second budget.
    Exceeding either skips with SKIPPED_TIMEOUT and falls back to deterministic.
    """
    proposer = LLMProposalAgent()
    proposer.enabled = True
    proposer.reset_case_budget()

    criterion = {"criterion_code": "CRIT-TEST-01", "name": "Test Criterion"}
    text = "Clinical note text."

    # Simulate 3 prior calls
    proposer.case_call_count = 3
    res = proposer.propose_spans_sync(sanitized_ehr=text, criterion=criterion)
    assert res.status == "SKIPPED_TIMEOUT"
    assert len(res.proposals) == 0

    # Simulate time budget exceeded
    proposer.case_call_count = 0
    proposer.case_elapsed_ms = 31000.0  # > 30,000 ms
    res_time = proposer.propose_spans_sync(sanitized_ehr=text, criterion=criterion)
    assert res_time.status == "SKIPPED_TIMEOUT"


def test_conversation_audit_trail_recorded_and_bounded():
    """
    Verifies that run_synonymy_conversation() logs the complete structured conversation
    into AgentConversationAuditBus and terminates within 3 rounds.
    """
    AgentConversationAuditBus.clear_ledger()
    proposer = LLMProposalAgent()
    proposer.enabled = True
    proposer.reset_case_budget()

    narrative = "[SYNTHETIC] Biopsy confirmed prostate adenocarcinoma Gleason 7."
    start = narrative.find("prostate adenocarcinoma")
    end = start + len("prostate adenocarcinoma")

    criterion = {
        "criterion_code": "CRIT-IMRT-01",
        "name": "Prostate Cancer",
        "description": "Clinically localized prostate cancer"
    }

    mock_span = LLMProposedSpan(
        criterion_code="CRIT-IMRT-01",
        proposed_status=DeterminationStatus.MET,
        claimed_text=narrative[start:end],
        char_start=start,
        char_end=end,
        claimed_equivalence="Adenocarcinoma is the histologic subtype of prostate cancer"
    )

    # Patch proposer to return mock_span without network
    with patch.object(proposer, "propose_spans_sync", return_value=ProposalResult(([mock_span], "COMPLETED", 150.0))):
        span, msgs = proposer.run_synonymy_conversation(
            criterion=criterion,
            ehr_narrative=narrative,
            failed_reason="Exact string 'prostate cancer' not found",
            case_id="CASE-SYN-AUDIT-01"
        )

    assert span is not None
    assert len(msgs) >= 4  # Query, Proposal, Challenge, Defense, Accept
    rounds = [m.round_number for m in msgs]
    assert max(rounds) <= 3  # Hard-bounded to <= 3 rounds!

    # Check audit ledger
    all_msgs = AgentConversationAuditBus.all_messages()
    types = [m.message_type for m in all_msgs]
    assert AgentMessageType.SYNONYMY_QUERY in types
    assert AgentMessageType.SYNONYMY_PROPOSAL in types
    assert AgentMessageType.CHALLENGE in types
    assert AgentMessageType.ACCEPT in types


def test_live_ollama_model_smoke_test():
    """
    Live smoke test against real local Ollama runtime on 127.0.0.1:11434.
    If Ollama is reachable and model is available, verifies live inference.
    If not reachable, cleanly skips with clear reason (skip is not pass).
    """
    proposer = LLMProposalAgent(
        endpoint_url="http://127.0.0.1:11434/v1/chat/completions",
        model_name="qwen2.5:3b",
        timeout_seconds=20.0
    )
    proposer.enabled = True

    if not proposer.is_available():
        pytest.skip("Local Ollama runtime on 127.0.0.1:11434 not reachable or qwen2.5:3b not ready")

    text = "Assessment: 66yo male with intermediate-risk prostate adenocarcinoma. Proceed with radiation."
    criterion = {
        "criterion_code": "CRIT-IMRT-01",
        "name": "Prostate Cancer",
        "description": "Biopsy-proven prostate cancer requiring radiation"
    }

    res = proposer.propose_spans_sync(sanitized_ehr=text, criterion=criterion)
    assert res.status in ("COMPLETED", "NO_PROPOSALS")
    assert res.elapsed_ms < 30000.0  # Within 30 second budget!
    if res.proposals:
        prop = res.proposals[0]
        assert "adenocarcinoma" in prop.claimed_text.lower() or "prostate" in prop.claimed_text.lower()
