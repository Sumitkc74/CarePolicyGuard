import pytest
from app.schemas.contracts import FinalAdjudication, AdjudicationDecision, DeterminationStatus, AuditTrailEvent
from app.agents.pipeline import MultiAgentVerificationPipeline


def test_scope_and_signoff_metadata_in_final_adjudication():
    """
    Task 1: Tests that scope, disclaimer, and human sign-off gate fields
    are explicitly present in FinalAdjudication response metadata.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "CARDIOLOGY CONSULTATION\n"
        "Patient with ischemic cardiomyopathy. LVEF 25% on TTE.\n"
        "On GDMT for 6 months with carvedilol and lisinopril. NYHA Class II.\n"
        "Remote MI 3 years ago. No acute cardiogenic shock."
    )
    res = pipeline.adjudicate_sync("PT-TEST-SCOPE", "NCD-20.4", ehr, save_record=False)

    # Scope statement must be present
    assert hasattr(res, "determination_scope")
    assert "curated CMS" in res.determination_scope
    assert "plan-specific" in res.determination_scope or "eligibility" in res.determination_scope

    # Human sign-off gate must be present and default to PENDING_CLINICAL_SIGN_OFF
    assert hasattr(res, "human_sign_off_status")
    assert res.human_sign_off_status == "PENDING_CLINICAL_SIGN_OFF"

    # Plain-language disclaimer must be present
    assert hasattr(res, "plain_language_disclaimer")
    assert "pre-check" in res.plain_language_disclaimer.lower() or "licensed clinical professional" in res.plain_language_disclaimer.lower()

    # Audit seal must be labeled as tamper-evident seal, not proof of correctness
    assert hasattr(res, "audit_hash_type")
    assert res.audit_hash_type == "tamper_evident_integrity_seal"


def test_audit_trail_correctness_labeling_in_schemas():
    """
    Task 1: Tests that AuditTrailEvent explicitly certifies post-creation
    record integrity and deterministic reproducibility, NOT clinical correctness.
    """
    event = AuditTrailEvent(
        event_id="EVT-001",
        timestamp="2026-11-03T00:00:00Z",
        event_type="ADJUDICATION",
        case_id="CASE-12345",
        patient_id_masked="PT-***",
        actor="SystemEngine",
        actor_role="AutomatedPipeline",
        action_details="Adjudication executed",
        audit_hash="a" * 64
    )
    assert hasattr(event, "audit_seal_certifies")
    assert "tamper_evident" in event.audit_seal_certifies
    assert "correctness" not in event.audit_seal_certifies or "not clinical correctness" in event.audit_seal_certifies


def test_scope_and_signoff_in_docs_and_ui():
    """
    Task 1: Tests that plain-language scope, sign-off gate, and audit integrity
    language are present in README.md and UI files.
    """
    with open("README.md", "r", encoding="utf-8") as f:
        readme = f.read()

    assert "Scope & Human Sign-Off Gate Notice" in readme
    assert "not altered after creation" in readme or "tamper-evident" in readme
    assert "Sufficiency Scores vs Probability" in readme

    with open("app/static/index.html", "r", encoding="utf-8") as f:
        index_html = f.read()

    assert "determination-scope-banner" in index_html
    assert "PENDING CLINICAL SIGN-OFF" in index_html
    assert "Tamper-evident chain-of-custody seals" in index_html

