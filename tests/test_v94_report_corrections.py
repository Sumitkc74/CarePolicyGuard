"""
Unit tests for Suggestion Prompt v94:
1. Corrected v93 report cites its delivery head cb8d698e10880e88c3950cf4a4bbe83022029d81.
2. Corrected v93 report does not cite the commit message as the delivery head.
3. Corrected v93 report states both v93 CI runs (45908866701, 45909465875) as failure.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
V93_REPORT_PATH = REPO_ROOT / "docs" / "agentic_v93_delivery_report.md"


def test_v93_report_cites_delivery_head_cb8d698():
    """(i) Corrected v93 report must contain the full delivery head hash cb8d698e10880e88c3950cf4a4bbe83022029d81."""
    text = V93_REPORT_PATH.read_text(encoding="utf-8")
    assert "cb8d698e10880e88c3950cf4a4bbe83022029d81" in text


def test_v93_report_has_no_commit_message_as_head():
    """(ii) Corrected v93 report must not use the commit message as the Delivery Head value."""
    text = V93_REPORT_PATH.read_text(encoding="utf-8")
    forbidden = "**v93 Delivery Head Commit**: `docs(v93): add v93 delivery report`"
    assert forbidden not in text


def test_v93_report_states_both_ci_runs_as_failure():
    """(iii) Corrected v93 report must contain both CI run IDs (45908866701 and 45909465875) and state both as failure."""
    text = V93_REPORT_PATH.read_text(encoding="utf-8")
    assert "45908866701" in text
    assert "45909465875" in text
    for run_id in ("45908866701", "45909465875"):
        matching_lines = [line for line in text.splitlines() if run_id in line]
        assert any("failure" in line.lower() for line in matching_lines), (
            f"Run ID {run_id} must be explicitly stated as failure"
        )
