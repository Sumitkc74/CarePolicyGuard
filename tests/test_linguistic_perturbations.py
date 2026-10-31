import pytest
from app.services.perturbation_engine import LinguisticPerturbationEngine
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision
from app.agents.benchmark_engine import BENCHMARK_VIGNETTES

@pytest.fixture
def pipeline():
    return MultiAgentVerificationPipeline()

@pytest.mark.parametrize("vignette_id", ["BENCH-01", "BENCH-04", "BENCH-07", "BENCH-08", "BENCH-10"])
def test_global_synonym_substitution_across_policies(pipeline, vignette_id):
    """
    Verifies that global clinical synonym substitutions across all 5 CMS policies
    maintain decision concordance and character-slice grounding without accuracy decay.
    """
    v = next(item for item in BENCHMARK_VIGNETTES if item["id"] == vignette_id)
    original_text = v["ehr"]
    perturbed_text = LinguisticPerturbationEngine.apply_synonym_substitution(original_text)
    
    # Verify perturbation took effect
    assert perturbed_text != original_text
    
    result = pipeline.adjudicate_sync(
        patient_id=f"PT-SYN-{vignette_id}",
        policy_id=v["policy_id"],
        ehr_narrative=perturbed_text,
        save_record=False
    )
    
    # Decisions must match original gold standard
    assert result.adjudication_decision.value == v["gold_decision"]
    assert result.abstention_status == v["gold_abstain"]
    assert all(a.grounding_status for a in result.verification_audits)

@pytest.mark.parametrize("vignette_id", ["BENCH-01", "BENCH-03"])
def test_syntactic_negation_displacement_across_domains(pipeline, vignette_id):
    """
    Verifies that syntactic inversion (moving pre-negations to post-negations)
    correctly prevents improper exclusion triggers or False Claims Act violations.
    """
    v = next(item for item in BENCHMARK_VIGNETTES if item["id"] == vignette_id)
    perturbed_text = LinguisticPerturbationEngine.apply_negation_displacement(v["ehr"])
    
    result = pipeline.adjudicate_sync(
        patient_id=f"PT-NEG-{vignette_id}",
        policy_id=v["policy_id"],
        ehr_narrative=perturbed_text,
        save_record=False
    )
    
    assert result.adjudication_decision.value == v["gold_decision"]

@pytest.mark.parametrize("vignette_id,omitted_entity", [
    ("BENCH-01", "LVEF"),
    ("BENCH-04", "AHI"),
    ("BENCH-07", "aortic valve area|gradient|velocity|stenosis"),
    ("BENCH-10", "Wagner Grade")
])
def test_adversarial_omission_across_all_specialties(pipeline, vignette_id, omitted_entity):
    """
    Adversarial Safety Stress Test:
    When mandatory diagnostic metrics (LVEF, AHI, AVA, Wagner Grade) are stripped from qualifying notes,
    the framework MUST NEVER falsely approve. It must safely DENY or DEFER_TO_HUMAN.
    """
    v = next(item for item in BENCHMARK_VIGNETTES if item["id"] == vignette_id)
    omitted_text = LinguisticPerturbationEngine.apply_evidence_omission(v["ehr"], omitted_entity)
    
    for kw in omitted_entity.split("|"):
        assert kw.strip().lower() not in omitted_text.lower()
    
    result = pipeline.adjudicate_sync(
        patient_id=f"PT-OMIT-{vignette_id}",
        policy_id=v["policy_id"],
        ehr_narrative=omitted_text,
        save_record=False
    )
    
    # Invariant: Must NEVER issue a false approval on missing mandatory diagnostic criteria
    assert result.adjudication_decision != AdjudicationDecision.APPROVED
    assert result.adjudication_decision in (AdjudicationDecision.DENIED, AdjudicationDecision.DEFERRED_TO_HUMAN)

def test_formatting_shorthand_noise_handling(pipeline):
    """
    Verifies that converting prose into bulleted diagnostic shorthand notation
    preserves character grounding and clinical determination.
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
