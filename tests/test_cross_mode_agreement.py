"""
Cross-Mode Agreement Unit Tests.
Proves that Deterministic, State Machine, and Declarative execution modes
agree on the exact same inputs for negation boundary, numeric cutoff,
and temporal duration, powered by the shared clinical core (app/core/clinical_core.py).
"""

from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.llm_extractor import ExtractorTools
from app.core.clinical_core import (
    ClinicalCoreEvaluator,
    ClinicalGroundingVerifier,
    ClinicalNumericParser,
    ClinicalScopeAnalyzer,
    ClinicalSectionDetector,
    ClinicalTemporalParser,
)
from app.schemas.contracts import DeterminationStatus
from app.schemas.declarative_policy import CriterionType, DeclarativeCriterion
from app.services.declarative_engine import DeclarativePolicyEngine


def test_negation_boundary_scope_agreement():
    """
    Test that all modes and analyzers agree that:
    1. Preceding negation inside sentence negates target.
    2. Sentence boundary (. or newline) terminates negation scope.
    3. Conjunction ('but', 'however') resets negation scope.
    """
    analyzer = CriteriaEvaluationAgent()

    # Case 1: Active negation
    text_neg = "Patient denies chest pain. Denies dyspnea."
    # span for 'dyspnea'
    start_d = text_neg.find("dyspnea")
    end_d = start_d + len("dyspnea")
    res_core = ClinicalScopeAnalyzer.analyze_scope(text_neg, start_d, end_d)
    res_agent = analyzer.analyze_clinical_scope(text_neg, start_d, end_d)

    assert res_core["is_negated"] is True
    assert res_agent["is_negated"] is True
    assert res_core["negation_trigger"] == res_agent["negation_trigger"]

    # Case 2: Sentence boundary terminates negation
    text_boundary = "Patient denies chest pain. Heart failure with reduced ejection fraction present."
    start_hf = text_boundary.find("Heart failure")
    end_hf = start_hf + len("Heart failure")
    res_core_b = ClinicalScopeAnalyzer.analyze_scope(text_boundary, start_hf, end_hf)
    res_agent_b = analyzer.analyze_clinical_scope(text_boundary, start_hf, end_hf)

    assert res_core_b["is_negated"] is False
    assert res_agent_b["is_negated"] is False

    # Case 3: Conjunction resets negation
    text_conj = "Denies severe angina, but reports severe dyspnea on exertion."
    start_disp = text_conj.find("severe dyspnea")
    end_disp = start_disp + len("severe dyspnea")
    res_core_c = ClinicalScopeAnalyzer.analyze_scope(text_conj, start_disp, end_disp)
    res_agent_c = analyzer.analyze_clinical_scope(text_conj, start_disp, end_disp)

    assert res_core_c["is_negated"] is False
    assert res_agent_c["is_negated"] is False


def test_numeric_cutoff_cross_mode_agreement():
    """
    Test that ExtractorTools (state_machine), DeclarativeCriterion evaluation,
    and ClinicalNumericParser agree on boundary and cutoff comparisons.
    """
    # Test boundary conditions
    test_cases = [
        (35.0, "<=", 35.0, True),
        (35.1, "<=", 35.0, False),
        (34.9, "<=", 35.0, True),
        (15.0, ">=", 15.0, True),
        (14.9, ">=", 15.0, False),
        (1.0, "<=", 1.0, True),
        (1.01, "<=", 1.0, False),
    ]

    for val, op, thresh, expected in test_cases:
        # 1. Core
        assert ClinicalNumericParser.evaluate_cutoff(val, op, thresh) == expected
        # 2. ExtractorTools (state_machine mode)
        assert ExtractorTools.evaluate_numeric_cutoff(val, op, thresh) == expected

    # Test date-as-measurement exclusion
    date_text = "Echo performed on 04/30/2026 revealed LVEF 28%."
    start_30 = date_text.find("30")
    end_30 = start_30 + 2
    assert ClinicalNumericParser.is_date_pattern(date_text, start_30, end_30) is True

    start_28 = date_text.find("28")
    end_28 = start_28 + 2
    assert ClinicalNumericParser.is_date_pattern(date_text, start_28, end_28) is False


def test_temporal_duration_and_calendar_delta_agreement():
    """
    Test that ExtractorTools and ClinicalTemporalParser agree on calendar deltas and unit conversions.
    """
    d1 = "2026-01-01"
    d2 = "2026-04-11"
    delta_core = ClinicalTemporalParser.calculate_calendar_delta(d1, d2)
    delta_tools = ExtractorTools.calculate_temporal_delta(d1, d2)

    assert delta_core == 100
    assert delta_tools == 100
    assert delta_core == delta_tools

    # Test duration conversion to days
    assert ClinicalTemporalParser.parse_duration_to_days(3, "months") == 90
    assert ClinicalTemporalParser.parse_duration_to_days(12, "weeks") == 84
    assert ClinicalTemporalParser.parse_duration_to_days(1, "year") == 365
    assert ClinicalTemporalParser.parse_duration_to_days(30, "days") == 30


def test_criterion_evaluation_cross_mode_concordance():
    """
    Test that evaluating criteria via ClinicalCoreEvaluator, CriteriaEvaluationAgent (deterministic),
    and DeclarativePolicyEngine (declarative) yields concordant determination statuses.
    """
    # LVEF qualification case
    ehr_qualifying = (
        "History of Present Illness: 68-year-old male with ischemic cardiomyopathy. "
        "Diagnostic Studies: Transthoracic echocardiogram confirms LVEF 28% with severe apical hypokinesis. "
        "Assessment & Plan: Patient remains in NYHA Class III heart failure despite guideline-directed medical therapy for 6 months."
    )

    crit_lvef = {
        "criterion_code": "CRIT-ICD-01",
        "name": "Left Ventricular Ejection Fraction <= 35%",
        "description": "LVEF <= 35% documented on echocardiogram or cardiac imaging",
        "operator": "<=",
        "threshold": 35.0,
        "target_unit": "%",
        "is_exclusion": False,
        "entity_names": ["LVEF", "ejection fraction"]
    }

    # 1. Core
    core_assessment = ClinicalCoreEvaluator.evaluate(crit_lvef, ehr_qualifying)
    assert core_assessment.status == DeterminationStatus.MET

    # 2. Deterministic CriteriaEvaluator
    agent = CriteriaEvaluationAgent()
    agent_assessment = agent.evaluate_criterion(crit_lvef, ehr_qualifying)
    assert agent_assessment.status == DeterminationStatus.MET

    # 3. Declarative Engine
    decl_crit = DeclarativeCriterion(
        criterion_code="CRIT-ICD-01",
        name="Left Ventricular Ejection Fraction <= 35%",
        description="LVEF <= 35% documented on echocardiogram or cardiac imaging",
        clinical_intent="Ensure severe systolic dysfunction",
        criterion_type=CriterionType.NUMERIC_THRESHOLD,
        entity_names=["LVEF", "ejection fraction"],
        operator="<=",
        threshold=35.0,
        target_unit="%"
    )
    decl_assessment = DeclarativePolicyEngine.evaluate(decl_crit, ehr_qualifying)
    assert decl_assessment.status == DeterminationStatus.MET


def test_grounding_verifier_agreement():
    """
    Test exact slice grounding verification across core and tools.
    """
    note = "Patient has severe ischemic cardiomyopathy with LVEF 25%."
    quote = "LVEF 25%"
    start = note.find(quote)
    end = start + len(quote)

    assert ClinicalGroundingVerifier.verify_exact_slice(note, quote, start, end) is True
    assert ExtractorTools.verify_exact_character_slice(note, quote, start, end) is True

    # Tampered offset
    assert ClinicalGroundingVerifier.verify_exact_slice(note, quote, start + 1, end) is False
    assert ExtractorTools.verify_exact_character_slice(note, quote, start + 1, end) is False



def test_declarative_negation_scope_integration_cross_mode():
    """
    Test that DeclarativePolicyEngine, CriteriaEvaluationAgent, and ClinicalScopeAnalyzer
    agree on negation scope boundaries on exclusion criteria.
    """
    # Case A: Negated exclusion symptom -> Exclusion is ruled out (NOT_MET)
    ehr_negated = (
        "History of Present Illness: 70-year-old male with severe heart failure. "
        "Physical Exam: Patient denies cardiogenic shock. Blood pressure is stable. "
        "Diagnostics: LVEF is 28%. NYHA Class III symptoms."
    )
    excl_dict = {
        "criterion_code": "CRIT-ICD-EXCL-01",
        "name": "Absence of Cardiogenic Shock",
        "description": "Patient must not be in acute cardiogenic shock",
        "is_exclusion": True,
        "entity_names": ["cardiogenic shock", "shock"]
    }
    decl_excl = DeclarativeCriterion(
        criterion_code="CRIT-ICD-EXCL-01",
        name="Absence of Cardiogenic Shock",
        description="Patient must not be in acute cardiogenic shock",
        clinical_intent="Exclude acute unstable shock",
        criterion_type=CriterionType.EXCLUSION_SYMPTOM,
        entity_names=["cardiogenic shock", "shock"],
        is_exclusion=True
    )

    det_res_a = CriteriaEvaluationAgent().evaluate_criterion(excl_dict, ehr_negated)
    decl_res_a = DeclarativePolicyEngine.evaluate(decl_excl, ehr_negated)
    core_res_a = ClinicalCoreEvaluator.evaluate(excl_dict, ehr_negated)

    assert det_res_a.status == DeterminationStatus.NOT_MET
    assert decl_res_a.status == DeterminationStatus.NOT_MET
    assert core_res_a.status == DeterminationStatus.NOT_MET

    # Case B: Sentence boundary does not leak negation -> Active exclusion present (MET)
    ehr_active = (
        "History of Present Illness: Patient denies fever or chills. "
        "Cardiogenic shock is actively documented requiring inotropes. "
        "Diagnostics: LVEF 25%."
    )
    det_res_b = CriteriaEvaluationAgent().evaluate_criterion(excl_dict, ehr_active)
    decl_res_b = DeclarativePolicyEngine.evaluate(decl_excl, ehr_active)
    core_res_b = ClinicalCoreEvaluator.evaluate(excl_dict, ehr_active)

    assert det_res_b.status == DeterminationStatus.MET
    assert decl_res_b.status == DeterminationStatus.MET
    assert core_res_b.status == DeterminationStatus.MET


def test_declarative_numeric_threshold_and_date_exclusion_cross_mode():
    """
    Test that DeclarativePolicyEngine, CriteriaEvaluationAgent, and ExtractorTools
    agree on numeric cutoff evaluation while ignoring embedded dates.
    """
    ehr_with_dates = (
        "History of Present Illness: Progress note from 05/12/2026. "
        "Diagnostic Studies: Transthoracic echocardiogram on 05/10/2026 confirms LVEF 30%. "
        "Assessment & Plan: Ischemic cardiomyopathy."
    )

    crit_lvef = {
        "criterion_code": "CRIT-ICD-01",
        "name": "LVEF <= 35%",
        "description": "LVEF <= 35% documented on echocardiogram",
        "operator": "<=",
        "threshold": 35.0,
        "target_unit": "%",
        "is_exclusion": False,
        "entity_names": ["LVEF", "ejection fraction"]
    }
    decl_lvef = DeclarativeCriterion(
        criterion_code="CRIT-ICD-01",
        name="LVEF <= 35%",
        description="LVEF <= 35% documented on echocardiogram",
        clinical_intent="Ejection fraction cutoff",
        criterion_type=CriterionType.NUMERIC_THRESHOLD,
        entity_names=["LVEF", "ejection fraction"],
        operator="<=",
        threshold=35.0,
        target_unit="%"
    )

    # 1. Deterministic mode
    det_res = CriteriaEvaluationAgent().evaluate_criterion(crit_lvef, ehr_with_dates)
    assert det_res.status == DeterminationStatus.MET

    # 2. Declarative mode (using shared ClinicalNumericParser date guard & cutoff)
    decl_res = DeclarativePolicyEngine.evaluate(decl_lvef, ehr_with_dates)
    assert decl_res.status == DeterminationStatus.MET

    # 3. Non-qualifying case (LVEF 48%)
    ehr_failing = ehr_with_dates.replace("30%", "48%")
    det_fail = CriteriaEvaluationAgent().evaluate_criterion(crit_lvef, ehr_failing)
    decl_fail = DeclarativePolicyEngine.evaluate(decl_lvef, ehr_failing)
    assert det_fail.status == DeterminationStatus.NOT_MET
    assert decl_fail.status == DeterminationStatus.NOT_MET


def test_declarative_temporal_duration_cross_mode():
    """
    Test that DeclarativePolicyEngine and CriteriaEvaluationAgent agree on
    temporal duration evaluation via ClinicalTemporalParser.
    """
    crit_gdmt = {
        "criterion_code": "CRIT-ICD-03",
        "name": "GDMT Duration >= 90 Days",
        "description": "Guideline-directed medical therapy sustained for >= 90 days",
        "is_exclusion": False,
        "entity_names": ["GDMT", "medical therapy", "carvedilol", "lisinopril"],
        "min_duration_days": 90
    }
    decl_gdmt = DeclarativeCriterion(
        criterion_code="CRIT-ICD-03",
        name="GDMT Duration >= 90 Days",
        description="Guideline-directed medical therapy sustained for >= 90 days",
        clinical_intent="Ensure medical optimization prior to device",
        criterion_type=CriterionType.TEMPORAL_DURATION,
        entity_names=["GDMT", "medical therapy", "carvedilol", "lisinopril"],
        operator=">=",
        min_duration_days=90
    )

    # Case A: 6 months (180 days) -> MET across modes
    ehr_qual = "Medications: Patient maintained on optimal medical therapy for 6 months."
    det_a = CriteriaEvaluationAgent().evaluate_criterion(crit_gdmt, ehr_qual)
    decl_a = DeclarativePolicyEngine.evaluate(decl_gdmt, ehr_qual)
    assert det_a.status == DeterminationStatus.MET
    assert decl_a.status == DeterminationStatus.MET

    # Case B: 3 weeks (21 days) -> NOT_MET across modes
    ehr_short = "Medications: Patient started on medical therapy for 3 weeks."
    det_b = CriteriaEvaluationAgent().evaluate_criterion(crit_gdmt, ehr_short)
    decl_b = DeclarativePolicyEngine.evaluate(decl_gdmt, ehr_short)
    assert det_b.status == DeterminationStatus.NOT_MET
    assert decl_b.status == DeterminationStatus.NOT_MET

    # Case C: Omission (no duration stated) -> INSUFFICIENT_EVIDENCE across modes
    ehr_omitted = "Medications: Patient currently taking carvedilol and lisinopril."
    det_c = CriteriaEvaluationAgent().evaluate_criterion(crit_gdmt, ehr_omitted)
    decl_c = DeclarativePolicyEngine.evaluate(decl_gdmt, ehr_omitted)
    assert det_c.status == DeterminationStatus.INSUFFICIENT_EVIDENCE
    assert decl_c.status == DeterminationStatus.INSUFFICIENT_EVIDENCE


def test_declarative_clinical_section_detector_cross_mode():
    """
    Test that section detection is identical between ClinicalSectionDetector,
    CriteriaEvaluationAgent, and DeclarativePolicyEngine evidence spans.
    """
    ehr_text = (
        "History of Present Illness:\nPatient reports shortness of breath.\n\n"
        "Diagnostic Studies:\nEchocardiogram confirms LVEF 28%.\n\n"
        "Assessment & Plan:\nReferral for ICD placement.\n"
    )

    # Position inside Diagnostic Studies
    pos_echo = ehr_text.find("LVEF 28%")
    sec_core = ClinicalSectionDetector.detect_section(ehr_text, pos_echo)
    sec_agent = CriteriaEvaluationAgent().detect_clinical_section(ehr_text, pos_echo)
    assert sec_core == "Diagnostic Studies"
    assert sec_agent == "Diagnostic Studies"

    # Evaluated span in DeclarativePolicyEngine carries same section
    decl_lvef = DeclarativeCriterion(
        criterion_code="CRIT-ICD-01",
        name="LVEF",
        description="LVEF <= 35%",
        clinical_intent="Ejection fraction cutoff",
        criterion_type=CriterionType.NUMERIC_THRESHOLD,
        entity_names=["LVEF"],
        operator="<=",
        threshold=35.0,
        target_unit="%"
    )
    res = DeclarativePolicyEngine.evaluate(decl_lvef, ehr_text)
    assert len(res.verified_spans) > 0
    assert res.verified_spans[0].clinical_section == "Diagnostic Studies"
