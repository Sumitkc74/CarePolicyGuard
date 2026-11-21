"""
Tests for Suggestion Prompt v72:
1. Task 1: Grounded judge-verified MET with unmapped concept is NOT killed by Gate C.
   (test_grounded_judge_verified_met_with_unmapped_concept_not_killed_by_gate_c)
2. Task 2: Guard does not block advocacy/promotion for grounded MET.
   (test_guard_does_not_block_grounded_met)
3. Task 2 Guard grounding check: Genuinely ungrounded MET is still blocked (KYPHO-01 pattern).
   (test_genuinely_ungrounded_met_still_blocked_by_guard)
4. Task 2 Concession arm: Conceded criterion is still blocked (SBRT-01 / SI-01 pattern).
   (test_conceded_criterion_still_blocked_by_guard)
5. Committed map invariant: Exactly 12 concepts, no draft approved.
   (test_committed_concept_map_unchanged_at_12_concepts)
"""

from unittest.mock import MagicMock, patch

from app.core.agentic_guardrails import AgenticGuardrails
from app.core.concept_map import get_concept_map
from app.core.llm_judge import (
    CaseDeferralReview,
    ClinicalEquivalenceJudge,
    CriterionJudgment,
)
from app.schemas.contracts import ClinicalEvidenceSpan


def test_grounded_judge_verified_met_with_unmapped_concept_not_killed_by_gate_c():
    """
    Task 1: When Gate A passes (quote locates verbatim in note)
    AND judge returned MET (judge_verified_met=True)
    BUT Gate C rejects (no matching concept definition in map),
    Gate C must NOT kill the criterion.
    It returns passed=True, is_provisional=True, needs_human_attestation=True.
    """
    ehr = "Patient with acute coronary syndrome undergoing percutaneous intervention with severe coronary stenosis."
    span_text = "severe coronary stenosis"
    s = ehr.index(span_text)
    e = s + len(span_text)

    cand_span = ClinicalEvidenceSpan(
        source_text=span_text,
        start_char=s,
        end_char=e,
        confidence=0.95
    )
    crit = {
        "criterion_code": "CRIT-TEST-01",
        "name": "Coronary Artery Disease",
        "keywords": ["coronary disease"],
        "is_exclusion": False,
    }

    # Case 1: judge_verified_met=False -> Gate C rejects as before
    res_unverified = AgenticGuardrails.evaluate_gate_chain(
        candidate_span=cand_span,
        criterion=crit,
        ehr_narrative=ehr,
        concept_map=None,
        judge_verified_met=False,
        conceded=False,
    )
    assert not res_unverified["passed"]
    assert res_unverified["failing_gate"] == "GATE_C_MAP_CHECK"
    assert res_unverified.get("is_provisional", False) is False

    # Case 2: judge_verified_met=True, not conceded -> Provisional pass!
    res_verified = AgenticGuardrails.evaluate_gate_chain(
        candidate_span=cand_span,
        criterion=crit,
        ehr_narrative=ehr,
        concept_map=None,
        judge_verified_met=True,
        conceded=False,
    )
    assert res_verified["passed"] is True
    assert res_verified["failing_gate"] is None
    assert res_verified["is_provisional"] is True
    assert res_verified["needs_human_attestation"] is True
    assert res_verified["gate_c_rejected"] is True
    assert "queued for human attestation" in res_verified["reason"].lower()


def test_guard_does_not_block_grounded_met():
    """
    Task 2: If a quote locates verbatim in the note (grounded) and was judge-verified MET,
    the guard status-MET arm must NOT block advocacy/promotion.
    """
    from app.agents.pipeline import MultiAgentVerificationPipeline

    ehr = (
        "PROGRESS NOTE: Patient with severe peripheral artery disease presenting with "
        "intermittent claudication and ankle-brachial index of 0.65. "
        "Conservative therapy completed."
    )
    quote = "ankle-brachial index of 0.65"

    pipeline = MultiAgentVerificationPipeline(db=None)

    # Initial judge returns MET with grounded quote
    mock_met = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Objective vascular measurement confirming PAD",
        confidence=0.95,
        status_code="COMPLETED",
    )

    mock_counter = {
        "has_objection": False,
        "objection_type": "NONE",
        "rationale": "No contradiction found",
        "status_code": "COMPLETED",
    }

    mock_review = CaseDeferralReview(
        confirmed_deferrable=False,
        rationale="Criteria satisfied",
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_counter), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync", return_value=mock_review):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V72-GROUNDED",
            policy_id="LCD-PAD",
            ehr_narrative=ehr,
            execution_mode="agentic",
        )

    # Verify that the guard status-MET arm did NOT fire on this grounded quote
    board_records = res.message_board or []
    status_met_blocks = [
        r for r in board_records
        if r.get("metadata", {}).get("guard_arm") == "status-MET"
    ]
    assert len(status_met_blocks) == 0, f"Expected 0 status-MET guard blocks for grounded quote, got {len(status_met_blocks)}"


def test_genuinely_ungrounded_met_still_blocked_by_guard():
    """
    Task 2 & 3: Genuinely ungrounded MET quote (KYPHO-01 pattern: quote does not locate in note)
    must still be blocked by the status-MET guard arm.
    """
    from app.agents.pipeline import MultiAgentVerificationPipeline

    ehr = "PATIENT NOTE: 74-year-old female with osteoporosis. Reports back pain."
    ungrounded_quote = "severe compression fracture with kyphoplasty indicated at T12 after failed analgesics"

    pipeline = MultiAgentVerificationPipeline(db=None)

    # Judge returns MET but with hallucinated / disjoint ungrounded quote
    mock_met_ungrounded = CriterionJudgment(
        status="MET",
        quoted_evidence=ungrounded_quote,
        rationale="Satisfies criterion according to clinical reasoning",
        confidence=0.90,
        status_code="COMPLETED",
    )

    mock_review = CaseDeferralReview(
        confirmed_deferrable=True,
        rationale="Ungrounded evidence",
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_met_ungrounded), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync", return_value=mock_review):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V72-UNGROUNDED",
            policy_id="LCD-KYPHO",
            ehr_narrative=ehr,
            execution_mode="agentic",
        )

    # Verify status-MET arm blocked the ungrounded quote
    board_records = res.message_board or []
    status_met_blocks = [
        r for r in board_records
        if r.get("metadata", {}).get("guard_arm") == "status-MET"
    ]
    assert len(status_met_blocks) >= 1, "Expected status-MET guard block for genuinely ungrounded quote"
    block_msg = status_met_blocks[0]
    assert "ungrounded" in block_msg.get("content", "").lower()
    assert block_msg.get("metadata", {}).get("genuinely_ungrounded") is True


def test_conceded_criterion_still_blocked_by_guard():
    """
    Task 2 & 3: Conceded criterion (SBRT-01 / SI-01 pattern) must still be strictly blocked
    by the concession arm of the guard. Concession is final.
    """
    from app.agents.pipeline import MultiAgentVerificationPipeline

    ehr = (
        "PATIENT RECORD: 62-year-old patient evaluated for stereotactic body radiation therapy. "
        "Lesion measures 6.5 cm in greatest dimension. Note indicates spine adjacent."
    )
    quote = "Lesion measures 6.5 cm in greatest dimension"

    pipeline = MultiAgentVerificationPipeline(db=None)

    # Initial judge returns MET
    mock_met = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Lesion size documented",
        confidence=0.90,
        status_code="COMPLETED",
    )

    # Counter-reading raises fatal ANATOMIC_MISMATCH / TEMPORAL objection
    mock_fatal_obj = {
        "has_objection": True,
        "objection_type": "ANATOMIC_MISMATCH",
        "rationale": "Lesion size exceeds max threshold of 5 cm",
        "status_code": "COMPLETED",
    }

    # Defense fails to resolve it, leading to concession
    mock_failed_defense = MagicMock(
        has_resolution=False,
        defense_quote="",
        rationale="Cannot resolve size mismatch",
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    mock_review = CaseDeferralReview(
        confirmed_deferrable=True,
        rationale="Conceded in debate",
        elapsed_ms=10.0,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_met), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_fatal_obj), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_failed_defense), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync", return_value=mock_review):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V72-CONCEDED",
            policy_id="LCD-SBRT",
            ehr_narrative=ehr,
            execution_mode="agentic",
        )

    # Verify concession arm blocked advocacy
    board_records = res.message_board or []
    concession_blocks = [
        r for r in board_records
        if r.get("metadata", {}).get("guard_arm") == "concession"
    ]
    assert len(concession_blocks) >= 1, "Expected concession arm guard block for conceded criterion"
    assert "concession is final" in concession_blocks[0].get("content", "").lower()


def test_committed_concept_map_unchanged_at_12_concepts():
    """
    Task 3: Committed ConceptMap must remain exactly 12 concepts, with 0 drafts approved.
    No concept was added, approved, or attested in the committed map.
    """
    cmap = get_concept_map()
    assert cmap.total_concepts == 12, f"Committed ConceptMap must have exactly 12 concepts, found {cmap.total_concepts}"
    for cid, cdef in cmap._concepts.items():
        assert not getattr(cdef, "is_draft", False), f"Concept {cid} must not be draft in committed map"
