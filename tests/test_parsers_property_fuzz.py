"""
Property and Fuzz Tests for Clinical Parsers.
Validates:
1. Numeric parser robustness against embedded calendar dates and noisy formatting.
2. Temporal parser behavior on valid/invalid date strings, negative deltas, and multi-scale durations.
3. Negation scope boundaries across conjunctions, sentence terminators, semicolons, parentheses, and multiline blocks.
"""

import random
from datetime import datetime, timedelta
import pytest

from app.core.clinical_core import (
    ClinicalScopeAnalyzer,
    ClinicalNumericParser,
    ClinicalTemporalParser,
    ClinicalGroundingVerifier
)
from app.services.declarative_engine import DeclarativePolicyEngine
from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType
from app.schemas.contracts import DeterminationStatus


# -------------------------------------------------------------------------
# 1. Numeric Parser Fuzz & Date Exclusion Tests
# -------------------------------------------------------------------------

def test_fuzz_random_dates_never_extracted_as_measurements():
    """
    Generate 50 random dates in YYYY-MM-DD, MM/DD/YYYY, and DD-MM-YYYY formats,
    place them next to clinical terms (LVEF, AHI), and verify that dates are
    never extracted as qualifying clinical values.
    """
    random.seed(42)
    start_date = datetime(1980, 1, 1)
    
    crit_lvef = DeclarativeCriterion(
        criterion_code="CRIT-ICD-01",
        name="LVEF",
        description="Left Ventricular Ejection Fraction <= 35%",
        clinical_intent="Ejection fraction threshold",
        criterion_type=CriterionType.NUMERIC_THRESHOLD,
        entity_names=["LVEF", "ejection fraction"],
        operator="<=",
        threshold=35.0,
        target_unit="%"
    )

    formats = [
        lambda dt: dt.strftime("%Y-%m-%d"),
        lambda dt: dt.strftime("%m/%d/%Y"),
        lambda dt: dt.strftime("%d-%m-%Y"),
        lambda dt: dt.strftime("%Y/%m/%d"),
    ]

    for _ in range(50):
        days_offset = random.randint(0, 15000)
        dt = start_date + timedelta(days=days_offset)
        fmt_fn = random.choice(formats)
        date_str = fmt_fn(dt)

        # Text with date right after LVEF, but NO real measurement
        note = f"Prior examination LVEF on {date_str}. Patient assessed for follow-up."
        
        # Core date detection check
        pos = note.find(date_str)
        assert pos != -1
        # The numbers inside the date must be recognized as date patterns
        num_len = 2 if len(date_str) >= 2 else 1
        assert ClinicalNumericParser.is_date_pattern(note, pos, pos + num_len) or \
               ClinicalNumericParser.is_date_pattern(note, pos + 5, pos + 7)

        # Declarative engine evaluation on date-only note should NOT approve or falsely assess
        assessment = DeclarativePolicyEngine.evaluate(crit_lvef, note)
        assert assessment.status == DeterminationStatus.INSUFFICIENT_EVIDENCE


def test_fuzz_numeric_cutoff_operator_invariants():
    """
    Verify operator correctness across 200 random numeric values and thresholds.
    """
    random.seed(1234)
    for _ in range(200):
        val = round(random.uniform(-100.0, 200.0), 2)
        thresh = round(random.uniform(-100.0, 200.0), 2)

        # Operator <=
        assert ClinicalNumericParser.evaluate_cutoff(val, "<=", thresh) == (val <= thresh)
        # Operator >=
        assert ClinicalNumericParser.evaluate_cutoff(val, ">=", thresh) == (val >= thresh)
        # Operator <
        assert ClinicalNumericParser.evaluate_cutoff(val, "<", thresh) == (val < thresh)
        # Operator >
        assert ClinicalNumericParser.evaluate_cutoff(val, ">", thresh) == (val > thresh)
        # Operator ==
        assert ClinicalNumericParser.evaluate_cutoff(val, "==", thresh) == (abs(val - thresh) < 1e-5)


# -------------------------------------------------------------------------
# 2. Temporal Parser Fuzz & Boundary Tests
# -------------------------------------------------------------------------

def test_temporal_parser_fuzz_and_edge_cases():
    """
    Tests calendar date calculation across valid spans, reverse spans,
    and invalid date formats.
    """
    # Valid delta
    d1 = "2025-01-01"
    d2 = "2025-03-01"
    assert ClinicalTemporalParser.calculate_calendar_delta(d1, d2) == 59
    # Reversed chronological order (must return absolute elapsed days)
    assert ClinicalTemporalParser.calculate_calendar_delta(d2, d1) == 59

    # Malformed dates should gracefully return None
    assert ClinicalTemporalParser.calculate_calendar_delta("invalid-date", "2025-01-01") is None
    assert ClinicalTemporalParser.calculate_calendar_delta("2025/01/01", "2025-01-01") is None
    assert ClinicalTemporalParser.calculate_calendar_delta("", "") is None

    # Multi-unit duration parser
    assert ClinicalTemporalParser.parse_duration_to_days(0, "days") == 0
    assert ClinicalTemporalParser.parse_duration_to_days(14, "days") == 14
    assert ClinicalTemporalParser.parse_duration_to_days(6, "weeks") == 42
    assert ClinicalTemporalParser.parse_duration_to_days(3, "months") == 90
    assert ClinicalTemporalParser.parse_duration_to_days(2, "years") == 730


# -------------------------------------------------------------------------
# 3. Negation Scope Boundary Tests
# -------------------------------------------------------------------------

@pytest.mark.parametrize("separator", [
    ". ",
    "\n",
    "\n\n",
    "; ",
    ";",
])
def test_negation_scope_respects_sentence_clause_boundaries(separator):
    """
    Negation triggers before a boundary must NOT spill over past the boundary.
    """
    text = f"Patient denies heart failure{separator}Severe symptomatic aortic stenosis documented."
    start_as = text.find("aortic stenosis")
    end_as = start_as + len("aortic stenosis")

    res = ClinicalScopeAnalyzer.analyze_scope(text, start_as, end_as)
    assert res["is_negated"] is False


@pytest.mark.parametrize("conjunction", [
    "but",
    "however",
    "nevertheless",
    "although",
    "except",
    "yet"
])
def test_negation_scope_resets_at_conjunctions(conjunction):
    """
    Negation trigger within same sentence is cancelled when a contrastive conjunction appears.
    """
    text = f"No evidence of coronary disease, {conjunction} patient exhibits severe dyspnea on exertion."
    start_disp = text.find("severe dyspnea")
    end_disp = start_disp + len("severe dyspnea")

    res = ClinicalScopeAnalyzer.analyze_scope(text, start_disp, end_disp)
    assert res["is_negated"] is False


def test_negation_scope_parentheses_and_multiline_blocks():
    """
    Verify negation detection behavior in parenthetical comments and multiline EHR blocks.
    """
    # Parenthetical note: target inside negated clause
    text_paren = "Clinical Status: Stable (denies angina or orthopnea). LVEF 28%."
    start_ang = text_paren.find("angina")
    end_ang = start_ang + len("angina")
    res_ang = ClinicalScopeAnalyzer.analyze_scope(text_paren, start_ang, end_ang)
    assert res_ang["is_negated"] is True

    # Target outside parentheses in subsequent sentence
    start_lvef = text_paren.find("LVEF")
    end_lvef = start_lvef + len("LVEF")
    res_lvef = ClinicalScopeAnalyzer.analyze_scope(text_paren, start_lvef, end_lvef)
    assert res_lvef["is_negated"] is False

    # Multiline block
    text_multiline = (
        "REVIEW OF SYSTEMS:\n"
        "- Cardiovascular: Denies chest pain, palpitation\n"
        "- Respiratory: Chronic dyspnea, wheezing present\n"
        "- Neurological: Unremarkable\n"
    )
    start_dys = text_multiline.find("Chronic dyspnea")
    end_dys = start_dys + len("Chronic dyspnea")
    res_dys = ClinicalScopeAnalyzer.analyze_scope(text_multiline, start_dys, end_dys)
    assert res_dys["is_negated"] is False
