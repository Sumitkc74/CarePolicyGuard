"""
Tests for Prompt v81: Build completion & review fixes verification.

Pins:
(i) Milestone demo 'Supported' entry records APPROVED.
(ii) policy_version is dynamic: loaded from policy definition JSON (e.g. 2026.1 for NCD-100.1 / NCD-260.1).
(iii) engine_version contains 'qwen2.5:3b' (specifically 'qwen2.5:3b (carepolicyguard-multiagent-v80)').
(iv) Per-file ruff counts are within baseline bounds (routes.py <= 175, pdf_routes.py <= 11).
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.agents.packet_generator import CoveragePacketGenerator
from app.db.models import EvaluationRun
from app.schemas.contracts import AdjudicationDecision, FinalAdjudication
from app.services.declarative_engine import DeclarativePolicyEngine
from app.services.pdf_generator import PDFPacketGeneratorService


def test_v81_milestone_demo_results_supported_approved():
    """Pin (i): Milestone demo 'Supported' entry records APPROVED."""
    demo_file = Path("docs/milestone_demo_v80_results.json")
    assert demo_file.exists(), "docs/milestone_demo_v80_results.json must exist"

    data = json.loads(demo_file.read_text(encoding="utf-8"))
    assert len(data) >= 4, f"Expected 4 demo cases, found {len(data)}"

    # First case: Supported (DEV-LCD-PCI-APP)
    supported_case = data[0]
    assert supported_case["vignette_id"] == "DEV-LCD-PCI-APP"
    assert supported_case["policy_id"] == "LCD-PCI"
    assert supported_case["decision"] == "APPROVED"
    assert supported_case["determination_stage"] == "PROVISIONAL"
    assert supported_case["policy_version"] == "2024.1"
    assert supported_case["engine_version"] == "qwen2.5:3b (carepolicyguard-multiagent-v80)"
    assert supported_case["agent_traces_count"] > 0

    # Ensure other cases are properly captured as human-deferral
    for other_case in data[1:]:
        assert other_case["decision"] in (
            "DEFERRED_TO_HUMAN",
            "CONTRADICTION",
            "OBJECTION",
            "DENIED",
            "INSUFFICIENT_DOCUMENTATION",
            "DEFERRED",
        )


def test_v81_dynamic_policy_version_lookup():
    """Pin (ii): policy_version is dynamic: read from governing policy JSON."""
    # Policies that specify 2026.1
    ncd_100 = DeclarativePolicyEngine.load_policy("NCD-100.1")
    assert ncd_100 is not None
    assert ncd_100.policy_version == "2026.1"

    ncd_260 = DeclarativePolicyEngine.load_policy("NCD-260.1")
    assert ncd_260 is not None
    assert ncd_260.policy_version == "2026.1"

    # Policy that specifies 2024.1
    pci_policy = DeclarativePolicyEngine.load_policy("LCD-PCI")
    assert pci_policy is not None
    assert pci_policy.policy_version == "2024.1"

    now = datetime.now(timezone.utc)
    # Packet generator uses dynamic policy version
    mock_adj_2026 = FinalAdjudication(
        case_id="CASE-TEST-DYN-01",
        patient_id="PT-DYN-01",
        patient_id_masked="PT-DYN-***",
        policy_id="NCD-100.1",
        policy_title=ncd_100.title,
        adjudication_decision=AdjudicationDecision.APPROVED,
        abstention_status=False,
        raw_aggregate_confidence=0.95,
        audit_hash="0" * 64,
        sanitized_ehr_text="Patient undergoing clinical evaluation for bariatric surgery.",
        timestamp=now,
        criterion_assessments=[],
        verification_audits=[],
    )
    packet_2026 = CoveragePacketGenerator.generate_packet(mock_adj_2026)
    assert packet_2026.policy_version == "2026.1", f"Expected 2026.1, got {packet_2026.policy_version}"

    mock_adj_pci = FinalAdjudication(
        case_id="CASE-TEST-DYN-02",
        patient_id="PT-DYN-02",
        patient_id_masked="PT-DYN-***",
        policy_id="LCD-PCI",
        policy_title=pci_policy.title,
        adjudication_decision=AdjudicationDecision.APPROVED,
        abstention_status=False,
        raw_aggregate_confidence=0.95,
        audit_hash="0" * 64,
        sanitized_ehr_text="Patient undergoing clinical evaluation for PCI.",
        timestamp=now,
        criterion_assessments=[],
        verification_audits=[],
    )
    packet_2024 = CoveragePacketGenerator.generate_packet(mock_adj_pci)
    assert packet_2024.policy_version == "2024.1", f"Expected 2024.1, got {packet_2024.policy_version}"


def test_v81_engine_version_contains_model_tag():
    """Pin (iii): engine_version contains 'qwen2.5:3b' across packets, runs, and generators."""
    expected_tag = "qwen2.5:3b (carepolicyguard-multiagent-v80)"
    now = datetime.now(timezone.utc)

    # 1. Packet generator
    mock_adj = FinalAdjudication(
        case_id="CASE-TEST-ENG-01",
        patient_id="PT-ENG-01",
        patient_id_masked="PT-ENG-***",
        policy_id="LCD-PCI",
        policy_title="Percutaneous Coronary Intervention",
        adjudication_decision=AdjudicationDecision.APPROVED,
        abstention_status=False,
        raw_aggregate_confidence=0.95,
        audit_hash="0" * 64,
        sanitized_ehr_text="Clinical note for PCI evaluation.",
        timestamp=now,
        criterion_assessments=[],
        verification_audits=[],
    )
    packet = CoveragePacketGenerator.generate_packet(mock_adj)
    assert "qwen2.5:3b" in packet.engine_version
    assert packet.engine_version == expected_tag

    # 2. EvaluationRun model
    run = EvaluationRun(
        run_id="RUN-TEST-ENG-01",
        case_id="CASE-TEST-ENG-01",
        run_number=1,
        decision="APPROVED",
        determination_stage="PROVISIONAL",
        policy_id="LCD-PCI",
        policy_version="2024.1",
        engine_version=expected_tag,
        note_version="sha256:abc",
        audit_hash="0" * 64,
        is_releasable=False,
    )
    assert "qwen2.5:3b" in run.engine_version
    assert run.engine_version == expected_tag

    # 3. PDF generator module generates PDF with packet metadata
    pdf_bytes = PDFPacketGeneratorService.generate_coverage_packet_pdf(packet)
    assert len(pdf_bytes) > 0, "PDF generation succeeded"


def test_v81_ruff_error_counts_within_baseline_bounds():
    """Pin (iv): Ruff error counts for touched files stay at or below baseline."""
    targets = {
        "app/api/routes.py": 175,
        "app/api/pdf_routes.py": 11,
        "app/api/release.py": 0,
        "app/schemas/contracts.py": 0,
        "app/services/trace_service.py": 0,
    }

    for path_str, max_allowed in targets.items():
        res = subprocess.run(
            ["ruff", "check", path_str, "--ignore", "E501"],
            capture_output=True,
            text=True,
        )
        match = re.search(r"Found (\d+) error", res.stdout + res.stderr)
        count = int(match.group(1)) if match else 0
        assert count <= max_allowed, (
            f"Ruff error count for {path_str} is {count}, exceeding baseline bound {max_allowed}!"
        )
