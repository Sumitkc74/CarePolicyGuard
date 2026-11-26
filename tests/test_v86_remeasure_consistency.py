"""
Consistency guard test suite for Suggestion Prompt v86 Re-measurement at head 738c729.

Validates that:
(i)   test_v86_remeasure_git_head_is_738c729:
      metadata['git_head'] == '738c729' and metadata['git_head_full'] == '738c72952bd8d6e715e3127f2bb879e57a71ea04'.
(ii)  test_v86_remeasure_transcript_decision_consistency:
      For every agentic case in the fresh run JSON, a HALT in the message board transcript
      implies actual_decision == 'DEFERRED_TO_HUMAN', and actual_decision == 'APPROVED'
      implies every non-exclusion criterion is MET and no HALT appears in the transcript.
(iii) test_v86_remeasure_target_cases_consistent:
      For DEV-LCD-KYPHO-APP, DEV-NCD-CATARACT-APP, and DEV-NCD-PET-ONC-APP, the decision,
      criterion statuses, debated outcomes, and transcript spans are mutually consistent.
      PET-ONC shows CRIT-PTONC-01 MET + DEFENDED and adjudicates to APPROVED.
      Cases with INSUFFICIENT_EVIDENCE criteria defer cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RUN_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "benchmarks" / "agentic_v86_three_mode_run.json"


@pytest.fixture(scope="module")
def run_data() -> dict:
    assert RUN_JSON_PATH.exists(), f"Benchmark run JSON not found at {RUN_JSON_PATH}"
    with open(RUN_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_v86_remeasure_git_head_is_738c729(run_data: dict) -> None:
    """Test (i): Provenance in metadata must record committed head 738c729."""
    meta = run_data.get("metadata", {})
    git_head = meta.get("git_head")
    git_head_full = meta.get("git_head_full")
    assert git_head == "738c729", f"Expected git_head '738c729', got '{git_head}'"
    assert git_head_full == "738c72952bd8d6e715e3127f2bb879e57a71ea04", (
        f"Expected git_head_full '738c72952bd8d6e715e3127f2bb879e57a71ea04', got '{git_head_full}'"
    )


def test_v86_remeasure_transcript_decision_consistency(run_data: dict) -> None:
    """Test (ii): HALT <=> DEFERRED, and APPROVED => all mandatory MET with no HALT."""
    cases = run_data.get("agentic_run", {}).get("cases", [])
    assert len(cases) == 84, f"Expected 84 cases, found {len(cases)}"

    inconsistencies = []
    for c in cases:
        vid = c.get("vignette_id")
        actual_decision = c.get("actual_decision")
        transcript = c.get("message_board_transcript", "")
        crit_assessments = c.get("criterion_assessments", [])
        abstention_halt = c.get("abstention_gate_halt", False)
        budget_halt = c.get("budget_halt", False)
        wall_sec = c.get("case_wall_time_seconds", 0.0)

        # Check for halts in transcript
        has_abstention_halt = "halt_type=ABSTENTION_GATE" in transcript
        has_budget_halt = "halt_type=OPERATIONAL_BUDGET" in transcript

        if has_abstention_halt or has_budget_halt:
            if actual_decision != "DEFERRED_TO_HUMAN":
                inconsistencies.append(
                    f"{vid}: Transcript has HALT but actual_decision={actual_decision}"
                )
            if has_abstention_halt and not abstention_halt:
                inconsistencies.append(
                    f"{vid}: Transcript has ABSTENTION_GATE halt but abstention_gate_halt is False"
                )
            if has_budget_halt and not budget_halt:
                inconsistencies.append(
                    f"{vid}: Transcript has OPERATIONAL_BUDGET halt but budget_halt is False"
                )
            if has_budget_halt and wall_sec < 60.0:
                inconsistencies.append(
                    f"{vid}: OPERATIONAL_BUDGET halt but wall time {wall_sec:.2f} < 60.0s"
                )

        if actual_decision == "APPROVED":
            if has_abstention_halt or has_budget_halt:
                inconsistencies.append(
                    f"{vid}: APPROVED decision but transcript contains HALT"
                )
            for ca in crit_assessments:
                code = ca.get("code") or ca.get("criterion_code")
                status = ca.get("status")
                is_excl = "EXCL" in str(code).upper() or ca.get("is_exclusion", False)
                if not is_excl and status != "MET":
                    inconsistencies.append(
                        f"{vid}: APPROVED decision but non-exclusion criterion {code} has status {status}"
                    )

    assert not inconsistencies, f"Found {len(inconsistencies)} inconsistencies: {inconsistencies}"


def test_v86_remeasure_target_cases_consistent(run_data: dict) -> None:
    """Test (iii): Target cases KYPHO, CATARACT, and PET-ONC are mutually consistent."""
    cases = {c["vignette_id"]: c for c in run_data.get("agentic_run", {}).get("cases", [])}

    # 1. DEV-NCD-PET-ONC-APP (Genuine Rescue)
    pet = cases.get("DEV-NCD-PET-ONC-APP")
    assert pet is not None, "DEV-NCD-PET-ONC-APP missing from run"
    assert pet.get("actual_decision") == "APPROVED"
    assert pet.get("debated_criteria_outcomes", {}).get("CRIT-PTONC-01") == "DEFENDED"
    pet_t = pet.get("message_board_transcript", "")
    assert "267:354" in pet_t or "[267:354]" in pet_t or "esophageal adenocarcinoma" in pet_t
    for ca in pet.get("criterion_assessments", []):
        code = ca.get("code") or ca.get("criterion_code")
        if not ("EXCL" in str(code).upper() or ca.get("is_exclusion", False)):
            assert ca.get("status") == "MET", f"PET-ONC {code} expected MET, got {ca.get('status')}"

    # 2. DEV-LCD-KYPHO-APP (Budget-halted deferral)
    kypho = cases.get("DEV-LCD-KYPHO-APP")
    assert kypho is not None, "DEV-LCD-KYPHO-APP missing from run"
    assert kypho.get("actual_decision") == "DEFERRED_TO_HUMAN"
    assert kypho.get("budget_halt") is True
    assert kypho.get("case_wall_time_seconds", 0.0) >= 60.0
    assert kypho.get("debated_criteria_outcomes", {}).get("CRIT-KYPHO-01") == "DEFENDED"
    kypho_crit2 = next(
        ca for ca in kypho.get("criterion_assessments", [])
        if (ca.get("code") or ca.get("criterion_code")) == "CRIT-KYPHO-02"
    )
    assert kypho_crit2.get("status") == "INSUFFICIENT_EVIDENCE"

    # 3. DEV-NCD-CATARACT-APP (Budget-halted deferral with located span)
    cat = cases.get("DEV-NCD-CATARACT-APP")
    assert cat is not None, "DEV-NCD-CATARACT-APP missing from run"
    assert cat.get("actual_decision") == "DEFERRED_TO_HUMAN"
    assert cat.get("budget_halt") is True
    assert cat.get("case_wall_time_seconds", 0.0) >= 60.0
    assert cat.get("debated_criteria_outcomes", {}).get("CRIT-CAT-01") == "DEFENDED"
    cat_t = cat.get("message_board_transcript", "")
    assert "379:460" in cat_t or "[379:460]" in cat_t or "20/60 in the right eye" in cat_t
    cat_crit2 = next(
        ca for ca in cat.get("criterion_assessments", [])
        if (ca.get("code") or ca.get("criterion_code")) == "CRIT-CAT-02"
    )
    assert cat_crit2.get("status") == "INSUFFICIENT_EVIDENCE"
