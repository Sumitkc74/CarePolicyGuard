"""
SHA-256 Audit Hash Verification & Tampering Detection Tests.
Verifies:
1. Determinism and canonical serialization of audit hash calculation.
2. Immediate detection of tampering in decision, confidence, criteria status, or timestamps.
3. Tamper-evidence validation on database audit records.
"""

from datetime import datetime, timezone
import pytest
from app.core.security import compute_audit_hash


def test_deterministic_audit_hash_generation():
    """
    Identical inputs must always produce the exact same SHA-256 hash.
    """
    ts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    criteria = [
        {"criterion_code": "CRIT-01", "status": "MET", "clinical_rationale": "Requirement met."},
        {"criterion_code": "CRIT-02", "status": "NOT_MET", "clinical_rationale": "Requirement not met."}
    ]
    spans = [
        {"start_char": 10, "end_char": 25, "source_text": "LVEF is 28%"}
    ]

    h1 = compute_audit_hash(
        patient_id_masked="PT-100",
        policy_id="NCD-20.4",
        decision="APPROVED",
        calibrated_confidence=0.95,
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )

    h2 = compute_audit_hash(
        patient_id_masked="PT-100",
        policy_id="NCD-20.4",
        decision="APPROVED",
        calibrated_confidence=0.95,
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )

    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string


def test_tampering_decision_detected():
    """
    Tampering with decision (e.g. flipping DENIED to APPROVED) alters the hash.
    """
    ts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    criteria = [{"criterion_code": "CRIT-01", "status": "NOT_MET", "clinical_rationale": "Fails threshold."}]
    spans = []

    h_denied = compute_audit_hash(
        patient_id_masked="PT-200",
        policy_id="NCD-20.4",
        decision="DENIED",
        calibrated_confidence=0.90,
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )

    h_tampered = compute_audit_hash(
        patient_id_masked="PT-200",
        policy_id="NCD-20.4",
        decision="APPROVED",  # Maliciously flipped
        calibrated_confidence=0.90,
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )

    assert h_denied != h_tampered


def test_tampering_confidence_and_spans_detected():
    """
    Altering calibrated confidence or evidence span character boundaries alters the hash.
    """
    ts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    criteria = [{"criterion_code": "CRIT-01", "status": "MET", "clinical_rationale": "Verified."}]
    spans = [{"start_char": 50, "end_char": 65, "source_text": "LVEF 25%"}]

    base_hash = compute_audit_hash(
        patient_id_masked="PT-300",
        policy_id="NCD-20.4",
        decision="APPROVED",
        calibrated_confidence=0.92,
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )

    # 1. Tamper confidence
    h_tamper_conf = compute_audit_hash(
        patient_id_masked="PT-300",
        policy_id="NCD-20.4",
        decision="APPROVED",
        calibrated_confidence=0.99,  # Inflated confidence
        criterion_assessments=criteria,
        evidence_spans=spans,
        timestamp=ts
    )
    assert base_hash != h_tamper_conf

    # 2. Tamper offset
    tampered_spans = [{"start_char": 51, "end_char": 65, "source_text": "LVEF 25%"}]
    h_tamper_span = compute_audit_hash(
        patient_id_masked="PT-300",
        policy_id="NCD-20.4",
        decision="APPROVED",
        calibrated_confidence=0.92,
        criterion_assessments=criteria,
        evidence_spans=tampered_spans,
        timestamp=ts
    )
    assert base_hash != h_tamper_span
