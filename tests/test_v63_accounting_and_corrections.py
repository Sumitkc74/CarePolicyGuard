"""
Tests for v63 Accounting and Corrections (Task 3).
Pins the classification of empty-quote advocacy rejections:
A synthetic advocacy record with an empty quote must classify as empty_quote,
not gate_b_or_c or Gate A.
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


def test_synthetic_advocacy_empty_quote_classifies_as_empty_quote(sample_vignette):
    """
    Task 3: A synthetic advocacy record with an empty quote must post CHALLENGE
    with empty_quote=True and classify as empty_quote, NOT gate_b_or_c.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    # Initial judge returns NOT_MET for CRIT-IMRT-02 to trigger Agent 3 advocacy
    mock_not_met = CriterionJudgment(
        status="NOT_MET",
        quoted_evidence="",
        rationale="Criteria not met in clinical text.",
        confidence=0.85,
        status_code="COMPLETED",
    )

    # Synthetic advocacy record returning empty quote (no supporting evidence)
    mock_advocacy_empty = AdvocacyResult(
        advocacy_quote="",
        rationale="The clinical note contains no evidence supporting organ sparing constraints.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_not_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy_empty):
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-EMPTY-QUOTE",
            policy_id="LCD-IMRT",
            ehr_narrative=sample_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []

    # 1. Assert board has CHALLENGE with empty_quote=True
    challenge_msgs = [
        m for m in board_msgs
        if m.get("message_type") in ("CHALLENGE", getattr(BoardMessageType, "CHALLENGE", "CHALLENGE"))
        and m.get("metadata", {}).get("advocacy_rejected") is True
    ]
    assert len(challenge_msgs) >= 1, "Must have an advocacy challenge rejection on the board"
    rejection = challenge_msgs[0]
    assert rejection.get("metadata", {}).get("empty_quote") is True, "Rejection metadata must have empty_quote=True"
    assert "failing_gate" not in rejection.get("metadata", {}), "Empty quote rejection must not have failing_gate set"

    # 2. Assert runner accounting classifies it under empty_quote
    advocacy_rejections_gate_a = 0
    advocacy_rejections_gate_b_or_c = 0
    advocacy_rejections_empty_quote = 0

    adv_q = ""
    for m in board_msgs:
        mtype = m.get("message_type")
        agent = m.get("agent", "")
        meta = m.get("metadata", {})
        content = m.get("content", "")

        if agent.startswith("Agent 3") and mtype == "ADVOCACY":
            adv_q = meta.get("advocacy_quote", "")

        if agent.startswith("Agent 3") and mtype == "CHALLENGE" and meta.get("advocacy_rejected"):
            fg = meta.get("failing_gate") or meta.get("gate")
            if meta.get("empty_quote") or not adv_q or adv_q.strip() == "":
                advocacy_rejections_empty_quote += 1
            elif fg == "Gate A" or "Gate A" in content:
                advocacy_rejections_gate_a += 1
            else:
                advocacy_rejections_gate_b_or_c += 1

    assert advocacy_rejections_empty_quote == 1, "Synthetic empty quote must classify under empty_quote"
    assert advocacy_rejections_gate_b_or_c == 0, "Synthetic empty quote must NOT classify under gate_b_or_c"
    assert advocacy_rejections_gate_a == 0, "Synthetic empty quote must NOT classify under gate_a"


def test_advocate_preserves_empty_quote_when_model_returns_empty():
    """
    Task 3: Verifies that when the model returns an empty quote, generate_advocacy_sync
    preserves the empty quote rather than fabricating an arbitrary candidate quote from the note.
    """
    judge = ClinicalEquivalenceJudge()
    crit = {
        "criterion_code": "CRIT-TEST-01",
        "name": "Test Requirement",
        "description": "Specific statutory criteria not present in note.",
    }
    note = "This is a note with zero evidence for the criterion."

    # When LLM returns empty quote
    with patch("httpx.Client.post") as mock_post:
        mock_resp = mock_post.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"advocacy_quote": "", "rationale": "No supporting evidence exists in note."}'
                }
            }]
        }
        res = judge.generate_advocacy_sync(crit, note)

    assert res.advocacy_quote == "", f"Expected empty advocacy_quote, got: {res.advocacy_quote!r}"
    assert "No supporting evidence" in res.rationale
