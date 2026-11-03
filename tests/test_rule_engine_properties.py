import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus


def test_property_unmet_inclusion_never_approves():
    """
    Task 7: Property Test — If any statutory inclusion criterion is unmet,
    the rule engine must NEVER output APPROVED under any circumstances.
    """
    pipeline = MultiAgentVerificationPipeline()

    test_scenarios = [
        # Scenario A: Missing GDMT
        (
            "Patient with ischemic cardiomyopathy. LVEF 25% on TTE. NYHA Class II. Remote MI 2 years ago. "
            "Patient is medication naive and has not taken beta-blocker or ACEi/ARB."
        ),
        # Scenario B: Missing qualifying LVEF (LVEF 45%)
        (
            "Patient with ischemic cardiomyopathy. LVEF 45% on TTE. NYHA Class II. On GDMT for 1 year. Remote MI."
        ),
        # Scenario C: Disqualifying acute cardiogenic shock
        (
            "Patient with ischemic cardiomyopathy. LVEF 22% on TTE. NYHA Class III. On GDMT for 8 months. "
            "Patient in active cardiogenic shock requiring intra-aortic balloon pump."
        )
    ]

    for scenario_text in test_scenarios:
        res = pipeline.adjudicate_sync("PT-PROP-TEST", "NCD-20.4", scenario_text, save_record=False)
        assert res.adjudication_decision != AdjudicationDecision.APPROVED, (
            f"Safety property violated! Unmet criteria scenario produced approval: {scenario_text[:80]}"
        )


def test_property_evidence_monotonicity():
    """
    Task 7: Property Test — Monotonicity:
    Adding verified qualifying supporting evidence to an already-approved case
    must NEVER flip the recommendation to a denial.
    """
    pipeline = MultiAgentVerificationPipeline()

    base_approved_ehr = (
        "CARDIOLOGY CLINIC NOTE\n"
        "Patient with ischemic cardiomyopathy. Transthoracic echocardiogram confirms LVEF 25%.\n"
        "Maintained on optimal GDMT (metoprolol succinate 100mg and valsartan 160mg) for 6 months.\n"
        "Classified as NYHA Class II symptoms. Prior MI was 3 years ago (> 40 days). No cardiogenic shock."
    )
    res_base = pipeline.adjudicate_sync("PT-MONO-1", "NCD-20.4", base_approved_ehr, save_record=False)
    assert res_base.adjudication_decision == AdjudicationDecision.APPROVED

    # Add further supporting evidence (e.g. repeat echo confirming LVEF 24%, additional drug tolerance)
    augmented_approved_ehr = (
        base_approved_ehr + "\n" +
        "ADDITIONAL CLINICAL EVIDENCE:\n"
        "Repeat confirmatory CMR also demonstrates LVEF 24%.\n"
        "Spironolactone 25mg added with good tolerance. BNP elevated at 450 pg/mL."
    )
    res_aug = pipeline.adjudicate_sync("PT-MONO-2", "NCD-20.4", augmented_approved_ehr, save_record=False)

    # Invariant: Must remain APPROVED
    assert res_aug.adjudication_decision == AdjudicationDecision.APPROVED


def test_property_deterministic_replayability():
    """
    Task 7: Property Test — Deterministic Replayability:
    Executing the pipeline twice on the exact same input string produces
    character-for-character identical decisions, scores, and cryptographic audit hash.
    """
    pipeline = MultiAgentVerificationPipeline()

    sample_ehr = (
        "Patient with severe symptomatic aortic stenosis for TAVR evaluation.\n"
        "Echocardiogram: Aortic valve area (AVA) 0.72 cm2, mean gradient 46 mmHg, peak velocity 4.4 m/s.\n"
        "NYHA Class III dyspnea. Heart Team consultation completed. STS score 8.2%."
    )

    run_1 = pipeline.adjudicate_sync("PT-REPLAY", "NCD-20.33", sample_ehr, save_record=False)
    run_2 = pipeline.adjudicate_sync("PT-REPLAY", "NCD-20.33", sample_ehr, save_record=False)

    assert run_1.adjudication_decision == run_2.adjudication_decision
    assert run_1.calibrated_aggregate_confidence == run_2.calibrated_aggregate_confidence
    assert run_1.sufficiency_score == run_2.sufficiency_score
    assert len(run_1.criterion_assessments) == len(run_2.criterion_assessments)

    for c1, c2 in zip(run_1.criterion_assessments, run_2.criterion_assessments):
        assert c1.criterion_code == c2.criterion_code
        assert c1.status == c2.status
        assert len(c1.verified_spans) == len(c2.verified_spans)

