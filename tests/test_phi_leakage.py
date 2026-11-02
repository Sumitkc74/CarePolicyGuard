"""
HIPAA PHI Leakage Prevention Tests.
Verifies that direct Patient Health Information (PHI) identifiers:
- Patient full names
- Date of birth (DOB)
- Medical record number (MRN)
- Street address
- Social Security Number (SSN)
are strictly sanitized by the pipeline and NEVER leak into:
1. Decision rationales
2. Verified clinical spans
3. Saved audit records
4. Generated coverage packets
"""

import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.security import sanitize_phi
from app.db.session import SessionLocal
from app.db.models import AdjudicationLog


def test_phi_sanitizer_masks_all_identifiers():
    """
    Direct unit test of sanitize_phi with multiple HIPAA identifiers.
    """
    raw_text = (
        "Patient: Alexander Hamilton\n"
        "DOB: 01/11/1757\n"
        "MRN: 17760404\n"
        "Address: 57 Maiden Lane\n"
        "SSN: 987-65-4321\n"
        "Phone: 212-555-1776\n"
        "Diagnosis: Severe ischemic cardiomyopathy with LVEF 25%."
    )

    sanitized = sanitize_phi(raw_text)

    # All identifiers must be masked
    assert "Alexander Hamilton" not in sanitized
    assert "01/11/1757" not in sanitized
    assert "17760404" not in sanitized
    assert "57 Maiden Lane" not in sanitized
    assert "987-65-4321" not in sanitized
    assert "212-555-1776" not in sanitized

    # Clinical findings must be preserved intact
    assert "LVEF 25%" in sanitized
    assert "ischemic cardiomyopathy" in sanitized


def test_pipeline_zero_phi_leakage_in_rationales_and_audit():
    """
    Pass synthetic note with full PHI through end-to-end pipeline.
    Verify zero leakage in adjudications, rationales, spans, and DB records.
    """
    db = SessionLocal()
    pipeline = MultiAgentVerificationPipeline(db=db)

    raw_note = (
        "CLINICAL PROGRESS NOTE\n"
        "Patient Name: Bartholomew Roberts\n"
        "DOB: 03/15/1962\n"
        "MRN: 88471920\n"
        "Address: 1204 Harbor Blvd\n"
        "SSN: 456-78-9012\n\n"
        "HISTORY OF PRESENT ILLNESS:\n"
        "64-year-old male presenting with ischemic cardiomyopathy status post CABG 14 months ago.\n"
        "NYHA Class II symptoms on stable GDMT for 6 months.\n\n"
        "DIAGNOSTICS:\n"
        "Transthoracic echocardiogram confirms LVEF 28% with severe apical hypokinesis.\n\n"
        "ASSESSMENT & PLAN:\n"
        "Patient qualifies for ICD under NCD 20.4."
    )

    result = pipeline.adjudicate_sync(
        patient_id="PT-SAFE-01",
        policy_id="NCD-20.4",
        ehr_narrative=raw_note,
        save_record=True
    )

    # Check AdjudicationResult object
    result_str = str(result.model_dump())
    assert "Bartholomew Roberts" not in result_str
    assert "03/15/1962" not in result_str
    assert "88471920" not in result_str
    assert "1204 Harbor Blvd" not in result_str
    assert "456-78-9012" not in result_str

    # Inspect the saved DB record
    db_record = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == result.case_id).first()
    assert db_record is not None
    db_str = (
        f"{db_record.sanitized_ehr_preview} "
        f"{db_record.criterion_evaluations_json} "
        f"{db_record.evidence_spans_json} "
        f"{db_record.adversarial_audits_json}"
    )

    assert "Bartholomew Roberts" not in db_str
    assert "03/15/1962" not in db_str
    assert "88471920" not in db_str
    assert "1204 Harbor Blvd" not in db_str
    assert "456-78-9012" not in db_str

    db.close()

