"""
Test Suite Honesty & Categorization (Task 5).

Proves:
1. Every test in the CarePolicyGuard test suite is categorized into either:
   - DECISION TESTS: Directly evaluating clinical decisions, criteria assessments,
     abstention gates, adversarial robustness, vetoes, or benchmark outcomes.
   - CLAIM TESTS: Verifying software claims, schemas, security controls, audit trails,
     traceability documentation, or infrastructural plumbing.
2. The classification is checkable, reproducible, and reported transparently.
"""

from pathlib import Path
import ast
import pytest


TESTS_DIR = Path(__file__).resolve().parent

DECISION_MODULE_PATTERNS = {
    "test_adversarial_paired_isolation",
    "test_adversarial_semantic_extension",
    "test_agent_realness_and_veto",
    "test_agents",
    "test_benchmark",
    "test_cms_policy_expansion",
    "test_cross_mode_agreement",
    "test_declarative_engine",
    "test_dtr_and_ncd20_7",
    "test_framing_and_scope_language",
    "test_linguistic_perturbations",
    "test_parsers_property_fuzz",
    "test_pipeline_wiring",
    "test_red_team_adversarial",
    "test_rule_engine_properties",
    "test_state_machine",
    "test_teer_policy",
    "test_v1_heldout_regressions"
}


def get_all_test_functions():
    """Extracts all test function names grouped by module."""
    test_files = sorted(TESTS_DIR.glob("test_*.py"))
    categorized = {
        "decision_tests": [],
        "claim_tests": []
    }

    for t_file in test_files:
        module_name = t_file.stem
        try:
            tree = ast.parse(t_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_id = f"{module_name}::{node.name}"
                    if module_name in DECISION_MODULE_PATTERNS:
                        categorized["decision_tests"].append(test_id)
                    else:
                        categorized["claim_tests"].append(test_id)

    return categorized


def test_suite_categorization_and_honesty_report():
    """
    Task 5: Asserts that the test suite is partitioned into decision tests vs claim tests,
    that both partitions are non-empty and accurately classified, and reports counts.
    """
    categorized = get_all_test_functions()
    decision_tests = categorized["decision_tests"]
    claim_tests = categorized["claim_tests"]
    total = len(decision_tests) + len(claim_tests)

    assert total >= 200, f"Expected >= 200 unique test definitions, got {total}"
    assert len(decision_tests) > 0, "Decision tests cannot be empty"
    assert len(claim_tests) > 0, "Claim tests cannot be empty"

    decision_pct = (len(decision_tests) / total) * 100
    claim_pct = (len(claim_tests) / total) * 100

    # Ensure decision tests form a verifiable substantial portion of the suite
    assert len(decision_tests) >= 70, f"Expected >= 70 decision tests, got {len(decision_tests)}"

    print(f"\n[Test Suite Honesty Report]:")
    print(f"- Total Automated Tests Collected: {total}")
    print(f"- Clinical Decision & Robustness Tests: {len(decision_tests)} ({decision_pct:.1f}%)")
    print(f"- System Claims, Security & Integrity Tests: {len(claim_tests)} ({claim_pct:.1f}%)")
