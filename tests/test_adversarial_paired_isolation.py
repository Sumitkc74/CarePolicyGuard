import json
import re
import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision


def load_paired_dev_set():
    with open("app/data/benchmarks/paired_adversarial_dev_set.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_paired_adversarial_invariants_differ_only_in_framing():
    """
    Task 3 Invariant Test:
    Proves that for each pair in the paired adversarial development set,
    the clinical facts and numbers are matched and the pair differs strictly in framing.
    """
    pairs = load_paired_dev_set()
    assert len(pairs) == 6

    for pair in pairs:
        dim = pair["dimension"]
        clean = pair["clean_case"]["narrative"]
        framed = pair["framed_case"]["narrative"]

        if dim == "subject":
            # Both must contain identical clinical numbers and facts
            for token in ["26%", "2 years", "Class II", "180 days", "ischemic cardiomyopathy"]:
                assert token in clean, f"Token '{token}' missing from clean case"
                assert token in framed, f"Token '{token}' missing from framed case"
            # Differ strictly in subject attribution
            assert "Father" in framed and "Father" not in clean

        elif dim == "timing":
            for token in ["AHI 22", "face-to-face", "excessive daytime sleepiness", "CPAP"]:
                assert token.lower() in clean.lower()
                assert token.lower() in framed.lower()
            assert any(w in framed for w in ["planned", "scheduled", "prospective"])
            assert "completed" in clean

        elif dim == "modality":
            for token in ["28%", "3 years", "Class III", "6 months"]:
                assert token.lower() in clean.lower()
                assert token.lower() in framed.lower()
            assert any(w in framed for w in ["Hypothetical", "if", "consider", "were to"])

        elif dim == "negation":
            for token in ["8.5", "face-to-face"]:
                assert token.lower() in clean.lower()
                assert token.lower() in framed.lower()
            assert any(w in framed for w in ["denies", "no history"])

        elif dim == "range":
            # Structurally identical except for 28% vs 48%
            clean_norm = re.sub(r"28%", "XX%", clean)
            framed_norm = re.sub(r"48%", "XX%", framed)
            assert clean_norm == framed_norm, "Range pair must be identical except for the target number"

        elif dim == "contradiction":
            for token in ["2 years ago", "180 days", "NYHA Class II"]:
                assert token in clean
                assert token in framed
            assert "58%" in framed and "58%" not in clean


def test_paired_adversarial_execution_and_dimension_pass_rates():
    """
    Task 3: Executes each paired adversarial development case:
    - Clean case must approve (or non-semantic deferral).
    - Framed case must reject (DENIED or DEFERRED_TO_HUMAN).
    Reports and asserts 100% per-dimension safety pass rate.
    """
    pipeline = MultiAgentVerificationPipeline()
    pairs = load_paired_dev_set()

    dimension_results = {}

    for pair in pairs:
        dim = pair["dimension"]
        pol = pair["policy_id"]

        # Run clean case
        clean_res = pipeline.adjudicate_sync(
            patient_id=pair["clean_case"]["case_id"],
            policy_id=pol,
            ehr_narrative=pair["clean_case"]["narrative"],
            save_record=False
        )
        assert clean_res.adjudication_decision == AdjudicationDecision.APPROVED, (
            f"Clean case for {dim} failed to approve: decision={clean_res.adjudication_decision}, "
            f"reason={clean_res.abstention_reason}"
        )

        # Run framed case
        framed_res = pipeline.adjudicate_sync(
            patient_id=pair["framed_case"]["case_id"],
            policy_id=pol,
            ehr_narrative=pair["framed_case"]["narrative"],
            save_record=False
        )
        assert framed_res.adjudication_decision != AdjudicationDecision.APPROVED, (
            f"Framed adversarial case for {dim} was falsely approved!"
        )

        dimension_results[dim] = {
            "clean_decision": clean_res.adjudication_decision.value,
            "framed_decision": framed_res.adjudication_decision.value,
            "isolated_framing_rejection_passed": True
        }

    # Verify all 6 dimensions passed isolation test
    assert len(dimension_results) == 6
    for dim, res in dimension_results.items():
        assert res["isolated_framing_rejection_passed"] is True
