import json
from pathlib import Path

import pytest

from app.agents.abstention_gate import CalibratedAbstentionGate
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core import concept_map as cm_mod
from app.schemas.contracts import (
    AdjudicationDecision,
    CriterionAssessment,
    DeterminationStatus,
)
from scripts.re_evaluate_in_sample_comparison import build_in_sample_concept_map

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_VIGNETTES_FILE = REPO_ROOT / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"


@pytest.fixture(autouse=True)
def restore_concept_map():
    """Ensure global ConceptMap singleton is restored after tests run."""
    orig_map = cm_mod._GLOBAL_CONCEPT_MAP
    yield
    cm_mod._GLOBAL_CONCEPT_MAP = orig_map


def _load_dev_vignette(vignette_id: str) -> dict:
    with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
        vignettes = json.load(f)
    for vig in vignettes:
        if vig.get("vignette_id") == vignette_id:
            return vig
    raise ValueError(f"Vignette {vignette_id} not found in {DEV_VIGNETTES_FILE}")


def test_agentic_short_circuit_dev_lcd_acdf_neg_e2e():
    """
    End-to-end regression test: DEV-LCD-ACDF-NEG triggers a statutory exclusion
    and must short-circuit to DENIED without raising ZeroDivisionError in agentic mode.
    """
    in_sample_map, _, _, _ = build_in_sample_concept_map()
    cm_mod._GLOBAL_CONCEPT_MAP = in_sample_map

    vig = _load_dev_vignette("DEV-LCD-ACDF-NEG")
    pipeline = MultiAgentVerificationPipeline(db=None)

    adj = pipeline.adjudicate_sync(
        patient_id="PT-TEST-ACDF-NEG",
        policy_id=vig["policy_id"],
        ehr_narrative=vig["ehr_narrative"],
        execution_mode="agentic",
        save_record=False,
    )

    assert adj.adjudication_decision == AdjudicationDecision.DENIED
    assert "Statutory exclusion" in (adj.abstention_reason or "")

    # Verify message board records intact
    board_msgs = adj.message_board or []
    msg_types = [m.get("message_type") for m in board_msgs]
    assert "ASSESSMENT_PROPOSED" in msg_types
    assert "DECISION" in msg_types

    # Find the DECISION message on board
    decision_msgs = [m for m in board_msgs if m.get("message_type") == "DECISION"]
    assert len(decision_msgs) >= 1
    assert "DENIED" in decision_msgs[0].get("content", "")
    assert decision_msgs[0].get("metadata", {}).get("statutory_exclusion") is True


def test_agentic_short_circuit_second_dev_vignette_lcd_aci_neg():
    """
    Second case regression test: DEV-LCD-ACI-NEG triggers CRIT-ACI-EXCL-01
    (diffuse osteoarthritis exclusion) and must short-circuit to DENIED in agentic mode.
    """
    in_sample_map, _, _, _ = build_in_sample_concept_map()
    cm_mod._GLOBAL_CONCEPT_MAP = in_sample_map

    vig = _load_dev_vignette("DEV-LCD-ACI-NEG")
    pipeline = MultiAgentVerificationPipeline(db=None)

    adj = pipeline.adjudicate_sync(
        patient_id="PT-TEST-ACI-NEG",
        policy_id=vig["policy_id"],
        ehr_narrative=vig["ehr_narrative"],
        execution_mode="agentic",
        save_record=False,
    )

    assert adj.adjudication_decision == AdjudicationDecision.DENIED
    assert "Statutory exclusion" in (adj.abstention_reason or "")


def test_abstention_gate_defensive_guard_empty_audit_results():
    """
    Defensive guard test: CalibratedAbstentionGate.evaluate must never raise
    ZeroDivisionError when audit_results is empty. It must return a safe deferral.
    """
    gate = CalibratedAbstentionGate(tau=0.85)

    ca = CriterionAssessment(
        criterion_id="CRIT-TEST-01",
        criterion_code="CRIT-TEST-01",
        name="Test Criterion",
        description="Synthetic test criterion description",
        status=DeterminationStatus.MET,
        clinical_rationale="Synthetic test criterion",
        raw_confidence=0.90,
        is_exclusion=False,
        verified_spans=[],
    )

    # criteria_assessments non-empty, audit_results empty
    decision, abstention_status, _raw_conf, cal_conf, reason, _notes = gate.evaluate(
        criteria_assessments=[ca],
        audit_results=[],
    )

    assert decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert abstention_status is True
    assert "audit" in reason.lower() or "empty" in reason.lower() or "no verification" in reason.lower()
    assert cal_conf == 0.0


def test_abstention_gate_defensive_guard_empty_criteria_assessments():
    """
    Defensive guard test: CalibratedAbstentionGate.evaluate with empty criteria_assessments
    must return a safe deferral without raising.
    """
    gate = CalibratedAbstentionGate(tau=0.85)

    decision, abstention_status, _raw_conf, cal_conf, _reason, _notes = gate.evaluate(
        criteria_assessments=[],
        audit_results=[],
    )

    assert decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert abstention_status is True
    assert cal_conf == 0.0
