"""Tests for Prompt v90: In-place v89 report corrections, v88 report fixes, and full suite verification.

Ensures that:
(i) docs/agentic_v89_delivery_report.md cites the correct delivery head (caca385)
    with CI run 45481946912, and d06bb93 appears only as intermediate docs commit.
(ii) docs/agentic_v88_delivery_report.md contains NO occurrence of lookups_rejected_by_egress
    and states the correct test module count (95 test modules).
(iii) docs/agentic_v89_delivery_report.md states the correct full-suite total (528 collected
    at caca385) with the passed/failed/skipped breakdown.
(iv) All v89 tests and core safety/concession invariants pass unchanged.
"""

import subprocess
from pathlib import Path

V88_REPORT_PATH = Path("docs/agentic_v88_delivery_report.md")
V89_REPORT_PATH = Path("docs/agentic_v89_delivery_report.md")


def test_v90_v89_report_cites_correct_delivery_head() -> None:
    """Assert that docs/agentic_v89_delivery_report.md cites delivery head caca385 with CI run 45481946912."""
    assert V89_REPORT_PATH.exists(), f"Missing report: {V89_REPORT_PATH}"
    report_text = V89_REPORT_PATH.read_text(encoding="utf-8")

    full_delivery_head = "caca385311fd202101f2859e4b8fece655501a32"
    ci_run_id = "45481946912"

    assert full_delivery_head in report_text, f"Report must cite full delivery head {full_delivery_head}"
    assert ci_run_id in report_text, f"Report must cite CI run {ci_run_id}"

    # Verify d06bb93 is cited only as intermediate docs commit, NOT delivery head
    assert "Delivery Head Commit: `d06bb93" not in report_text
    assert "Delivery Head Commit**: `d06bb93" not in report_text
    assert "Intermediate Docs Commit**: `d06bb93" in report_text or "Intermediate Docs Commit: `d06bb93" in report_text


def test_v90_v88_report_telemetry_and_file_counts() -> None:
    """Assert docs/agentic_v88_delivery_report.md has no lookups_rejected_by_egress and states correct test file count."""
    assert V88_REPORT_PATH.exists(), f"Missing report: {V88_REPORT_PATH}"
    report_text = V88_REPORT_PATH.read_text(encoding="utf-8")

    # (a) No fabricated telemetry key
    assert "lookups_rejected_by_egress" not in report_text, (
        "docs/agentic_v88_delivery_report.md must not contain non-existent key 'lookups_rejected_by_egress'"
    )

    # (b) Count test modules in repo at caca385 baseline
    # Verify using git ls-tree if git is available, else fallback to Path
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "caca385", "--", "tests/"],
            capture_output=True,
            text=True,
            check=True,
        )
        test_files = [
            line.strip()
            for line in proc.stdout.splitlines()
            if line.strip().startswith("tests/test_") and line.strip().endswith(".py")
        ]
        test_module_count = len(test_files)
    except (subprocess.SubprocessError, OSError):
        # If git revision query fails, count existing test files excluding v90 test
        test_files = [str(p) for p in Path("tests").glob("test_*.py") if p.name != "test_v90_report_corrections.py"]
        test_module_count = len(test_files)

    assert test_module_count == 95, f"Expected 95 baseline test modules at caca385, found: {test_module_count}"
    assert "95 test modules" in report_text, "docs/agentic_v88_delivery_report.md must state 95 test modules"


def test_v90_v89_report_states_correct_full_suite_total() -> None:
    """Assert docs/agentic_v89_delivery_report.md states 528 collected tests at caca385 with split."""
    assert V89_REPORT_PATH.exists(), f"Missing report: {V89_REPORT_PATH}"
    report_text = V89_REPORT_PATH.read_text(encoding="utf-8")

    assert "528 collected tests" in report_text, "Report must state 528 collected tests at caca385"
    assert "passed" in report_text.lower()
    assert "skipped" in report_text.lower()
    assert "failed" in report_text.lower()


def test_v90_prior_tests_and_invariants_pass() -> None:
    """Verify that all v89 tests, v84 concession invariant, and v87 advocacy rejection pass unchanged."""
    from tests.test_v84_concession_defense import (
        test_v84_valid_objection_still_concedes as run_v84_concede,
    )
    from tests.test_v87_umls_integration import (
        test_v87_judge_still_rejects_advocacy_in_gold_denied_case as run_v87_advocacy_rejection,
    )
    from tests.test_v89_report_corrections import (
        test_v89_invariance_and_safety_checks_pass as run_v89_invariance,
    )
    from tests.test_v89_report_corrections import (
        test_v89_v88_report_cites_correct_delivery_head as run_v89_delivery_head,
    )
    from tests.test_v89_report_corrections import (
        test_v89_v88_report_contains_no_fabricated_identifiers as run_v89_fabricated,
    )
    from tests.test_v89_report_corrections import (
        test_v89_v88_report_test_table_names_only_real_files as run_v89_test_table,
    )

    # 1. v89 report tests
    run_v89_test_table()
    run_v89_fabricated()
    run_v89_delivery_head()
    run_v89_invariance()

    # 2. Concession invariant (v84 test iii)
    run_v84_concede()

    # 3. Advocacy rejection in gold-DENIED case (v87 test vii)
    run_v87_advocacy_rejection()
