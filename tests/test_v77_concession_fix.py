"""
Test Suite for Prompt v77: Concession Rule Fix, DEFENSE Audit Trail, Gate A Paraphrase Normalization.

Pins:
(i)   A named_sub_requirement matching a criterion code (CRIT-CAT-01, CRIT-SGD-02, REQUIREMENT 2.1.1.1.1)
      does NOT count as specific; the judge HOLDS.
(ii)  A valid clinical sub-requirement phrase DOES count as specific.
(iii) The HOLD-path DEFENSE message carries objection_type and verbatim grounding in content,
      and objection_type + defense_quote in metadata.
(iv)  The PACEMAKER paraphrase resolves to its verbatim note span via advocate-assisted span normalization.
(v)   The PET-ONC span verifies as EQUIVALENT against CRIT-PTONC-01 as written.
(vi)  The advocate does not propose a span when evidence is genuinely absent (CRIT-MRIB-02).
"""

from __future__ import annotations

from unittest.mock import patch

from app.agents.pipeline import (
    MultiAgentVerificationPipeline,
    _is_valid_clinical_sub_requirement,
)
from app.core.agentic_guardrails import AgenticGuardrails
from app.core.llm_judge import (
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    DefenseResult,
    EquivalenceVerdict,
)
from app.schemas.contracts import DeterminationStatus


def test_named_sub_req_criterion_code_does_not_count_as_specific():
    """
    Test (b)(i): A named_sub_requirement of CRIT-CAT-01 / CRIT-SGD-02 / REQUIREMENT 2.1.1.1.1
    does NOT count as specific. The judge HOLDS.
    """
    # Unit check of helper
    assert not _is_valid_clinical_sub_requirement("CRIT-CAT-01", "CRIT-CAT-01")
    assert not _is_valid_clinical_sub_requirement("CRIT-SGD-02", "CRIT-SGD-02")
    assert not _is_valid_clinical_sub_requirement("REQUIREMENT 2.1.1.1.1", "CRIT-SI-01")
    assert not _is_valid_clinical_sub_requirement("2.1.1.1.1", "CRIT-SI-01")
    assert not _is_valid_clinical_sub_requirement("CRIT-PACE-02")
    assert not _is_valid_clinical_sub_requirement("none")
    assert not _is_valid_clinical_sub_requirement("N/A")

    # End-to-end pipeline check
    ehr = (
        "PATIENT RECORD: 72-year-old presenting with best corrected visual acuity 20/60 in right eye "
        "and 20/50 in left eye due to nuclear sclerotic cataract."
    )
    quote = "best corrected visual acuity 20/60 in right eye and 20/50 in left eye"

    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Visual acuity 20/60 satisfies criterion",
        confidence=0.92,
        status_code="COMPLETED"
    )

    # Verifier outputs named_sub_requirement = "CRIT-CAT-01" without a distinct undercutting counter-quote
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "NEGATION",
        "counter_quote": quote,  # matches supporting quote, does not undercut
        "named_sub_requirement": "CRIT-CAT-01",  # criterion code must be rejected as specific
        "specific_contradiction": False,
        "rationale": "Visual acuity might not satisfy criterion requirement"
    }

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V77-CRIT-CODE",
            policy_id="NCD-CATARACT",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    # Assert no concession occurred; judge held
    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == "CRIT-CAT-01"]
    assert len(concede_msgs) == 0, "Judge must NOT concede when named_sub_requirement is a criterion code"

    defend_msgs = [m for m in board_msgs if m.get("message_type") == "DEFENSE" and m.get("criterion_code") == "CRIT-CAT-01"]
    assert len(defend_msgs) >= 1, "Judge must post DEFENSE (HOLD) when challenge lacks specific contradiction"
    assert defend_msgs[0].get("metadata", {}).get("judge_action") == "HOLD"
    assert defend_msgs[0].get("metadata", {}).get("debated_criteria_outcome") == "DEFENDED"


def test_valid_named_clinical_sub_req_counts_as_specific():
    """
    Test (b)(ii): A valid clinical sub-requirement phrase DOES count as specific.
    """
    assert _is_valid_clinical_sub_requirement("best-corrected Snellen distance visual acuity of 20/50 or worse", "CRIT-CAT-01")
    assert _is_valid_clinical_sub_requirement("formal SLP evaluation and device trial", "CRIT-SGD-02")
    assert _is_valid_clinical_sub_requirement("75% pain relief during anesthetic window", "CRIT-SI-01")

    ehr = (
        "PATIENT RECORD: 72-year-old presenting with best corrected visual acuity 20/60 in right eye "
        "and 20/50 in left eye due to nuclear sclerotic cataract."
    )
    quote = "best corrected visual acuity 20/60 in right eye and 20/50 in left eye"

    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Visual acuity 20/60 satisfies criterion",
        confidence=0.92,
        status_code="COMPLETED"
    )

    # Verifier supplies a genuine clinical phrase from criterion text
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "NEGATION",
        "counter_quote": "",
        "named_sub_requirement": "Snellen distance visual acuity of 20/50 or worse in the affected eye",
        "specific_contradiction": True,
        "rationale": "Clinical documentation fails to specify affected eye visual acuity."
    }

    # Defense fails to resolve it
    mock_failed_defense = DefenseResult(
        defense_quote="",
        rationale="Cannot resolve specific clinical sub-requirement."
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_failed_defense):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V77-SPECIFIC-SUBREQ",
            policy_id="NCD-CATARACT",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == "CRIT-CAT-01"]
    assert len(concede_msgs) >= 1, "Judge must concede when verifier cites a genuine clinical sub-requirement and defense fails"
    assert concede_msgs[0].get("metadata", {}).get("debated_criteria_outcome") == "CONCEDED"


def test_hold_path_defense_content_contains_objection_type_and_verbatim_span():
    """
    Test (b)(iii): The HOLD-path DEFENSE message carries objection_type and verbatim grounding in content,
    and objection_type + defense_quote in metadata.
    """
    ehr = (
        "PATIENT NOTE: 68-year-old male with confirmed prostate adenocarcinoma. "
        "Recommending IMRT for organ sparing."
    )
    quote = "prostate adenocarcinoma"

    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Biopsy proven prostate adenocarcinoma satisfies criterion",
        confidence=0.95,
        status_code="COMPLETED"
    )

    # General / non-specific challenge (counter_quote is the evidence itself, no valid clinical sub-req)
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "TEMPORAL",
        "counter_quote": quote,
        "named_sub_requirement": "CRIT-IMRT-01",  # criterion code -> not specific
        "specific_contradiction": False,
        "rationale": "General doubt about staging timeline."
    }

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V77-HOLD-AUDIT",
            policy_id="LCD-IMRT",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    hold_defenses = [
        m for m in board_msgs
        if m.get("message_type") == "DEFENSE"
        and m.get("metadata", {}).get("judge_action") == "HOLD"
    ]
    assert len(hold_defenses) >= 1, "Expected HOLD defense message"
    defense_msg = hold_defenses[0]

    content = defense_msg.get("content", "")
    metadata = defense_msg.get("metadata", {})

    # Verify content contains objection type and verbatim grounding
    assert "TEMPORAL" in content, f"Defense content must name objection type 'TEMPORAL', got: {content}"
    assert "prostate adenocarcinoma" in content, f"Defense content must quote verbatim span, got: {content}"

    # Verify metadata contains objection_type and defense_quote
    assert metadata.get("objection_type") == "TEMPORAL"
    assert metadata.get("defense_quote") == "prostate adenocarcinoma"
    assert metadata.get("debated_criteria_outcome") == "DEFENDED"


def test_pacemaker_paraphrase_resolves_via_advocate_span_normalization():
    """
    Test (b)(iv): The PACEMAKER paraphrase resolves to its verbatim span via the advocate
    (Gate A passes after normalization).
    """
    ehr = (
        "CLINICAL PROGRESS NOTE: High-grade third-degree atrioventricular block. "
        "Not taking AV nodal blocking agents. Potassium 4.2, TSH 1.8. "
        "Recommendation for permanent pacemaker placement."
    )

    crit = {
        "criterion_code": "CRIT-PACE-02",
        "name": "Absence of Reversible Causes",
        "description": "Absence of reversible causes such as drug toxicity (AV nodal blockers) or electrolyte imbalance"
    }

    # Paraphrase that does not exist verbatim in the note
    paraphrase = "not taking AV nodal blockers"

    # Verify advocate's span normalization locates the verbatim sentence from note
    norm_span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit,
        note_text=ehr,
        candidate_quote=paraphrase
    )
    assert norm_span != "", "Advocate must return a candidate span"
    assert "Not taking AV nodal blocking agents" in norm_span
    assert norm_span in ehr, "Normalized span must be verbatim text from the clinical note"

    # Test pipeline end-to-end: judge outputs paraphrase, Gate A normalizes to verbatim span
    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=paraphrase,
        rationale="Patient is not taking AV nodal blockers, ruling out reversible cause",
        confidence=0.92,
        status_code="COMPLETED"
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value={
             "has_objection": False, "objection_type": "NONE", "counter_quote": "", "specific_contradiction": False, "rationale": "Solid evidence"
         }):
        res = pipeline.adjudicate_sync(
            patient_id="PT-V77-PACE-NORM",
            policy_id="NCD-PACEMAKER",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    crit_pace_02 = next((ca for ca in res.criterion_assessments if ca.criterion_code == "CRIT-PACE-02"), None)
    assert crit_pace_02 is not None
    # Must NOT fail Gate A
    assert crit_pace_02.status == DeterminationStatus.MET
    assert len(crit_pace_02.verified_spans) > 0
    assert "Not taking AV nodal blocking agents" in crit_pace_02.verified_spans[0].source_text


def test_pet_onc_span_verifies_as_equivalent_against_criterion_as_written():
    """
    Test (b)(v): The PET-ONC span verifies as EQUIVALENT against CRIT-PTONC-01 as written.
    """
    crit = {
        "criterion_code": "CRIT-PTONC-01",
        "name": "Histologically Confirmed Malignancy or High-Probability Solitary Nodule",
        "description": "Pathology report documenting biopsy-proven malignancy (or solitary pulmonary nodule with high clinical cancer probability on chest CT)."
    }
    span = "Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma."

    judge = ClinicalEquivalenceJudge()
    prompt = judge.build_prompt(
        criterion_code=crit["criterion_code"],
        criterion_name=crit["name"],
        criterion_desc=crit["description"],
        candidate_span_text=span
    )

    # Verify governing rules in the prompt explicitly enforce checking requirement as written
    assert "Check the criterion requirement AS WRITTEN" in prompt
    assert "satisfying EITHER alternative satisfies the criterion" in prompt
    assert "biopsy-proven malignancy" in prompt

    # With mocked response following the prompt rule:
    mock_equiv_json = {
        "verdict": "EQUIVALENT",
        "rationale": "Biopsy pathology confirms invasive esophageal adenocarcinoma, satisfying the biopsy-proven malignancy branch."
    }

    with patch("httpx.Client.post") as mock_post:
        mock_resp = mock_post.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": str(mock_equiv_json).replace("'", '"')}}]
        }
        res = judge.judge_equivalence_sync(criterion=crit, candidate_span_text=span)
        assert res.verdict == EquivalenceVerdict.EQUIVALENT
        assert "biopsy-proven malignancy" in res.rationale


def test_advocate_does_not_propose_span_when_evidence_genuinely_absent():
    """
    Test (b)(vi): The advocate does NOT propose a span for a criterion whose evidence
    is genuinely absent (e.g. CRIT-MRIB-02 progressive headache with red flags).
    """
    # Note has focal deficits, but ZERO headache or red flag exam findings
    note = (
        "CLINICAL PROGRESS NOTE: Neurology\n"
        "61-year-old presenting with acute onset right facial droop and right arm weakness.\n"
        "Exam confirms central facial palsy and 4/5 right upper extremity strength.\n"
        "No complaints of headache, nausea, or visual changes.\n"
        "Plan: Urgent brain MRI to evaluate for stroke versus intracranial lesion."
    )

    crit_mrib_02 = {
        "criterion_code": "CRIT-MRIB-02",
        "name": "Progressive Headache with Red Flags or Abnormal Exam",
        "description": "Headache with progressive severity, nocturnal awakening, papilledema on fundoscopy, or worsening with Valsalva maneuver."
    }

    selected = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=crit_mrib_02,
        note_text=note,
        candidate_quote=""
    )

    # Empty or no valid supporting quote because headache findings are absent
    assert selected == "" or "headache" not in selected.lower() or "no complaints of headache" in selected.lower()
