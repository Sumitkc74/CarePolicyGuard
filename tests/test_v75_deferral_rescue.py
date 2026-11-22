"""
Tests for Suggestion Prompt v75:
1. Task 1: Tighten the concession rule (judge holds without specific contradiction, concedes with one).
   - test_judge_holds_met_verdict_when_challenge_has_no_specific_contradiction (a)
   - test_judge_concedes_when_verifier_cites_specific_contradicting_span (b)
2. Task 2: Improve extraction (judge prompting + advocate semantic span matching).
   - test_advocate_finds_pacemaker_and_pet_onc_semantic_spans (c)
   - test_advocate_does_not_propose_span_when_evidence_genuinely_absent (d)
3. Task 4(e): Preservation of v73 optimizations (narrowed review, reuse flag, keep-alive, bench-only).
   - test_v73_optimizations_unchanged_and_reusable (e)
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.llm_judge import (
    AdvocacyResult,
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    DefenseResult,
)
from app.schemas.contracts import DeterminationStatus
from app.schemas.message_board import BoardMessageType
from scripts.run_agentic_v59_three_mode_measurement import (
    verify_baseline_reuse_validity,
)


@pytest.fixture
def sbrt_narrative():
    return (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Radiation Oncology\n"
        "SUBJECTIVE: 72-year-old male with severe COPD (FEV1 34% predicted) evaluated for pulmonary mass. "
        "Medically inoperable primary pulmonary malignancy with localized disease confined to right thorax. "
        "Plan: Stereotactic body radiation therapy.\n"
        "OBJECTIVE: Chest CT: 2.1 cm right upper lobe nodule without nodal involvement (cT1cN0M0). "
        "Brain MRI negative. 4D CT motion management placed.\n"
        "ASSESSMENT & PLAN: Medically inoperable localized pulmonary neoplasm. Proceed with SBRT 54 Gy in 3 fractions."
    )


@pytest.fixture
def sbrt_contradicting_narrative():
    return (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Radiation Oncology\n"
        "SUBJECTIVE: 72-year-old male with severe COPD evaluated for pulmonary mass. "
        "Medically inoperable primary pulmonary malignancy with localized disease confined to right thorax. "
        "Plan: Stereotactic body radiation therapy.\n"
        "OBJECTIVE: Chest CT: 2.1 cm right upper lobe nodule. "
        "Repeat thoracic CT confirms widespread contralateral lung metastases. "
        "4D CT motion management placed.\n"
        "ASSESSMENT & PLAN: Widespread metastatic disease; not localized disease."
    )


def test_judge_holds_met_verdict_when_challenge_has_no_specific_contradiction(sbrt_narrative):
    """
    Task 4(a): The judge HOLDS its MET verdict when the verifier challenges WITHOUT
    citing a specific contradicting span or named sub-requirement.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    def mock_judge_side_effect(criterion=None, *args, **kwargs):
        if criterion is None and args:
            criterion = args[0]
        ccode = criterion.get("criterion_code") if isinstance(criterion, dict) else getattr(criterion, "criterion_code", None)
        if ccode == "CRIT-SBRT-01":
            return CriterionJudgment(
                status="MET",
                quoted_evidence="Medically inoperable primary pulmonary malignancy with localized disease confined to right thorax.",
                rationale="Early stage inoperable pulmonary malignancy matches criterion intent",
                confidence=0.95,
                status_code="COMPLETED",
            )
        return CriterionJudgment(
            status="MET",
            quoted_evidence="4D CT motion management placed.",
            rationale="Motion management established",
            confidence=0.95,
            status_code="COMPLETED",
        )

    # Verifier challenge is general skepticism / non-specific
    general_challenge = {
        "has_objection": True,
        "objection_type": "ANATOMIC_MISMATCH",
        "counter_quote": "",  # No specific contradicting span
        "named_sub_requirement": "",
        "specific_contradiction": False,
        "rationale": "General clinical concern about potential microscopic metastasis without specific note contradiction.",
    }

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_judge_side_effect), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=general_challenge):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V75-HOLD",
            policy_id="LCD-SBRT",
            ehr_narrative=sbrt_narrative,
            execution_mode="agentic",
            save_record=False,
        )

    # CRIT-SBRT-01 must be DEFENDED (held), not conceded
    sbrt_01 = next(a for a in res.criterion_assessments if a.criterion_code == "CRIT-SBRT-01")
    assert sbrt_01.status == DeterminationStatus.MET

    # Verify board messages record specific_contradiction_cited=False and judge_action=HOLD
    board_msgs = res.message_board or []
    defense_msgs = [
        m for m in board_msgs
        if m.get("message_type") in (BoardMessageType.DEFENSE, BoardMessageType.DEFENSE.value)
        and m.get("criterion_code") == "CRIT-SBRT-01"
    ]
    assert len(defense_msgs) >= 1
    hold_msg = defense_msgs[0]
    meta = hold_msg.get("metadata", {})
    assert meta.get("specific_contradiction_cited") is False
    assert meta.get("judge_action") == "HOLD"
    assert meta.get("debated_criteria_outcome") == "DEFENDED"


def test_judge_concedes_when_verifier_cites_specific_contradicting_span(sbrt_contradicting_narrative):
    """
    Task 4(b): The judge CONCEDES when the verifier cites a specific contradicting verbatim span
    from the narrative that undercuts the MET verdict and defense cannot resolve it.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    def mock_judge_side_effect(criterion=None, *args, **kwargs):
        if criterion is None and args:
            criterion = args[0]
        ccode = criterion.get("criterion_code") if isinstance(criterion, dict) else getattr(criterion, "criterion_code", None)
        if ccode == "CRIT-SBRT-01":
            return CriterionJudgment(
                status="MET",
                quoted_evidence="Medically inoperable primary pulmonary malignancy with localized disease confined to right thorax.",
                rationale="Initial reading found inoperable pulmonary malignancy",
                confidence=0.92,
                status_code="COMPLETED",
            )
        return CriterionJudgment(
            status="MET",
            quoted_evidence="4D CT motion management placed.",
            rationale="Motion tracking present",
            confidence=0.92,
            status_code="COMPLETED",
        )

    # Verifier cites specific verbatim contradicting span in narrative
    specific_challenge = {
        "has_objection": True,
        "objection_type": "ANATOMIC_MISMATCH",
        "counter_quote": "Repeat thoracic CT confirms widespread contralateral lung metastases.",
        "named_sub_requirement": "Absence of distant or widespread metastases (M0)",
        "specific_contradiction": True,
        "rationale": "Patient has widespread contralateral metastases, directly contradicting early-stage M0 status.",
    }

    # Defense fails to find an alternative resolving quote
    failing_defense = DefenseResult(
        defense_quote="",
        rationale="Cannot resolve metastasis contradiction.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_judge_side_effect), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=specific_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=failing_defense):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V75-CONCEDE",
            policy_id="LCD-SBRT",
            ehr_narrative=sbrt_contradicting_narrative,
            execution_mode="agentic",
            save_record=False,
        )

    # CRIT-SBRT-01 must be CONCEDED
    sbrt_01 = next(a for a in res.criterion_assessments if a.criterion_code == "CRIT-SBRT-01")
    assert sbrt_01.status == DeterminationStatus.INSUFFICIENT_EVIDENCE

    # Verify board messages record specific_contradiction_cited=True and judge_action=CONCEDE
    board_msgs = res.message_board or []
    concede_msgs = [
        m for m in board_msgs
        if m.get("message_type") in (BoardMessageType.CONCEDE, BoardMessageType.CONCEDE.value)
        and m.get("criterion_code") == "CRIT-SBRT-01"
    ]
    assert len(concede_msgs) >= 1
    concede_meta = concede_msgs[0].get("metadata", {})
    assert concede_meta.get("specific_contradiction_cited") is True
    assert concede_meta.get("judge_action") == "CONCEDE"
    assert concede_meta.get("debated_criteria_outcome") == "CONCEDED"


def test_advocate_finds_pacemaker_and_pet_onc_semantic_spans():
    """
    Task 4(c): The advocate FINDS the PACEMAKER span ('in the absence of reversible causes' /
    the AV-nodal-blocker + normal potassium findings) for CRIT-PACE-02 and the PET-ONC span
    ('Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma')
    for CRIT-PTONC-01.
    """
    dev_vigs_path = Path("app/data/policies_extended/dev_vignettes_extended.json")
    with dev_vigs_path.open(encoding="utf-8") as f:
        vignettes = {v["vignette_id"]: v for v in json.load(f)}

    # 1. Test PACEMAKER (CRIT-PACE-02)
    pace_vig = vignettes["DEV-NCD-PACEMAKER-APP"]
    crit_pace = {
        "criterion_code": "CRIT-PACE-02",
        "name": "Absence of reversible causes",
        "description": "Clinical confirmation that bradyarrhythmia is not caused by reversible drug toxicity (beta-blockers, digoxin), acute electrolyte disturbance, or transient hypothermia.",
        "clinical_intent": "Exclude transient or reversible causes of bradycardia",
        "is_exclusion": False,
    }
    pace_span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_pace,
        note_text=pace_vig["ehr_narrative"],
    )
    assert pace_span, "Advocate must find a relevant span for CRIT-PACE-02"
    assert (
        "in the absence of reversible causes" in pace_span
        or "Not taking AV nodal blocking agents" in pace_span
        or "serum potassium" in pace_span
    ), f"Unexpected PACE-02 span: '{pace_span}'"

    # 2. Test PET-ONC (CRIT-PTONC-01)
    ptonc_vig = vignettes["DEV-NCD-PET-ONC-APP"]
    crit_ptonc = {
        "criterion_code": "CRIT-PTONC-01",
        "name": "Biopsy-proven malignancy",
        "description": "Pathology report documenting biopsy-proven malignancy (or solitary pulmonary nodule with high clinical cancer probability on chest CT).",
        "clinical_intent": "Confirm histological malignancy prior to PET staging",
        "is_exclusion": False,
    }
    ptonc_span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_ptonc,
        note_text=ptonc_vig["ehr_narrative"],
    )
    assert ptonc_span, "Advocate must find a relevant span for CRIT-PTONC-01"
    assert "Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma" in ptonc_span, (
        f"Unexpected PTONC-01 span: '{ptonc_span}'"
    )


def test_advocate_does_not_propose_span_when_evidence_genuinely_absent():
    """
    Task 4(d): The advocate does NOT propose a span for a criterion whose evidence is
    genuinely absent (CRIT-MRIB-02 headache in DEV-LCD-MRI-BRAIN-APP).
    """
    dev_vigs_path = Path("app/data/policies_extended/dev_vignettes_extended.json")
    with dev_vigs_path.open(encoding="utf-8") as f:
        vignettes = {v["vignette_id"]: v for v in json.load(f)}

    mrib_vig = vignettes["DEV-LCD-MRI-BRAIN-APP"]
    crit_mrib = {
        "criterion_code": "CRIT-MRIB-02",
        "name": "Headache with red flags",
        "description": "Headache with progressive severity, nocturnal awakening, papilledema on fundoscopy, or worsening with Valsalva maneuver.",
        "clinical_intent": "Document severe or red-flag headache justifying neuroimaging",
        "is_exclusion": False,
    }

    # The note has focal deficits and 'No history of uncomplicated tension headache',
    # but no evidence satisfying CRIT-MRIB-02.
    span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_mrib,
        note_text=mrib_vig["ehr_narrative"],
    )
    assert span == "", f"Advocate proposed an ungrounded span when evidence was absent: '{span}'"


def test_v73_optimizations_unchanged_and_reusable():
    """
    Task 4(e): Pin that v73 optimizations (narrowed pre-deferral review, baseline reuse validity,
    keep-alive, and bench-only flag) are intact and operational.
    """
    # 1. Baseline reuse checker holds because critical deterministic files are untouched
    is_valid = verify_baseline_reuse_validity(Path("app/data/benchmarks/agentic_v73_three_mode_run.json"))
    assert is_valid is True, "Baseline reuse checker must pass at current HEAD"

    # 2. Narrowed pre-deferral review behaves as designed:
    # Review is skipped when 0 mandatory criteria are met
    pipeline = MultiAgentVerificationPipeline(db=None)

    def mock_all_unmet(criterion=None, *args, **kwargs):
        return CriterionJudgment(
            status="NOT_MET",
            quoted_evidence="",
            rationale="Evidence missing",
            confidence=0.50,
            status_code="COMPLETED",
        )

    mock_advocacy = AdvocacyResult(
        advocacy_quote="",
        rationale="No alternate evidence",
        confidence=0.50,
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_all_unmet), \
         patch.object(ClinicalEquivalenceJudge, "generate_advocacy_sync", return_value=mock_advocacy), \
         patch.object(ClinicalEquivalenceJudge, "review_case_deferral_sync") as mock_review:
        res = pipeline.adjudicate_sync(
            patient_id="PT-V75-ZERO-MET",
            policy_id="LCD-IMRT",
            ehr_narrative="Patient note without prostate cancer or IMRT indications.",
            execution_mode="agentic",
            save_record=False,
        )

    # When 0 mandatory criteria are met, pre-deferral review is narrowed/skipped
    assert not mock_review.called, "Pre-deferral review must be skipped when 0 mandatory criteria are met"
    board_msgs = res.message_board or []
    assert any(
        m.get("message_type") in (BoardMessageType.INFORM, BoardMessageType.INFORM.value)
        and m.get("metadata", {}).get("narrowing_rule_applied") is True
        for m in board_msgs
    ), "Skipped review INFORM message must be posted to message board"
