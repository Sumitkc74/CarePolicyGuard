import pytest
from app.services.perturbation_engine import LinguisticPerturbationEngine
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, FinalAdjudication
from app.agents.benchmark_engine import BENCHMARK_VIGNETTES

@pytest.fixture
def pipeline():
    return MultiAgentVerificationPipeline()

def test_synonym_substitution_robustness(pipeline):
    """
    Verifies that clinical synonym substitutions (e.g., LVEF <-> Left Ventricular Ejection Fraction)
    maintain accurate adjudication and character grounding without decision degradation.
    """
    v01 = next(v for v in BENCHMARK_VIGNETTES if v["id"] == "BENCH-01")
    original_text = v01["ehr"]
    perturbed_text = LinguisticPerturbationEngine.apply_synonym_substitution(original_text)
    
    # Ensure text was actually perturbed
    assert perturbed_text != original_text
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-SYN-01",
        policy_id=v01["policy_id"],
        ehr_narrative=perturbed_text,
        save_record=False
    )
    
    assert result.adjudication_decision == AdjudicationDecision.APPROVED
    assert result.abstention_status is False
    assert all(a.grounding_status for a in result.verification_audits)

def test_negation_displacement_robustness(pipeline):
    """
    Verifies that shifting negation syntax (pre-negation 'no cardiogenic shock' to
    post-negation 'cardiogenic shock is absent and ruled out') correctly prevents exclusion activation.
    """
    v01 = next(v for v in BENCHMARK_VIGNETTES if v["id"] == "BENCH-01")
    perturbed_text = LinguisticPerturbationEngine.apply_negation_displacement(v01["ehr"])
    
    assert "cardiogenic shock is absent and ruled out" in perturbed_text
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-NEG-01",
        policy_id=v01["policy_id"],
        ehr_narrative=perturbed_text,
        save_record=False
    )
    
    assert result.adjudication_decision == AdjudicationDecision.APPROVED
    assert result.abstention_status is False

def test_adversarial_omission_triggers_abstention_or_denial(pipeline):
    """
    Adversarial Stress Test: When mandatory clinical evidence (LVEF metric) is stripped from a qualifying note,
    the framework MUST NOT falsely approve. It must either DENY or DEFER_TO_HUMAN.
    """
    v01 = next(v for v in BENCHMARK_VIGNETTES if v["id"] == "BENCH-01")
    omitted_text = LinguisticPerturbationEngine.apply_evidence_omission(v01["ehr"], "LVEF")
    
    # Ensure LVEF was stripped
    assert "LVEF" not in omitted_text
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-OMIT-01",
        policy_id=v01["policy_id"],
        ehr_narrative=omitted_text,
        save_record=False
    )
    
    # Absolute safety check: CANNOT be APPROVED
    assert result.adjudication_decision != AdjudicationDecision.APPROVED
    assert result.adjudication_decision in (AdjudicationDecision.DENIED, AdjudicationDecision.DEFERRED_TO_HUMAN)

def test_formatting_shorthand_noise_handling(pipeline):
    """
    Verifies that converting prose into bulleted diagnostic shorthand preserves character grounding and decision.
    """
    v01 = next(v for v in BENCHMARK_VIGNETTES if v["id"] == "BENCH-01")
    noisy_text = LinguisticPerturbationEngine.apply_formatting_noise(v01["ehr"])
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-NOISE-01",
        policy_id=v01["policy_id"],
        ehr_narrative=noisy_text,
        save_record=False
    )
    
    assert result.adjudication_decision == AdjudicationDecision.APPROVED
