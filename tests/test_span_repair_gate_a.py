"""
Unit tests for deterministic span-repair in Gate A (Task 2).
Verifies:
1. Paraphrase-class failures differing in casing/punctuation (e.g. ACDF case) are repaired to verbatim note span.
2. Hallucinated claims still fail Gate A.
3. Claims matching a different span with different clinical content do not get repaired into a pass.
4. Exactly 7 of the 26 v28 paraphrase failures are recovered by case/punctuation repair, with 0 hallucinations recovered.
"""

import json
from pathlib import Path
import pytest

from app.agents.llm_proposer import LLMProposalAgent, LLMProposedSpan

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_span_repair_paraphrase_acdf_recovers_exact_span():
    """
    ACDF case: LLM claimed 'conservative management tried for only 1 week' (lowercase 'c', no period).
    Note contains 'Conservative management tried for only 1 week.'
    Span repair must locate exact offsets [s:e], set claimed_text to the verbatim note slice, and pass Gate A.
    """
    note = (
        "SUBJECTIVE: 44-year-old presenting with generalized dull ache across posterior neck. "
        "Patient reports neck pain only for 10 days. No radiation into upper extremities. "
        "Conservative management tried for only 1 week."
    )
    crit = {
        "criterion_code": "CRIT-ACDF-02",
        "name": "Conservative Therapy Trial Failure (>= 6 Weeks)",
        "description": "Trial and failure of >= 6 weeks of conservative therapy.",
        "criterion_type": "TEMPORAL_DURATION",
        "is_exclusion": False,
    }

    claimed_text = "conservative management tried for only 1 week"

    # Direct locate check
    s, e = LLMProposalAgent.locate_claimed_span(note, claimed_text, allow_repair=True)
    assert s != -1 and e != -1
    assert note[s:e] == "Conservative management tried for only 1 week"

    # Gate evaluation check
    prop = LLMProposedSpan(
        criterion_code="CRIT-ACDF-02",
        proposed_status="NOT_MET",
        claimed_text=claimed_text,
        char_start=0,
        char_end=0,
        rationale="Only 1 week tried",
    )

    res = LLMProposalAgent.evaluate_proposal_through_gates(
        proposal=prop,
        sanitized_ehr=note,
        criterion=crit,
    )

    # Must pass Gate A exact slice check (res.failing_gate != "GATE_A_EXACT_SLICE")
    assert res.failing_gate != "GATE_A_EXACT_SLICE"
    assert prop.claimed_text == "Conservative management tried for only 1 week"
    assert note[prop.char_start:prop.char_end] == prop.claimed_text


def test_span_repair_hallucination_fails_gate_a():
    """
    Hallucinated claim (e.g. copied criterion title absent from note) must still fail Gate A.
    """
    note = "Patient has severe knee pain and mild joint space narrowing."
    crit = {
        "criterion_code": "CRIT-ESI-02",
        "name": "Conservative Therapy Trial Failure (>= 4 Weeks)",
        "description": "Trial and failure of >= 4 weeks.",
        "criterion_type": "FINDING_PRESENCE",
        "is_exclusion": False,
    }

    hallucinated_text = (
        "Trial and failure of >= 4 weeks of non-invasive conservative treatment "
        "(medications, physical therapy, activity modification)."
    )

    s, e = LLMProposalAgent.locate_claimed_span(note, hallucinated_text, allow_repair=True)
    assert s == -1 and e == -1

    prop = LLMProposedSpan(
        criterion_code="CRIT-ESI-02",
        proposed_status="MET",
        claimed_text=hallucinated_text,
        char_start=0,
        char_end=0,
        rationale="Copied from prompt",
    )

    res = LLMProposalAgent.evaluate_proposal_through_gates(
        proposal=prop,
        sanitized_ehr=note,
        criterion=crit,
    )

    assert not res.passed
    assert res.failing_gate == "GATE_A_EXACT_SLICE"
    assert "Hallucinated evidence" in (res.rejection_reason or "")


def test_span_repair_wrong_content_does_not_pass():
    """
    A claim with different clinical content (e.g., claiming 20/50 in the right eye
    when the note states 20/60 in right eye and 20/50 in left eye) must not pass Gate A.
    """
    note = (
        "OBJECTIVE: Best corrected visual acuity is 20/60 in the right eye and "
        "20/50 in the left eye. Slit-lamp shows nuclear cataract."
    )
    crit = {
        "criterion_code": "CRIT-CAT-01",
        "name": "Visual Acuity",
        "description": "Visual acuity <= 20/50 in operative eye.",
        "criterion_type": "FINDING_PRESENCE",
        "is_exclusion": False,
    }

    wrong_claim = "20/50 in the right eye"

    s, e = LLMProposalAgent.locate_claimed_span(note, wrong_claim, allow_repair=True)
    assert s == -1 and e == -1

    prop = LLMProposedSpan(
        criterion_code="CRIT-CAT-01",
        proposed_status="MET",
        claimed_text=wrong_claim,
        char_start=0,
        char_end=0,
    )

    res = LLMProposalAgent.evaluate_proposal_through_gates(
        proposal=prop,
        sanitized_ehr=note,
        criterion=crit,
    )

    assert not res.passed
    assert res.failing_gate == "GATE_A_EXACT_SLICE"


def test_span_repair_recovery_rate_on_v28_residual_cases():
    """
    Verifies that on the 26 paraphrase cases and 18 hallucination cases from v28:
    - Exactly 7 paraphrase cases are recovered by case/punctuation repair.
    - Zero hallucination cases are recovered.
    """
    v28_file = ROOT_DIR / "app" / "data" / "benchmarks" / "what_if_residual_failure_classification.json"
    dev_file = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"

    assert v28_file.exists(), f"Missing {v28_file}"
    assert dev_file.exists(), f"Missing {dev_file}"

    with open(v28_file, encoding="utf-8") as f:
        classif = json.load(f)

    with open(dev_file, encoding="utf-8") as f:
        vigs = {v["vignette_id"]: v["ehr_narrative"] for v in json.load(f)}

    cases = classif["task2_gate_a_classification"]["classified_cases"]
    paraphrases = [c for c in cases if c["assigned_class"] == "paraphrase of a real span"]
    hallucinations = [c for c in cases if c["assigned_class"] == "hallucination"]

    assert len(paraphrases) == 26
    assert len(hallucinations) == 18

    recovered_paraphrases = []
    for p in paraphrases:
        vid = p["vignette_id"]
        note = vigs.get(vid, "")
        s, e = LLMProposalAgent.locate_claimed_span(note, p["claimed_text"], allow_repair=True)
        if s != -1:
            recovered_paraphrases.append((vid, p["criterion_code"]))

    recovered_hallucinations = []
    for h in hallucinations:
        vid = h["vignette_id"]
        note = vigs.get(vid, "")
        s, e = LLMProposalAgent.locate_claimed_span(note, h["claimed_text"], allow_repair=True)
        if s != -1:
            recovered_hallucinations.append((vid, h["criterion_code"]))

    assert len(recovered_paraphrases) == 7
    assert len(recovered_hallucinations) == 0

    expected_recovered_vids = {
        "DEV-LCD-ACDF-NEG",
        "DEV-LCD-HALLUX-NEG",
        "DEV-NCD-CARDIAC-REHAB-NEG",
        "DEV-NCD-PACEMAKER-NEG",
        "DEV-NCD-PUMP-NEG",
        "DEV-OPD-RHINO-NEG",
        "DEV-OPD-VEIN-NEG",
    }
    actual_recovered_vids = {vid for vid, _ in recovered_paraphrases}
    assert actual_recovered_vids == expected_recovered_vids
