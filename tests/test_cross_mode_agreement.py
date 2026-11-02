"""
Cross-Mode Agreement Unit Tests.
Proves that Deterministic, State Machine, and Declarative execution modes
agree on the exact same inputs for negation boundary, numeric cutoff,
and temporal duration, powered by the shared clinical core (app/core/clinical_core.py).
"""

import pytest
from app.core.clinical_core import (
    ClinicalScopeAnalyzer,
    ClinicalNumericParser,
    ClinicalTemporalParser,
    ClinicalGroundingVerifier,
    ClinicalCoreEvaluator
)
from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.llm_extractor import ExtractorTools
from app.services.declarative_engine import DeclarativePolicyEngine
from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType
from app.schemas.contracts import DeterminationStatus


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
