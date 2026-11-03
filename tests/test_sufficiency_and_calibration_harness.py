import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision
from app.services.calibration_harness import CalibrationHarness


def test_sufficiency_reporting_present_for_approvals_and_deferrals():
    """
    Task 2: Proves sufficiency score reporting is present for all decisions
    (including approved and deferred cases), with formula documented and counts accurate.
    """
    pipeline = MultiAgentVerificationPipeline()

    # Case 1: Approved case
    ehr_approved = (
        "CARDIOLOGY NOTE: Patient with ischemic cardiomyopathy.\n"
        "Echocardiogram confirms LVEF 24%. NYHA Class II dyspnea.\n"
        "Maintained on GDMT (carvedilol and lisinopril) for 6 months.\n"
        "Myocardial infarction occurred 2 years ago (> 40 days). No acute cardiogenic shock."
    )
    res_app = pipeline.adjudicate_sync("PT-SUFF-APP", "NCD-20.4", ehr_approved, save_record=False)

    assert hasattr(res_app, "score_type")
    assert res_app.score_type == "sufficiency_score"
    assert hasattr(res_app, "sufficiency_score")
    assert res_app.sufficiency_score > 0.0
    assert hasattr(res_app, "sufficiency_formula")
    assert "criteria_sufficiency_weighted_sum" in res_app.sufficiency_formula
    assert res_app.criteria_total_count == 5
    assert res_app.criteria_met_count == 4  # 4 inclusion criteria met

    # Case 2: Deferred case
    ehr_deferred = (
        "CARDIOLOGY NOTE: Patient evaluated for heart failure.\n"
        "NYHA Class II. GDMT for 1 year. Remote MI.\n"
        "Echocardiogram was ordered but results pending."
    )
    res_def = pipeline.adjudicate_sync("PT-SUFF-DEF", "NCD-20.4", ehr_deferred, save_record=False)

    assert res_def.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res_def.score_type == "sufficiency_score"
    assert res_def.criteria_total_count == 5
    assert len(res_def.insufficient_criteria) > 0 or len(res_def.missing_criteria) > 0
    assert res_def.deferral_reason is not None


def test_calibration_harness_rejects_fit_on_test_data():
    """
    Task 2: Proves that the CalibrationHarness strictly rejects evaluating
    on the same dataset partition it was fitted on, preventing data leakage.
    """
    harness = CalibrationHarness(method="temperature")
    data_partition = [
        {"case_id": "VAL-01", "raw_score": 0.95, "is_correct": 1},
        {"case_id": "VAL-02", "raw_score": 0.88, "is_correct": 1},
        {"case_id": "VAL-03", "raw_score": 0.60, "is_correct": 0},
        {"case_id": "VAL-04", "raw_score": 0.75, "is_correct": 1},
    ]

    harness.fit(data_partition)
    assert harness.is_fitted is True
    assert harness.temperature > 0.0

    # Attempting to evaluate on the exact same dataset must raise ValueError
    with pytest.raises(ValueError, match="same dataset"):
        harness.evaluate(data_partition)


def test_calibration_harness_evaluates_on_disjoint_test_data():
    """
    Task 2: Proves that the CalibrationHarness generates valid ECE, Brier score,
    reliability summary, and coverage-accuracy curves on independent test records.
    """
    harness = CalibrationHarness(method="temperature")
    val_data = [
        {"case_id": "VAL-01", "raw_score": 0.92, "is_correct": 1},
        {"case_id": "VAL-02", "raw_score": 0.85, "is_correct": 1},
        {"case_id": "VAL-03", "raw_score": 0.65, "is_correct": 0},
        {"case_id": "VAL-04", "raw_score": 0.78, "is_correct": 1},
    ]
    test_data = [
        {"case_id": "TEST-01", "raw_score": 0.94, "is_correct": 1, "is_false_approval": False},
        {"case_id": "TEST-02", "raw_score": 0.82, "is_correct": 1, "is_false_approval": False},
        {"case_id": "TEST-03", "raw_score": 0.55, "is_correct": 0, "is_false_approval": True},
        {"case_id": "TEST-04", "raw_score": 0.89, "is_correct": 1, "is_false_approval": False},
    ]

    harness.fit(val_data)
    results = harness.evaluate(test_data)

    assert results["is_calibrated"] is True
    assert "expected_calibration_error" in results
    assert "brier_score" in results
    assert "coverage_accuracy_curve" in results
    assert len(results["coverage_accuracy_curve"]) == 7  # 7 evaluated thresholds


def test_selective_risk_threshold_derivation():
    """
    Task 2: Proves derivation of threshold tau based on target false approval rate.
    """
    val_data = [
        {"case_id": "VAL-01", "raw_score": 0.95, "is_correct": 1, "is_false_approval": False},
        {"case_id": "VAL-02", "raw_score": 0.88, "is_correct": 1, "is_false_approval": False},
        {"case_id": "VAL-03", "raw_score": 0.72, "is_correct": 0, "is_false_approval": True},
        {"case_id": "VAL-04", "raw_score": 0.60, "is_correct": 0, "is_false_approval": False},
    ]
    derived = CalibrationHarness.derive_selective_risk_threshold(val_data, max_false_approval_rate=0.0)

    assert derived["derived_threshold_tau"] >= 0.85  # Must filter out 0.72 false approval
    assert derived["target_false_approval_rate"] == 0.0
    assert "uncalibrated_operating_tradeoff_note" in derived


def test_uncalibrated_determination_emits_null_calibrated_confidence():
    """
    Task 3: Proves that in normal uncalibrated runtime, the pipeline outputs
    a documented sufficiency score and strictly sets calibrated_aggregate_confidence to None,
    ensuring no heuristic value wears a calibrated name.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "CARDIOLOGY NOTE: Patient with ischemic cardiomyopathy.\n"
        "Echocardiogram confirms LVEF 24%. NYHA Class II dyspnea.\n"
        "Maintained on GDMT (carvedilol and lisinopril) for 6 months.\n"
        "Myocardial infarction occurred 2 years ago. No acute cardiogenic shock."
    )
    result = pipeline.adjudicate_sync("PT-TEST-CAL-HONEST", "NCD-20.4", ehr, save_record=False)

    assert result.score_type == "sufficiency_score"
    assert result.sufficiency_score is not None
    assert result.sufficiency_score > 0.0
    # Strictly null when uncalibrated
    assert result.calibrated_aggregate_confidence is None
    assert "No empirical calibration model fitted" in result.calibrated_confidence_explanation


def test_genuinely_calibrated_value_reported_when_produced_via_harness():
    """
    Task 3: Proves that an empirical calibrated confidence value is ONLY populated
    when produced through the calibration harness on validation data.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "CARDIOLOGY NOTE: Patient with ischemic cardiomyopathy.\n"
        "Echocardiogram confirms LVEF 24%. NYHA Class II dyspnea.\n"
        "Maintained on GDMT (carvedilol and lisinopril) for 6 months.\n"
        "Myocardial infarction occurred 2 years ago. No acute cardiogenic shock."
    )
    uncalibrated = pipeline.adjudicate_sync("PT-TEST-CAL-EMP", "NCD-20.4", ehr, save_record=False)
    assert uncalibrated.calibrated_aggregate_confidence is None

    # Fit calibration harness on validation data
    harness = CalibrationHarness(method="temperature")
    val_data = [
        {"case_id": "VAL-01", "raw_score": 0.95, "is_correct": 1},
        {"case_id": "VAL-02", "raw_score": 0.88, "is_correct": 1},
        {"case_id": "VAL-03", "raw_score": 0.65, "is_correct": 0},
        {"case_id": "VAL-04", "raw_score": 0.78, "is_correct": 1},
    ]
    harness.fit(val_data)

    calibrated = harness.calibrate_determination(uncalibrated)
    assert calibrated.calibrated_aggregate_confidence is not None
    assert isinstance(calibrated.calibrated_aggregate_confidence, float)
    assert 0.0 <= calibrated.calibrated_aggregate_confidence <= 1.0
    assert "Empirically calibrated via Temperature Scaling" in calibrated.calibrated_confidence_explanation


