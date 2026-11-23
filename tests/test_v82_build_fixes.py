"""
Tests for Prompt v82: Build fixes, CI hardening, and concept-map documentation.

Pins:
(i) CI workflow file .github/workflows/ci.yml contains 'pip install ruff' in test-and-coverage job.
(ii) All 11 app-touched files are checked by ruff with individual counts within baseline bounds.
(iii) Demo results JSON (docs/milestone_demo_v80_results.json) records fetch status codes (HTTP 200)
      for traces, runs, and packet for all 4 cases, and none of the deferred cases have empty trace arrays.
(iv) Architectural documentation in scripts/run_milestone_demo.py documents the
     12-committed vs 131-benchmark distinction (preserved in demo script to protect
     critical-file baseline reuse validation in scripts/run_agentic_v59_three_mode_measurement.py).
"""

import inspect
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.core import concept_map


def test_v82_ci_workflow_installs_ruff():
    """Pin (i): CI workflow file .github/workflows/ci.yml contains 'pip install ruff' in test-and-coverage."""
    ci_file = Path(".github/workflows/ci.yml")
    assert ci_file.exists(), ".github/workflows/ci.yml must exist"

    content = ci_file.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    test_job = parsed.get("jobs", {}).get("test-and-coverage", {})
    steps = test_job.get("steps", [])

    install_step = next((s for s in steps if "Install Dependencies" in s.get("name", "")), None)
    assert install_step is not None, "Install Dependencies step not found in test-and-coverage job"
    assert "pip install ruff" in install_step.get("run", ""), (
        "'pip install ruff' must be present in Install Dependencies step of test-and-coverage"
    )


def test_v82_all_eleven_files_within_ruff_bounds():
    """Pin (ii): All 11 app-touched files checked by ruff within baseline bounds."""
    if not shutil.which("ruff"):
        pytest.fail(
            "ruff binary not found on PATH. Install ruff via 'pip install ruff' and ensure it is available on PATH."
        )

    targets = {
        "app/api/deps.py": 17,
        "app/api/pas_routes.py": 35,
        "app/services/deferral_queue.py": 56,
        "app/api/routes.py": 147,
        "app/api/pdf_routes.py": 9,
        "app/api/release.py": 0,
        "app/db/models.py": 4,
        "app/schemas/contracts.py": 0,
        "app/services/trace_service.py": 0,
        "app/services/pdf_generator.py": 15,
        "app/agents/packet_generator.py": 9,
    }

    total_errors = 0
    total_bound = 292

    for path_str, max_allowed in targets.items():
        try:
            res = subprocess.run(
                ["ruff", "check", path_str, "--ignore", "E501"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            pytest.fail(
                "ruff binary not found on PATH. Install ruff via 'pip install ruff' and ensure it is available on PATH."
            )
        match = re.search(r"Found (\d+) error", res.stdout + res.stderr)
        count = int(match.group(1)) if match else 0
        total_errors += count
        assert count <= max_allowed, (
            f"Ruff error count for {path_str} is {count}, exceeding baseline bound {max_allowed}!"
        )

    assert total_errors <= total_bound, (
        f"Total ruff errors across 11 files is {total_errors}, exceeding maximum allowed bound {total_bound}!"
    )


def test_v82_demo_results_json_status_codes_and_traces():
    """Pin (iii): Demo results JSON records fetch status codes (HTTP 200) and non-empty traces."""
    demo_file = Path("docs/milestone_demo_v80_results.json")
    assert demo_file.exists(), "docs/milestone_demo_v80_results.json must exist"

    data = json.loads(demo_file.read_text(encoding="utf-8"))
    assert len(data) >= 4, f"Expected at least 4 demo cases, found {len(data)}"

    for case in data:
        cid = case.get("case_id", "")
        # Check fetch status codes
        assert case.get("trace_fetch_status") == 200, (
            f"Case {cid} trace_fetch_status is {case.get('trace_fetch_status')}, expected 200"
        )
        assert case.get("runs_fetch_status") == 200, (
            f"Case {cid} runs_fetch_status is {case.get('runs_fetch_status')}, expected 200"
        )
        assert case.get("packet_fetch_status") == 200, (
            f"Case {cid} packet_fetch_status is {case.get('packet_fetch_status')}, expected 200"
        )

        # Check packet label
        assert case.get("packet_label") == "Coverage Criteria Evaluation", (
            f"Case {cid} packet_label is {case.get('packet_label')}, expected 'Coverage Criteria Evaluation'"
        )

        # Deferred cases must NOT have empty trace arrays
        if case.get("decision") != "APPROVED":
            assert case.get("agent_traces_count", 0) > 0, (
                f"Deferred case {cid} has 0 agent traces; expected > 0"
            )
            assert case.get("persisted_runs_count", 0) > 0, (
                f"Deferred case {cid} has 0 persisted runs; expected > 0"
            )


def test_v82_concept_map_gap_architectural_docstring():
    """Pin (iv): Architectural documentation documents 12-committed vs 131-benchmark distinction."""
    demo_script = Path("scripts/run_milestone_demo.py")
    assert demo_script.exists(), "scripts/run_milestone_demo.py must exist"
    doc = demo_script.read_text(encoding="utf-8")

    assert "12 committed" in doc, "Documentation must mention 12 committed concepts"
    assert "131" in doc, "Documentation must mention 131-concept map in benchmark harness"
    assert "Gate C" in doc or "unmapped" in doc, "Documentation must explain Gate C / unmapped criteria abstention"
    assert "DEV-LCD-SBRT-APP" in doc or "SBRT" in doc, "Documentation must mention SBRT as an example"
    assert "scripts/run_agentic_v59_three_mode_measurement.py" in doc, (
        "Documentation must reference the actual benchmark measurement harness script scripts/run_agentic_v59_three_mode_measurement.py"
    )
    assert "run_adjudication_benchmark.py" not in doc, (
        "Documentation must NOT reference the nonexistent run_adjudication_benchmark.py"
    )
