"""
Tests for AgenticGuardrails (Task 3).
Verifies that deterministic guardrails cannot be bypassed by any agent action:
1. Verbatim grounding: reject spans not exactly matching note text or offsets.
2. Gate chain: reject candidates that fail negation, family history, or ConceptMap equivalence.
3. Grounded negative wins: proven NOT_MET or MET exclusion is never overturned by LLM EQUIVALENT.
4. Operational budget exhaustion: hard caps trigger BudgetExhaustionHalt.
5. Safety floors: weakest-link < 0.65 or tau < 0.85 halts auto-approval.
"""

from unittest.mock import MagicMock

import pytest

from app.core.agentic_guardrails import (
    AgenticGuardrails,
    BudgetExhaustionHalt,
    GuardrailViolationError,
)
from app.core.concept_map import ConceptDefinition, ConceptMap
from app.schemas.contracts import (
    ClinicalEvidenceSpan,
    CriterionAssessment,
    DeterminationStatus,
)


@pytest.fixture
def sample_concept_map() -> ConceptMap:
    cmap = ConceptMap()
    cmap.register_concept(
        ConceptDefinition(
            concept_id="CONCEPT-PROSTATE-CANCER",
            canonical_name="prostate cancer",
            domain="oncology",
            accepted_terms=["prostate adenocarcinoma", "prostatic neoplasm", "pca of prostate"],
            prohibited_near_misses=["lung adenocarcinoma", "colorectal adenocarcinoma"],
            source_reason="Established oncology synonymy",
        )
    )
    return cmap


def test_verbatim_grounding_rejects_hallucinated_text() -> None:
    note = "Patient has localized prostate adenocarcinoma diagnosed on biopsy."
    # Text in span is altered from the true note slice
    span = ClinicalEvidenceSpan(
        source_text="Patient has metastatic lung carcinoma",
        start_char=12,
        end_char=35,
        clinical_section="OBJECTIVE",
        confidence=0.95,
    )
    assessment = CriterionAssessment(
        criterion_id="CRIT-1",
        criterion_code="CRIT-1",
        name="Prostate Cancer",
        description="Documentation of prostate cancer",
        status=DeterminationStatus.MET,
        raw_confidence=0.95,
        clinical_rationale="Found span",
        verified_spans=[span],
    )

    with pytest.raises(GuardrailViolationError) as exc_info:
        AgenticGuardrails.verify_verbatim_grounding(note, assessment)
    assert "Span text mismatch" in str(exc_info.value)


def test_verbatim_grounding_rejects_out_of_bounds_offsets() -> None:
    note = "Short note."
    span = ClinicalEvidenceSpan(
        source_text="Short note.",
        start_char=0,
        end_char=500,  # exceeds length
        clinical_section="OBJECTIVE",
        confidence=0.95,
    )
    assessment = CriterionAssessment(
        criterion_id="CRIT-1",
        criterion_code="CRIT-1",
        name="Prostate Cancer",
        description="Documentation of prostate cancer",
        status=DeterminationStatus.MET,
        raw_confidence=0.95,
        clinical_rationale="Found span",
        verified_spans=[span],
    )

    with pytest.raises(GuardrailViolationError) as exc_info:
        AgenticGuardrails.verify_verbatim_grounding(note, assessment)
    assert "Invalid span offsets" in str(exc_info.value)


def test_verbatim_grounding_rejects_met_with_zero_spans() -> None:
    note = "Patient has localized prostate adenocarcinoma diagnosed on biopsy."
    assessment = CriterionAssessment(
        criterion_id="CRIT-1",
        criterion_code="CRIT-1",
        name="Prostate Cancer",
        description="Documentation of prostate cancer",
        status=DeterminationStatus.MET,
        raw_confidence=0.95,
        clinical_rationale="Found span",
        verified_spans=[],  # Zero spans
    )

    with pytest.raises(GuardrailViolationError) as exc_info:
        AgenticGuardrails.verify_verbatim_grounding(note, assessment)
    assert "zero verified evidence spans" in str(exc_info.value)


def test_gate_chain_fails_on_negation(sample_concept_map: ConceptMap) -> None:
    note = "Biopsy reveals no evidence of prostate adenocarcinoma."
    # Slice matches exactly, but context is negated
    target = "prostate adenocarcinoma"
    start = note.index(target)
    end = start + len(target)
    span = ClinicalEvidenceSpan(
        source_text=target,
        start_char=start,
        end_char=end,
        clinical_section="OBJECTIVE",
        confidence=0.92,
    )
    criterion = {
        "criterion_code": "CRIT-PCA",
        "name": "prostate cancer",
        "description": "Biopsy-proven prostate cancer",
    }

    res = AgenticGuardrails.evaluate_gate_chain(span, criterion, note, concept_map=sample_concept_map)
    assert res["passed"] is False
    assert res["failing_gate"] == "GATE_B_SEMANTIC"
    assert "negated" in res["reason"].lower()


def test_gate_chain_fails_on_family_history(sample_concept_map: ConceptMap) -> None:
    note = "Family history: Father diagnosed with prostate adenocarcinoma at age 68."
    target = "prostate adenocarcinoma"
    start = note.index(target)
    end = start + len(target)
    span = ClinicalEvidenceSpan(
        source_text=target,
        start_char=start,
        end_char=end,
        clinical_section="OBJECTIVE",
        confidence=0.92,
    )
    criterion = {
        "criterion_code": "CRIT-PCA",
        "name": "prostate cancer",
        "description": "Biopsy-proven prostate cancer",
    }

    res = AgenticGuardrails.evaluate_gate_chain(span, criterion, note, concept_map=sample_concept_map)
    assert res["passed"] is False
    assert res["failing_gate"] == "GATE_B_SEMANTIC"
    assert "family" in res["reason"].lower()


def test_gate_chain_fails_on_prohibited_near_miss(sample_concept_map: ConceptMap) -> None:
    note = "Pathology confirmed lung adenocarcinoma with mediastinal involvement."
    target = "lung adenocarcinoma"
    start = note.index(target)
    end = start + len(target)
    span = ClinicalEvidenceSpan(
        source_text=target,
        start_char=start,
        end_char=end,
        clinical_section="OBJECTIVE",
        confidence=0.92,
    )
    criterion = {
        "criterion_code": "CRIT-PCA",
        "name": "prostate cancer",
        "description": "Biopsy-proven prostate cancer",
    }

    res = AgenticGuardrails.evaluate_gate_chain(span, criterion, note, concept_map=sample_concept_map)
    assert res["passed"] is False
    assert res["failing_gate"] == "GATE_C_MAP_CHECK"
    assert "prohibited_near_miss" in res["reason"].lower() or "rejected" in res["reason"].lower()


def test_gate_chain_fails_on_agent3_veto(sample_concept_map: ConceptMap) -> None:
    note = "Pathology confirms prostate adenocarcinoma."
    target = "prostate adenocarcinoma"
    start = note.index(target)
    end = start + len(target)
    span = ClinicalEvidenceSpan(
        source_text=target,
        start_char=start,
        end_char=end,
        clinical_section="OBJECTIVE",
        confidence=0.92,
    )
    criterion = {
        "criterion_code": "CRIT-PCA",
        "name": "prostate cancer",
        "description": "Biopsy-proven prostate cancer",
    }

    # Mock Agent 3 raising a hallucination flag
    mock_verifier = MagicMock()
    mock_audit = MagicMock()
    mock_audit.hallucination_flag = True
    mock_audit.grounding_status = False
    mock_audit.audit_notes = "Incompatible clinical timeline"
    mock_verifier.audit_assessment.return_value = mock_audit

    res = AgenticGuardrails.evaluate_gate_chain(
        span, criterion, note, concept_map=sample_concept_map, verifier_agent=mock_verifier
    )
    assert res["passed"] is False
    assert res["failing_gate"] == "GATE_C_AGENT3_VETO"
    assert "Incompatible clinical timeline" in res["reason"]


def test_grounded_negative_wins_over_llm_verdict() -> None:
    # 1. Proven NOT_MET inclusion criterion cannot be overturned by LLM EQUIVALENT
    status = AgenticGuardrails.reconcile_deterministic_and_llm(
        deterministic_status=DeterminationStatus.NOT_MET,
        llm_verdict="EQUIVALENT",
        is_exclusion=False,
    )
    assert status == DeterminationStatus.NOT_MET

    # 2. Proven MET exclusion criterion (disqualifying) cannot be overturned
    status = AgenticGuardrails.reconcile_deterministic_and_llm(
        deterministic_status=DeterminationStatus.MET,
        llm_verdict="EQUIVALENT",
        is_exclusion=True,
    )
    assert status == DeterminationStatus.MET

    # 3. Only INSUFFICIENT_EVIDENCE may be promoted to MET by EQUIVALENT
    status = AgenticGuardrails.reconcile_deterministic_and_llm(
        deterministic_status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
        llm_verdict="EQUIVALENT",
        is_exclusion=False,
    )
    assert status == DeterminationStatus.MET

    # 4. INSUFFICIENT_EVIDENCE with NOT_EQUIVALENT remains INSUFFICIENT_EVIDENCE
    status = AgenticGuardrails.reconcile_deterministic_and_llm(
        deterministic_status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
        llm_verdict="NOT_EQUIVALENT",
        is_exclusion=False,
    )
    assert status == DeterminationStatus.INSUFFICIENT_EVIDENCE


def test_budget_exhaustion_halts() -> None:
    # 1. LLM Calls > 3
    with pytest.raises(BudgetExhaustionHalt) as exc_calls:
        AgenticGuardrails.check_budgets(llm_calls=4, elapsed_seconds=5.0, agent_turns=5, criterion_debate_rounds=1)
    assert "LLM_CALLS" in str(exc_calls.value)

    # 2. Time > 30.0s
    with pytest.raises(BudgetExhaustionHalt) as exc_time:
        AgenticGuardrails.check_budgets(llm_calls=2, elapsed_seconds=31.0, agent_turns=5, criterion_debate_rounds=1)
    assert "LLM_TIME_SECONDS" in str(exc_time.value)

    # 3. Agent Turns > 25
    with pytest.raises(BudgetExhaustionHalt) as exc_turns:
        AgenticGuardrails.check_budgets(llm_calls=2, elapsed_seconds=10.0, agent_turns=26, criterion_debate_rounds=1)
    assert "AGENT_TURNS" in str(exc_turns.value)

    # 4. Debate Rounds > 2
    with pytest.raises(BudgetExhaustionHalt) as exc_rounds:
        AgenticGuardrails.check_budgets(llm_calls=2, elapsed_seconds=10.0, agent_turns=10, criterion_debate_rounds=3)
    assert "DEBATE_ROUNDS" in str(exc_rounds.value)


def test_confidence_floors_halt() -> None:
    crit_met = CriterionAssessment(
        criterion_id="CRIT-1",
        criterion_code="CRIT-1",
        name="Prostate Cancer",
        description="Biopsy documentation",
        status=DeterminationStatus.MET,
        raw_confidence=0.60,  # Below 0.65 floor!
        clinical_rationale="Under-confident span",
        is_exclusion=False,
    )

    reason = AgenticGuardrails.check_confidence_floors(
        criteria_assessments=[crit_met],
        calibrated_aggregate_confidence=0.90,
    )
    assert reason is not None
    assert "Weakest-link safety floor breached" in reason
    assert "0.60" in reason

    # Tau breach
    crit_met.raw_confidence = 0.90
    reason_tau = AgenticGuardrails.check_confidence_floors(
        criteria_assessments=[crit_met],
        calibrated_aggregate_confidence=0.82,  # Below 0.85 tau!
    )
    assert reason_tau is not None
    assert "safety threshold tau" in reason_tau
