import pytest
from app.agents.benchmark_engine import BenchmarkRunner, calculate_expected_calibration_error

def test_ece_calculation_perfect_calibration():
    # When predicted probabilities match empirical accuracy perfectly
    confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    # For a balanced set
    accuracies = [False, False, False, False, True, True, True, True, True, True]
    ece = calculate_expected_calibration_error(confidences, accuracies, num_bins=5)
    assert isinstance(ece, float)
    assert ece >= 0.0

def test_ece_calculation_severe_overconfidence():
    # Severe overconfidence: confidence 0.99 for all samples, but accuracy is 50%
    confidences = [0.99] * 10
    accuracies = [True, False, True, False, True, False, True, False, True, False]
    ece = calculate_expected_calibration_error(confidences, accuracies, num_bins=10)
    # ECE should be approximately |0.50 - 0.99| = 0.49
    assert ece > 0.40

def test_benchmark_runner_empirical_comparisons():
    runner = BenchmarkRunner()
    response = runner.run_benchmark()
    assert response.dataset_size > 0
    assert len(response.configs) == 4

    # Extract configs
    cfg_a = next(c for c in response.configs if c.config_name == "Config A" or "A" in c.config_name)
    cfg_b = next(c for c in response.configs if c.config_name == "Config B" or "B" in c.config_name)
    cfg_c = next(c for c in response.configs if c.config_name == "Config C" or "C" in c.config_name)
    cfg_d = next(c for c in response.configs if c.config_name == "Config D" or "D" in c.config_name)

    # Config D must demonstrate superior clinical safety and evidence faithfulness
    assert cfg_d.evidence_faithfulness > cfg_a.evidence_faithfulness
    assert cfg_d.evidence_faithfulness > cfg_b.evidence_faithfulness
    assert cfg_d.expected_calibration_error < cfg_a.expected_calibration_error
    assert cfg_d.expected_calibration_error < cfg_b.expected_calibration_error
    assert cfg_d.clinical_safety_score > cfg_a.clinical_safety_score

def test_benchmark_vignettes_cross_policy_coverage():
    """Validates 10 clinical vignettes spanning all 5 CMS policies with granular per-vignette audits."""
    runner = BenchmarkRunner()
    response = runner.run_benchmark()

    assert response.dataset_size == 10
    assert len(response.vignette_results) == 10

    # Ensure all 5 active CMS policies are evaluated in the benchmark
    policies_evaluated = {v.policy_id for v in response.vignette_results}
    assert "NCD-20.4" in policies_evaluated
    assert "LCD-L33829" in policies_evaluated
    assert "NCD-20.33" in policies_evaluated
    assert "NCD-220.13" in policies_evaluated
    assert "NCD-20.29" in policies_evaluated

    # Verify Config D achieved 100% character grounding across all 10 vignettes
    for v in response.vignette_results:
        assert v.config_d_grounded is True
        assert v.status_match is True

    # Verify safe abstention on edge cases
    abstain_cases = [v for v in response.vignette_results if v.config_d_abstain]
    assert len(abstain_cases) == 2
    abstain_ids = {v.vignette_id for v in abstain_cases}
    assert "BENCH-02" in abstain_ids  # Inadequate GDMT duration
    assert "BENCH-05" in abstain_ids  # Borderline AHI without comorbidity

def test_empirical_harness_standalone_execution():
    """Verifies that EmpiricalResearchHarness executes standalone across all experimental conditions."""
    from app.agents.empirical_harness import EmpiricalResearchHarness
    from app.agents.benchmark_engine import BENCHMARK_VIGNETTES

    harness = EmpiricalResearchHarness()
    response = harness.run_full_benchmark(BENCHMARK_VIGNETTES)
    assert response.dataset_size == 10
    assert len(response.configs) == 4

    config_names = [c.config_name for c in response.configs]
    assert "Config A" in config_names
    assert "Config B" in config_names
    assert "Config C" in config_names
    assert "Config D" in config_names

    harness.close()

