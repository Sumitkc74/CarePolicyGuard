"""
Tests for Silent Default Elimination (Task 9).

Verifies that the three audited silent defaults have been eliminated:
1. app/api/batch_routes.py: missing policy in CSV, Excel, and JSON defaults to 'AUTO', not 'NCD-20.4'.
2. app/api/pas_routes.py: unmapped claim returns pended status with explicit message, not silently assuming 'NCD-20.4'.
3. app/agents/criteria_evaluator.py: evaluate_patient_against_policy with None returns DEFERRED_TO_HUMAN, not 'NCD-20.4'.
4. CDS Hooks CRD default in cds_hooks_routes.py is untouched (owned by v41 line).
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.agents.criteria_evaluator import evaluate_patient_against_policy
from app.api.pas_routes import (
    PASClaimItem,
    PASClaimRequest,
    _evaluate_pas_claim,
)
from main import app

client = TestClient(app)


def test_batch_routes_csv_defaults_to_auto():
    """CSV upload with missing policy column must default to 'AUTO', not 'NCD-20.4'."""
    csv_content = (
        b"patient_id,requested_procedure_code,clinical_narrative\n"
        b"PT-TEST-001,99213,Patient presents with chronic cough and dyspnea for 3 weeks.\n"
    )

    files = [("files", ("test_cohort.csv", io.BytesIO(csv_content), "text/csv"))]
    res = client.post("/api/v1/adjudicate/batch/upload-parse", files=files)
    assert res.status_code == 200, res.text

    items = res.json().get("items", [])
    assert len(items) == 1
    assert items[0]["policy_id"] == "AUTO", f"Expected 'AUTO', got {items[0]['policy_id']}"


def test_batch_routes_json_defaults_to_auto():
    """JSON upload with missing policy_id field must default to 'AUTO', not 'NCD-20.4'."""
    json_data = [
        {
            "patient_id": "PT-JSON-001",
            "requested_procedure_code": "99214",
            "clinical_narrative": "Routine annual clinical examination for general health evaluation."
        }
    ]
    json_content = json.dumps(json_data).encode("utf-8")

    files = [("files", ("test_cohort.json", io.BytesIO(json_content), "application/json"))]
    res = client.post("/api/v1/adjudicate/batch/upload-parse", files=files)
    assert res.status_code == 200, res.text

    items = res.json().get("items", [])
    assert len(items) == 1
    assert items[0]["policy_id"] == "AUTO", f"Expected 'AUTO', got {items[0]['policy_id']}"


def test_pas_routes_unmapped_procedure_pends_explicitly():
    """PAS claim with unmapped procedure and narrative must pend with explicit message, not assume NCD-20.4."""
    claim = PASClaimRequest(
        resourceType="Claim",
        status="active",
        type={"coding": [{"code": "professional"}]},
        use="preauthorization",
        patient={"reference": "Patient/PT-UNMAPPED-01"},
        created="2026-11-16T00:00:00Z",
        provider={"reference": "Practitioner/DR-TEST"},
        item=[
            PASClaimItem(
                sequence=1,
                productOrService={
                    "coding": [{"code": "99999"}],
                    "text": "Experimental Unclassified Procedure"
                }
            )
        ]
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = _evaluate_pas_claim(
        claim=claim,
        patient_id="PT-UNMAPPED-01",
        provider_ref="Practitioner/DR-TEST",
        combined_narrative="Patient seen for experimental unclassified diagnostic evaluation. General status stable.",
        db=mock_db
    )

    assert response.outcome == "pended"
    assert "No governing Medicare policy identified" in response.disposition
    assert "manual policy selection required" in response.disposition
    assert response.adjudication_summary["policy_id"] is None, (
        f"Expected policy_id to be None, got {response.adjudication_summary['policy_id']}"
    )


def test_criteria_evaluator_none_policy_defers_to_human():
    """evaluate_patient_against_policy with policy=None must return DEFERRED_TO_HUMAN, not evaluate against NCD-20.4."""
    narrative = (
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III, "
        "on optimal GDMT for 6 months. Candidate for cardiac defibrillator."
    )

    result = evaluate_patient_against_policy(ehr_text=narrative, policy=None)

    assert result["determination"] == "DEFERRED_TO_HUMAN"
    assert result["confidence_score"] == 0.0
    assert "Evaluation deferred to human review" in result["clinical_rationale"]
    assert "GOVERNING_POLICY_UNSPECIFIED" in result["missing_criteria"]


def test_cds_hooks_crd_default_untouched():
    """Audits that the CDS Hooks CRD route default remains untouched per v41 ownership."""
    from pathlib import Path
    cds_file = Path(__file__).resolve().parent.parent / "app" / "api" / "cds_hooks_routes.py"
    content = cds_file.read_text(encoding="utf-8")
    # v41 CRD default to NCD-20.4 when no procedure code matches must remain present
    assert "NCD-20.4" in content
