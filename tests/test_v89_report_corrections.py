"""Tests for Prompt v89: In-place v88 report corrections and full suite verification.

Ensures that docs/agentic_v88_delivery_report.md contains only verified filenames,
no fabricated identifiers or functions, cites the true delivery head (f90decf),
and that all core safety and adjudication invariants remain strictly preserved.
"""

import re
from pathlib import Path

V88_REPORT_PATH = Path("docs/agentic_v88_delivery_report.md")


def test_v89_v88_report_test_table_names_only_real_files() -> None:
    """Verify that every tests/test_*.py file mentioned in v88 report actually exists."""
    assert V88_REPORT_PATH.exists(), f"Missing report: {V88_REPORT_PATH}"
    report_text = V88_REPORT_PATH.read_text(encoding="utf-8")

    # Extract all tests/test_*.py filenames
    referenced_tests = set(re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", report_text))
    assert len(referenced_tests) >= 11, f"Expected at least 11 test files referenced, found: {len(referenced_tests)}"

    for test_file in referenced_tests:
        assert Path(test_file).exists(), f"Report references non-existent test file: {test_file}"

    # Confirm all 11 real delivery test files are explicitly present
    expected_real_delivery_files = [
        "tests/test_v76_release_workflow.py",
        "tests/test_v77_concession_fix.py",
        "tests/test_v78_judge_in_loop.py",
        "tests/test_v79_app_release_fixes.py",
        "tests/test_v80_reviewer_workflow.py",
        "tests/test_v81_build_completion.py",
        "tests/test_v82_build_fixes.py",
        "tests/test_v84_concession_defense.py",
        "tests/test_v85_threshold_revert.py",
        "tests/test_v87_umls_integration.py",
        "tests/test_v88_umls_proof_and_report.py",
    ]
    for rf in expected_real_delivery_files:
        assert rf in report_text, f"Expected real delivery file {rf} missing from report"


def test_v89_v88_report_contains_no_fabricated_identifiers() -> None:
    """Assert that docs/agentic_v88_delivery_report.md contains NO fabricated identifiers or files."""
    assert V88_REPORT_PATH.exists()
    report_text = V88_REPORT_PATH.read_text(encoding="utf-8")

    forbidden_identifiers = [
        "validate_term_for_egress",
        "test_umls_client.py",
        "umls_telemetry",
        "umls_api_configured",
        "test_v76_release_path.py",
        "test_v77_concept_map_wiring.py",
        "test_v78_judge_loop_and_report.py",
        "test_v80_reviewer_ui_smoke.py",
        "test_v83_doc_corrections_and_sbrt_diagnostic.py",
        "test_v84_two_case_rescues.py",
        "test_v85_defense_fixes_and_threshold_revert.py",
    ]

    for identifier in forbidden_identifiers:
        assert identifier not in report_text, f"Found forbidden fabricated identifier/file in report: {identifier}"


def test_v89_v88_report_cites_correct_delivery_head() -> None:
    """Assert that the report cites delivery head f90decf with CI run 45456658216."""
    assert V88_REPORT_PATH.exists()
    report_text = V88_REPORT_PATH.read_text(encoding="utf-8")

    full_delivery_head = "f90decfd7923ef7ccaac1b5602a46f2af7570fb0"
    ci_run_id = "45456658216"

    assert full_delivery_head in report_text, f"Report must cite full delivery head {full_delivery_head}"
    assert ci_run_id in report_text, f"Report must cite CI run {ci_run_id}"

    # Verify 33c0cbd is cited as intermediate docs commit, NOT delivery head
    assert "Delivery Head Commit: `33c0cbd" not in report_text
    assert "Delivery Head Commit**: `33c0cbd" not in report_text
    assert "Intermediate Docs Commit**: `33c0cbd" in report_text


def test_v89_invariance_and_safety_checks_pass() -> None:
    """Verify that prior safety and concession invariants pass without regressions."""
    from tests.test_v84_concession_defense import (
        test_v84_valid_objection_still_concedes as run_v84_concede,
    )
    from tests.test_v87_umls_integration import (
        test_v87_judge_still_rejects_advocacy_in_gold_denied_case as run_v87_advocacy_rejection,
    )
    from tests.test_v88_umls_proof_and_report import (
        test_v88_target_case_defenses_and_advocacy_rejection_preserved as run_v88_target,
    )
    from tests.test_v88_umls_proof_and_report import (
        test_v88_telemetry_recording as run_v88_telemetry,
    )
    from tests.test_v88_umls_proof_and_report import (
        test_v88_tightened_egress_boundary as run_v88_egress,
    )
    from tests.test_v88_umls_proof_and_report import (
        test_v88_v87_report_corrections_present as run_v88_report,
    )

    # 1. v88 report corrections & egress tightening
    run_v88_egress()
    run_v88_telemetry()
    run_v88_report()
    run_v88_target()

    # 2. Concession invariant (v84 test iii)
    run_v84_concede()

    # 3. Advocacy rejection in gold-DENIED case (v87 test vii)
    run_v87_advocacy_rejection()
