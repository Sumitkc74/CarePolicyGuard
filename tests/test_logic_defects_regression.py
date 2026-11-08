"""
Regression tests for Task 3: Three Diagnosed Logic Defects
- (a) DEV-OPD-BOTOX-APP: Numeric extractor binding to 18 headache days instead of 12 days
- (b) DEV-OPD-RHINO-APP: Temporal duration binding to 1 year (365 days) instead of 8 weeks (56 days) for chronic airway obstruction
- (c) DEV-OPD-VEIN-APP: Regex accepting 4-digit numeric values (1450 ms >= 500 ms)
"""

import pytest
from app.schemas.contracts import DeterminationStatus, AdjudicationDecision
from app.services.declarative_engine import DeclarativePolicyEngine
from app.agents.pipeline import MultiAgentVerificationPipeline


def test_regression_botox_numeric_extractor_binds_to_18_headache_days():
    """
    (a) DEV-OPD-BOTOX-APP: The note mentions '18 headache days per month, with 12 days meeting full criteria'.
    The numeric extractor must bind to '18 headache days per month' (>= 15 threshold -> MET),
    not the downstream 12 days.
    """
    policy = DeclarativePolicyEngine.load_policy("OPD-BOTOX")
    assert policy is not None

    narrative = (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Comprehensive Headache Center\n"
        "SUBJECTIVE: 42-year-old presenting with chronic debilitating headaches for 2 years. "
        "Headache diary confirms 18 headache days per month, with 12 days meeting full criteria for "
        "throbbing migraine with photophobia and nausea. Patient has completed adequate 8-week trials "
        "of topiramate and propranolol without efficacy.\n"
        "OBJECTIVE: Normal neurological examination. Normal brain MRI. Documented adherence to headache calendar.\n"
        "ASSESSMENT & PLAN: Chronic migraine refractory to two oral prophylactic classes. Plan: Botox injection."
    )

    assessments = DeclarativePolicyEngine.evaluate_policy(policy, narrative)
    crit_map = {ca.criterion_code: ca for ca in assessments}

    assert "CRIT-BOTOX-01" in crit_map
    crit_01 = crit_map["CRIT-BOTOX-01"]
    assert crit_01.status == DeterminationStatus.MET
    assert any("18" in s.source_text for s in crit_01.verified_spans)
    assert not any("12" in s.source_text for s in crit_01.verified_spans)


def test_regression_rhino_temporal_extractor_binds_to_1_year():
    """
    (b) DEV-OPD-RHINO-APP: The note mentions chronic nasal airway obstruction for 1 year (365 days),
    and a trial of fluticasone spray for 8 weeks (56 days).
    For CRIT-RHINO-01 (min_duration_days = 180), the temporal extractor must bind to
    the 1 year condition duration (>= 180 days -> MET), not the 8-week medical therapy trial.
    """
    policy = DeclarativePolicyEngine.load_policy("OPD-RHINO")
    assert policy is not None

    narrative = (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Otolaryngology - Head and Neck Surgery\n"
        "SUBJECTIVE: 36-year-old presenting with chronic unilateral right-sided nasal airway obstruction "
        "causing persistent mouth breathing and sleep disruption for 1 year following nasal trauma. "
        "Patient has used intranasal fluticasone spray and nasal saline irrigations consistently for 8 weeks "
        "without improvement in airflow. Denies cosmetic dissatisfaction.\n"
        "OBJECTIVE: Anterior rhinoscopy reveals marked S-shaped nasal septal deviation.\n"
        "ASSESSMENT & PLAN: Structural nasal airway obstruction. Plan: Functional septoplasty."
    )

    assessments = DeclarativePolicyEngine.evaluate_policy(policy, narrative)
    crit_map = {ca.criterion_code: ca for ca in assessments}

    assert "CRIT-RHINO-01" in crit_map
    crit_01 = crit_map["CRIT-RHINO-01"]
    assert crit_01.status == DeterminationStatus.MET
    assert any("1 year" in s.source_text.lower() for s in crit_01.verified_spans)
    assert not any("8 weeks" in s.source_text.lower() for s in crit_01.verified_spans)


def test_regression_vein_regex_accepts_4_digit_1450_ms():
    """
    (c) DEV-OPD-VEIN-APP: Duplex ultrasound demonstrates reflux duration of 1450 ms (>= 500 ms threshold).
    The numeric extractor regex must allow 4-digit numbers (\\d{1,5}) and successfully match 1450 ms -> MET.
    """
    policy = DeclarativePolicyEngine.load_policy("OPD-VEIN")
    assert policy is not None

    narrative = (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Vascular Surgery Outpatient Clinic\n"
        "SUBJECTIVE: 52-year-old presenting with severe aching in right lower extremity. Symptoms present for 2 years. "
        "Patient has worn prescription 20-30 mmHg compression stockings daily for 16 weeks with persistent swelling. "
        "Denies cosmetic concerns.\n"
        "OBJECTIVE: Visible bulging varicosities. Standing duplex ultrasound demonstrates great saphenous vein "
        "reflux duration of 1450 ms at the saphenofemoral junction with vein diameter of 7.8 mm.\n"
        "ASSESSMENT & PLAN: Symptomatic severe saphenofemoral incompetence. Plan: Endovenous ablation."
    )

    assessments = DeclarativePolicyEngine.evaluate_policy(policy, narrative)
    crit_map = {ca.criterion_code: ca for ca in assessments}

    assert "CRIT-VEIN-01" in crit_map
    crit_01 = crit_map["CRIT-VEIN-01"]
    assert crit_01.status == DeterminationStatus.MET
    assert any("1450 ms" in s.source_text for s in crit_01.verified_spans)


def test_regression_three_diagnosed_vignettes_end_to_end_pipeline():
    """
    End-to-end verification through MultiAgentVerificationPipeline:
    All three previously failing dev cases now adjudicate to APPROVED.
    """
    pipeline = MultiAgentVerificationPipeline(db=None)

    # 1. BOTOX
    botox_note = (
        "42yo with chronic headaches for 2 years. Headache diary confirms 18 headache days per month, "
        "with 12 days meeting migraine criteria. Trials of topiramate and propranolol failed."
    )
    res_botox = pipeline.adjudicate_sync("PT-REG-01", "OPD-BOTOX", botox_note, execution_mode="declarative", save_record=False)
    assert res_botox.adjudication_decision == AdjudicationDecision.APPROVED

    # 2. RHINO
    rhino_note = (
        "36yo presenting with chronic nasal airway obstruction causing persistent mouth breathing for 1 year. "
        "Trial of fluticasone spray for 8 weeks without improvement. Denies cosmetic dissatisfaction."
    )
    res_rhino = pipeline.adjudicate_sync("PT-REG-02", "OPD-RHINO", rhino_note, execution_mode="declarative", save_record=False)
    assert res_rhino.adjudication_decision == AdjudicationDecision.APPROVED

    # 3. VEIN
    vein_note = (
        "52yo with lower extremity pain for 2 years. Prescription compression stockings worn for 16 weeks without relief. "
        "Duplex ultrasound demonstrates great saphenous vein reflux duration of 1450 ms. Denies cosmetic concerns."
    )
    res_vein = pipeline.adjudicate_sync("PT-REG-03", "OPD-VEIN", vein_note, execution_mode="declarative", save_record=False)
    assert res_vein.adjudication_decision == AdjudicationDecision.APPROVED
