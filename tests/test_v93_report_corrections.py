"""
Unit tests for Suggestion Prompt v93:
1. Test viii isolation guard: onboarding flow with tmp queue_path leaves real queue file byte-identical.
2. Validator revert guard: metadata-only policy JSON change (e.g. adding "status") invalidates baseline reuse.
3. Corrected v91 report cites delivery head 45be01e1b036ef91e0951c9028a0c1c46bbc357f.
4. Corrected v91 report contains no fabricated flags, statuses, or nonexistent test names.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.policy_onboarding import PolicyOnboardingAgent
from scripts.run_agentic_v59_three_mode_measurement import (
    verify_baseline_reuse_validity,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_QUEUE_PATH = REPO_ROOT / "app" / "data" / "policy_verification_records.json"
V91_REPORT_PATH = REPO_ROOT / "docs" / "agentic_v91_delivery_report.md"


def test_viii_onboarding_isolation_does_not_mutate_real_queue(tmp_path: Path):
    """
    Task 2(a) guard: Running the test_viii onboarding flow with tmp queue_path
    must leave app/data/policy_verification_records.json byte-identical.
    """
    before_bytes = REAL_QUEUE_PATH.read_bytes()

    doc_text = "The patient must have documented knee instability on clinical exam."
    valid_doc = {
        "mcd_id": "L33318",
        "title": "Knee Orthoses",
        "jurisdiction": "DME MAC",
        "authority": "DME MAC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33318",
        "text": doc_text,
        "indications": [
            {
                "code": "CRIT-KNEE-01",
                "name": "Knee Instability",
                "description": "Documented knee instability.",
                "quoted_passage": doc_text,
                "section": "Indications",
                "paragraph": "Paragraph 1",
                "type": "FINDING_PRESENCE",
                "synonyms": ["knee instability"],
            }
        ],
    }

    queue_file = tmp_path / "queue_v8_guard.json"
    queue_file.write_text("[]", encoding="utf-8")

    agent = PolicyOnboardingAgent(staging_dir=tmp_path, queue_path=queue_file)
    with patch.object(agent, "fetch_mcd_document", return_value=valid_doc):
        result = agent.onboard_policy("L33318", "Knee Orthoses", save_draft=True)

    assert result.status == "DRAFT_ONBOARDED"
    after_bytes = REAL_QUEUE_PATH.read_bytes()
    assert after_bytes == before_bytes, "Real queue file was mutated during isolated onboarding test!"


def test_metadata_only_policy_change_invalidates_baseline_reuse(tmp_path: Path):
    """
    Task 2(b) guard: A metadata-only change (e.g. adding only "status": "ACTIVE")
    to a policy JSON under app/data/policies_extended/ must invalidate baseline reuse.
    """
    run_json = tmp_path / "prev_run.json"
    run_json.write_text(
        json.dumps({"metadata": {"git_head_full": "0000000000000000000000000000000000000000"}}),
        encoding="utf-8",
    )

    def fake_check_output(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "--name-only" in cmd_str:
            return "app/data/policies_extended/LCD-ACDF.json\n"
        if "-U0" in cmd_str:
            return '@@ -132 +132,2 @@\n-  }\n+  },\n+  "status": "ACTIVE"\n'
        return ""

    with patch("scripts.run_agentic_v59_three_mode_measurement.subprocess.run") as mock_run, \
         patch("scripts.run_agentic_v59_three_mode_measurement.subprocess.check_output", side_effect=fake_check_output):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="")
        with pytest.raises(RuntimeError, match="Cannot reuse baselines"):
            verify_baseline_reuse_validity(run_json)


def test_v91_report_cites_delivery_head_45be01e():
    """
    Task 2(c): The corrected v91 delivery report must cite its delivery head 45be01e.
    """
    text = V91_REPORT_PATH.read_text(encoding="utf-8")
    assert "45be01e1b036ef91e0951c9028a0c1c46bbc357f" in text
    assert "45be01e" in text


def test_v91_report_contains_no_fabricated_claims():
    """
    Task 2(c): The corrected v91 report must contain no nonexistent flags, statuses, or test names.
    """
    text = V91_REPORT_PATH.read_text(encoding="utf-8")
    forbidden = [
        "--force-fail-override",
        "--force-partial-activation",
        "VERIFIED_BY_HUMAN",
        "test_iii_agent_reviewer_rejection",
        "test_vi_agent5_synthetic_fallback_removed",
        "absolute adjudication neutrality",
        "zero decision changes",
        "0-commit provenance gap",
        "100% green",
    ]
    for token in forbidden:
        assert token not in text, f"Forbidden fabricated/contradicted string found in v91 report: {token!r}"
