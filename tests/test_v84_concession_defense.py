"""
Test Suite for Prompt v84: Concession Defense and Objection-Validity Verification.

Validates that:
(i)   An objection citing a requirement NOT in the criterion text is invalidated
      (defense returns objection_valid=False with reason quoting criterion text).
(ii)  An objection with a backwards numeric comparison is invalidated
      (defense returns objection_valid=False due to arithmetic/direction failure).
(iii) A VALID objection still concedes: when an objection cites a requirement actually
      present in the criterion text with a grounded counter-span and defense cannot
      resolve it, the judge still concedes (concession rule not weakened).
(iv)  The two target cases rescue in the pipeline: DEV-LCD-KYPHO-APP and
      DEV-NCD-CATARACT-APP adjudicate to APPROVED through the objection-validity mechanism.
(v)   Existing concession behavior is preserved for valid contradictions.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from contextlib import ExitStack
from unittest.mock import patch

from app.agents.pipeline import (
    MultiAgentVerificationPipeline,
)
from app.core.agentic_guardrails import AgenticGuardrails
from app.core.llm_judge import (
    ClinicalEquivalenceJudge,
    CriterionJudgment,
    DefenseResult,
    JudgeEvaluation,
)
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus


def _is_ollama_available() -> bool:
    """Check if local Ollama daemon is reachable (returns False in CI environment)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


class MockPolicy:
    policy_id = "SYNTH-POLICY"
    title = "Synthetic Policy"
    description = "Synthetic Policy Description"
    category = "Synthetic"
    effective_date = "2026-01-01"
    jurisdiction = "National"

    def __init__(self, criteria):
        self.criteria = criteria


def test_v84_synthetic_absent_requirement_invalidated():
    """
    Condition (i): An objection citing a requirement NOT in the criterion text
    is invalidated (objection_valid=False quoting the criterion text),
    allowing the original MET verdict to stand without concession.
    """
    ehr = (
        "CLINICAL NOTE: 74-year-old female with acute severe thoracic back pain following a fall. "
        "Thoracic spine imaging reveals acute fracture edema confirming recent vertebral compression fracture."
    )
    quote = "acute fracture edema confirming recent vertebral compression fracture"

    pipeline = MultiAgentVerificationPipeline(db=None)

    crit_code = "CRIT-SYNTH-EDEMA-01"
    crit_desc = "MRI or nuclear imaging demonstrating acute bone marrow edema confirming recent compression fracture."
    crit_dict = {
        "criterion_code": crit_code,
        "name": "Acute Edema on Imaging",
        "description": crit_desc,
        "clinical_intent": crit_desc,
        "is_exclusion": False,
        "mandatory": True,
    }

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Imaging confirms acute fracture edema satisfying criterion",
        confidence=0.95,
        status_code="COMPLETED",
    )

    # Verifier challenges with a 4-week conservative therapy requirement NOT present in the criterion
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "TEMPORAL",
        "counter_quote": "acute severe thoracic back pain following a fall",
        "named_sub_requirement": "4 weeks conservative therapy",
        "specific_contradiction": True,
        "rationale": "Conservative therapy lasted only 10 days, less than the required 4 weeks.",
    }

    # Defense recognizes the requirement is absent from the criterion text
    mock_defense = DefenseResult(
        objection_valid=False,
        objection_invalid_reason=(
            f"The objection demands 4 weeks of conservative therapy, but the criterion description "
            f"'{crit_desc}' contains no conservative therapy duration requirement."
        ),
        defense_quote="",
        rationale="Objection premise is absent from the criterion text as written; original evidence stands.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_defense), \
         patch.object(pipeline.retrieval_agent, "get_structured_criteria", return_value=[crit_dict]), \
         patch.object(pipeline.retrieval_agent, "retrieve_policy", return_value=MockPolicy([crit_dict])):

        res = pipeline.adjudicate_sync(
            patient_id="PT-V84-ABSENT-REQ",
            policy_id="POLICY-SYNTH-KYPHO",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []

    # 1. No concession message posted for this criterion
    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == crit_code]
    assert len(concede_msgs) == 0, f"Judge must NOT concede on an invalidated objection, found: {concede_msgs}"

    # 2. Defense message posted with objection_valid=False and invalidation reason in metadata
    defense_msgs = [m for m in board_msgs if m.get("message_type") == "DEFENSE" and m.get("criterion_code") == crit_code]
    assert len(defense_msgs) >= 1, "Expected DEFENSE message on board"
    def_meta = defense_msgs[0].get("metadata", {})
    assert def_meta.get("objection_valid") is False
    assert "conservative therapy" in def_meta.get("objection_invalid_reason", "")
    assert def_meta.get("debated_criteria_outcome") == "DEFENDED"
    assert def_meta.get("judge_action") == "HOLD"

    # 3. Guard concession arm did not block
    guard_blocked_msgs = [m for m in board_msgs if m.get("metadata", {}).get("guard_blocked") is True]
    assert len(guard_blocked_msgs) == 0, f"Guard must not block on invalidated objection, found: {guard_blocked_msgs}"


def test_v84_synthetic_backwards_numeric_comparison_invalidated():
    """
    Condition (ii): An objection with a backwards numeric comparison (e.g., Snellen acuity
    where larger denominator is worse vision) is invalidated.
    """
    ehr = (
        "CLINICAL NOTE: 69-year-old presenting with cataract. Best corrected visual acuity "
        "is 20/60 in the right eye and 20/40 in the left eye."
    )
    quote = "Best corrected visual acuity is 20/60 in the right eye and 20/40 in the left eye"

    pipeline = MultiAgentVerificationPipeline(db=None)

    crit_code = "CRIT-SYNTH-ACUITY-01"
    crit_desc = "Documented best-corrected Snellen distance visual acuity of 20/50 or worse in affected eye."
    crit_dict = {
        "criterion_code": crit_code,
        "name": "Visual Acuity 20/50 or Worse",
        "description": crit_desc,
        "clinical_intent": crit_desc,
        "is_exclusion": False,
        "mandatory": True,
    }

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="20/60 in right eye meets 20/50 or worse requirement",
        confidence=0.94,
        status_code="COMPLETED",
    )

    # Verifier challenges with backwards comparison
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "NEGATION",
        "counter_quote": quote,
        "named_sub_requirement": "20/50 or worse in affected eye",
        "specific_contradiction": True,
        "rationale": "Visual acuity of 20/60 does not meet the requirement of 20/50 or worse.",
    }

    # Defense recognizes 20/60 is worse than 20/50
    mock_defense = DefenseResult(
        objection_valid=False,
        objection_invalid_reason=(
            f"The objection claims 20/60 does not meet '20/50 or worse', but Snellen visual acuity "
            f"with a larger denominator (20/60) represents worse visual acuity than 20/50. The criterion "
            f"'{crit_desc}' is satisfied."
        ),
        defense_quote="",
        rationale="Numeric comparison in objection is inverted; 20/60 satisfies 20/50 or worse.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_defense), \
         patch.object(pipeline.retrieval_agent, "get_structured_criteria", return_value=[crit_dict]), \
         patch.object(pipeline.retrieval_agent, "retrieve_policy", return_value=MockPolicy([crit_dict])):

        res = pipeline.adjudicate_sync(
            patient_id="PT-V84-SNELLEN-NUMERIC",
            policy_id="POLICY-SYNTH-CATARACT",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []

    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == crit_code]
    assert len(concede_msgs) == 0, f"Judge must NOT concede on backwards numeric objection, found: {concede_msgs}"

    defense_msgs = [m for m in board_msgs if m.get("message_type") == "DEFENSE" and m.get("criterion_code") == crit_code]
    assert len(defense_msgs) >= 1
    def_meta = defense_msgs[0].get("metadata", {})
    assert def_meta.get("objection_valid") is False
    assert "20/60" in def_meta.get("objection_invalid_reason", "")
    assert def_meta.get("debated_criteria_outcome") == "DEFENDED"


def test_v84_valid_objection_still_concedes():
    """
    Condition (iii): A VALID objection (cites requirement actually present in criterion text,
    with grounded counter-span, correct comparison) where defense cannot resolve it
    MUST STILL lead to CONCEDED.
    This proves the concession rule is NOT weakened or disabled.
    """
    ehr = (
        "CLINICAL NOTE: Patient with chronic back pain completed 2 weeks of physical therapy "
        "and NSAIDs without substantial improvement."
    )
    quote = "completed 2 weeks of physical therapy and NSAIDs without substantial improvement"

    pipeline = MultiAgentVerificationPipeline(db=None)

    crit_code = "CRIT-SYNTH-CONSERVATIVE-01"
    crit_desc = "Documented failure of at least 6 weeks of non-surgical conservative therapy including physical therapy."
    crit_dict = {
        "criterion_code": crit_code,
        "name": "6 Weeks Conservative Therapy",
        "description": crit_desc,
        "clinical_intent": crit_desc,
        "is_exclusion": False,
        "mandatory": True,
    }

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Patient attempted conservative therapy",
        confidence=0.88,
        status_code="COMPLETED",
    )

    # Valid objection: requirement specifies 6 weeks, note explicitly says only 2 weeks
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "TEMPORAL",
        "counter_quote": "completed 2 weeks of physical therapy",
        "named_sub_requirement": "at least 6 weeks of non-surgical conservative therapy",
        "specific_contradiction": True,
        "rationale": "Conservative therapy lasted only 2 weeks, which does not meet the 6-week requirement.",
    }

    # Defense confirms objection IS valid and cannot locate resolving quote elsewhere in note
    mock_failed_defense = DefenseResult(
        objection_valid=True,
        objection_invalid_reason="",
        defense_quote="",
        rationale="Objection is valid: clinical note confirms conservative therapy was only 2 weeks, not 6 weeks.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_failed_defense), \
         patch.object(pipeline.retrieval_agent, "get_structured_criteria", return_value=[crit_dict]), \
         patch.object(pipeline.retrieval_agent, "retrieve_policy", return_value=MockPolicy([crit_dict])):

        res = pipeline.adjudicate_sync(
            patient_id="PT-V84-VALID-CONCEDE",
            policy_id="POLICY-SYNTH-CONSERVATIVE",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []

    # Concession MUST occur
    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == crit_code]
    assert len(concede_msgs) >= 1, "Valid objection with failed defense MUST yield CONCEDE"
    assert concede_msgs[0].get("metadata", {}).get("debated_criteria_outcome") == "CONCEDED"

    # Status must be INSUFFICIENT_EVIDENCE
    matching = [a for a in res.criterion_assessments if a.criterion_code == crit_code]
    assert len(matching) == 1
    assessment = matching[0]
    assert assessment.status == DeterminationStatus.INSUFFICIENT_EVIDENCE


def test_v84_target_cases_rescue_kypho_and_cataract():
    """
    Condition (iv): DEV-LCD-KYPHO-APP and DEV-NCD-CATARACT-APP rescue in the pipeline
    and adjudicate to APPROVED, with transcript metadata recording the objection validity finding.
    Runs against live Ollama when available, or mocked LLM responses in CI/offline environments.
    """
    from app.core import concept_map as cm_mod
    from scripts.run_agentic_v59_three_mode_measurement import (
        build_merged_in_memory_map,
    )

    merged_map, _, _ = build_merged_in_memory_map()
    cm_mod._GLOBAL_CONCEPT_MAP = merged_map

    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    vignettes_by_id = {v["vignette_id"]: v for v in vignettes}

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.span_repair_enabled = True

    stack = ExitStack()
    if not _is_ollama_available():
        def mock_judge(*args, **kwargs):
            criterion = kwargs.get("criterion") if "criterion" in kwargs else (args[0] if len(args) > 0 and isinstance(args[0], dict) else args[1])
            ccode = criterion.get("criterion_code", "")
            if ccode == "CRIT-KYPHO-01":
                return CriterionJudgment(status="MET", quoted_evidence="Pain rating is 8/10 on visual analog scale.", rationale="Severe pain 8/10", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-KYPHO-02":
                return CriterionJudgment(status="MET", quoted_evidence="STIR imaging demonstrating acute osteoporotic vcf with bone edema", rationale="Acute edema confirmed", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-KYPHO-EXCL-01":
                return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="No infection", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-CAT-01":
                return CriterionJudgment(status="MET", quoted_evidence="Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye.", rationale="20/60 meets 20/50 or worse", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-CAT-02":
                return CriterionJudgment(status="MET", quoted_evidence="difficulty with daily activities", rationale="ADL impairment", confidence=0.95, status_code="COMPLETED")
            elif ccode == "CRIT-CAT-EXCL-01":
                return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="Refractory to spectacles", confidence=0.95, status_code="COMPLETED")
            return CriterionJudgment(status="UNMET", quoted_evidence="", rationale="Default", confidence=0.5, status_code="COMPLETED")

        def mock_challenge(*args, **kwargs):
            criterion = kwargs.get("criterion") or args[1]
            ccode = criterion.get("criterion_code", "")
            if ccode == "CRIT-KYPHO-02":
                return {
                    "adversarial_counter_reading": True,
                    "has_objection": True,
                    "objection_type": "TEMPORAL",
                    "counter_quote": "Patient has tried scheduled oral analgesics, bed rest, and calcitonin for 2 weeks",
                    "named_sub_requirement": "4 weeks conservative therapy",
                    "specific_contradiction": True,
                    "rationale": "Conservative therapy lasted only 2 weeks, less than 4 weeks required.",
                }
            elif ccode == "CRIT-CAT-01":
                return {
                    "adversarial_counter_reading": True,
                    "has_objection": True,
                    "objection_type": "NEGATION",
                    "counter_quote": "Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye.",
                    "named_sub_requirement": "20/50 or worse in affected eye",
                    "specific_contradiction": True,
                    "rationale": "20/60 does not meet 20/50 or worse.",
                }
            return {"adversarial_counter_reading": False, "has_objection": False, "rationale": "No objection"}

        def mock_defense(*args, **kwargs):
            criterion = kwargs.get("criterion") or args[1]
            ccode = criterion.get("criterion_code", "")
            if ccode == "CRIT-KYPHO-02":
                return DefenseResult(
                    objection_valid=False,
                    objection_invalid_reason="The objection demands 4 weeks of conservative therapy, but CRIT-KYPHO-02 contains no conservative therapy duration requirement.",
                    defense_quote="",
                    rationale="Objection absent from criterion text",
                    status_code="COMPLETED",
                )
            elif ccode == "CRIT-CAT-01":
                return DefenseResult(
                    objection_valid=False,
                    objection_invalid_reason="The objection claims 20/60 does not meet 20/50 or worse, but 20/60 is worse than 20/50 in Snellen acuity.",
                    defense_quote="",
                    rationale="Numeric comparison inverted",
                    status_code="COMPLETED",
                )
            return DefenseResult(objection_valid=True, defense_quote="", rationale="Default", status_code="COMPLETED")

        def mock_equiv(*args, **kwargs):
            return JudgeEvaluation(verdict="EQUIVALENT", rationale="Equivalent clinical concept", elapsed_ms=10.0, status_code="COMPLETED")

        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", side_effect=mock_judge))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", side_effect=mock_challenge))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", side_effect=mock_defense))
        stack.enter_context(patch.object(ClinicalEquivalenceJudge, "judge_equivalence_sync", side_effect=mock_equiv))

    with stack:
        # 1. DEV-LCD-KYPHO-APP
        kypho_vignette = vignettes_by_id["DEV-LCD-KYPHO-APP"]
        res_kypho = pipeline.adjudicate_sync(
            patient_id=kypho_vignette.get("patient_id", "DEV-LCD-KYPHO-APP"),
            policy_id=kypho_vignette["policy_id"],
            ehr_narrative=kypho_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )
        assert res_kypho.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"DEV-LCD-KYPHO-APP must adjudicate to APPROVED, got: {res_kypho.adjudication_decision} ({res_kypho.abstention_reason})"
        )

        # Verify transcript contains defense message invalidating the 4-week objection
        kypho_board = res_kypho.message_board or []
        kypho_defenses = [
            m for m in kypho_board
            if m.get("message_type") == "DEFENSE" and m.get("criterion_code") == "CRIT-KYPHO-02"
        ]
        assert len(kypho_defenses) >= 1, "CRIT-KYPHO-02 must have a DEFENSE message"
        assert kypho_defenses[0].get("metadata", {}).get("objection_valid") is False, (
            f"CRIT-KYPHO-02 objection must be invalidated, got meta: {kypho_defenses[0].get('metadata')}"
        )

        # 2. DEV-NCD-CATARACT-APP
        cat_vignette = vignettes_by_id["DEV-NCD-CATARACT-APP"]
        res_cat = pipeline.adjudicate_sync(
            patient_id=cat_vignette.get("patient_id", "DEV-NCD-CATARACT-APP"),
            policy_id=cat_vignette["policy_id"],
            ehr_narrative=cat_vignette["ehr_narrative"],
            execution_mode="agentic",
            save_record=False,
        )
        assert res_cat.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"DEV-NCD-CATARACT-APP must adjudicate to APPROVED, got: {res_cat.adjudication_decision} ({res_cat.abstention_reason})"
        )

        # Verify transcript contains defense message invalidating the Snellen objection
        cat_board = res_cat.message_board or []
        cat_defenses = [
            m for m in cat_board
            if m.get("message_type") == "DEFENSE" and m.get("criterion_code") == "CRIT-CAT-01"
        ]
        assert len(cat_defenses) >= 1, "CRIT-CAT-01 must have a DEFENSE message"
        assert cat_defenses[0].get("metadata", {}).get("objection_valid") is False, (
            f"CRIT-CAT-01 objection must be invalidated, got meta: {cat_defenses[0].get('metadata')}"
        )


def test_v84_existing_concession_behavior_preserved():
    """
    Condition (v): Verify existing concession behavior is preserved when a specific
    clinical sub-requirement is unmet and defense fails to provide resolving evidence.
    """
    ehr = (
        "PATIENT RECORD: 72-year-old presenting with best corrected visual acuity 20/40 in right eye "
        "and 20/40 in left eye due to nuclear sclerotic cataract."
    )
    quote = "best corrected visual acuity 20/40 in right eye and 20/40 in left eye"

    pipeline = MultiAgentVerificationPipeline(db=None)

    mock_judgment = CriterionJudgment(
        status="MET",
        quoted_evidence=quote,
        rationale="Visual acuity 20/40 assessed as meeting requirement",
        confidence=0.85,
        status_code="COMPLETED",
    )

    # Valid challenge citing genuine clinical sub-requirement that is genuinely unmet
    mock_challenge = {
        "adversarial_counter_reading": True,
        "has_objection": True,
        "objection_type": "NEGATION",
        "counter_quote": "",
        "named_sub_requirement": "Snellen distance visual acuity of 20/50 or worse in the affected eye",
        "specific_contradiction": True,
        "rationale": "Visual acuity of 20/40 is better than 20/50, failing the 20/50 or worse requirement.",
    }

    mock_failed_defense = DefenseResult(
        objection_valid=True,
        objection_invalid_reason="",
        defense_quote="",
        rationale="Objection is valid: visual acuity is 20/40 which is better than 20/50.",
        status_code="COMPLETED",
    )

    with patch.object(ClinicalEquivalenceJudge, "judge_criterion_sync", return_value=mock_judgment), \
         patch.object(AgenticGuardrails, "evaluate_gate_chain", return_value={"passed": True, "failing_gate": None, "reason": "Verified"}), \
         patch.object(ClinicalEquivalenceJudge, "generate_adversarial_counter_reading_sync", return_value=mock_challenge), \
         patch.object(ClinicalEquivalenceJudge, "generate_defense_sync", return_value=mock_failed_defense):

        res = pipeline.adjudicate_sync(
            patient_id="PT-V84-PRESERVED-CONCESSION",
            policy_id="NCD-CATARACT",
            ehr_narrative=ehr,
            execution_mode="agentic",
            save_record=False,
        )

    board_msgs = res.message_board or []
    concede_msgs = [m for m in board_msgs if m.get("message_type") == "CONCEDE" and m.get("criterion_code") == "CRIT-CAT-01"]
    assert len(concede_msgs) >= 1, "Concession must still occur when objection is valid and unrefuted"
    assert concede_msgs[0].get("metadata", {}).get("debated_criteria_outcome") == "CONCEDED"
