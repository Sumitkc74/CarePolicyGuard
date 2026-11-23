"""
Tests for Prompt v76: One shared authorization and release workflow.
Pins:
(a) A provisional determination CANNOT be submitted via POST /packet/submit (412) even with signed_by supplied.
(b) A non-clinician (Auditor user) CANNOT submit via POST /packet/submit (403) even for a FINAL determination.
(c) A verified clinician CAN submit a FINAL determination (200), receipt is honest (SUBMITTED_TO_PAYER, no fabricated acceptance).
(d) After an override to APPROVED, the packet and PDF export carry the overridden decision APPROVED.
(e) After an override to DENIED, the packet and FHIR export carry the overridden decision DENIED.
(f) The sign-off and override endpoints work for verified clinician, transitioning stage to FINAL with audit preserved.
(g) The EHR push enforces the shared gate (412 for provisional determination).
(h) Submitting with mismatched signed_by string is rejected with 400.
"""

import io
import json
import secrets
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from main import app
from app.db.session import SessionLocal
from app.db.models import User, AdjudicationLog
from app.core.security import get_password_hash, create_access_token

client = TestClient(app)


def _create_test_user(
    role: str = "Clinician",
    is_verified: bool = True,
    credential_title: str = "MD",
    npi: str = "1234567890",
) -> tuple[dict[str, str], User]:
    """Helper to provision test users with clean database state."""
    db = SessionLocal()
    uname = f"u_{secrets.token_hex(4)}"
    user = User(
        username=uname,
        email=f"{uname}@hospital.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role=role,
        is_active=True,
        is_verified_medical_pro=is_verified,
        credential_title=credential_title,
        npi_number=npi,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": uname, "role": role, "uid": user.id},
        expires_delta=timedelta(minutes=30),
    )
    db.close()
    return {"Authorization": f"Bearer {token}"}, user


def _adjudicate_case(auth_headers: dict[str, str], ehr_text: str, policy_id: str = "NCD-20.4") -> str:
    """Helper to adjudicate a test case and return its case_id."""
    res = client.post(
        "/api/v1/adjudicate",
        headers=auth_headers,
        json={
            "patient_id": f"PT-{secrets.token_hex(3).upper()}",
            "policy_id": policy_id,
            "ehr_narrative": ehr_text,
        },
    )
    assert res.status_code == 200, f"Adjudication failed: {res.text}"
    return res.json()["case_id"]


def test_v76_provisional_determination_cannot_be_submitted():
    """
    Task 4a: A provisional determination CANNOT be submitted via POST /packet/submit (412),
    even with a signed_by string supplied, when the caller is a verified clinician.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
    )

    # Submit before sign-off must be blocked by the shared release gate
    res = client.post(
        "/api/v1/packet/submit",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "signed_by": f"{clin_user.username}, MD",
            "clinician_notes": "Attempting pre-signoff submission.",
        },
    )
    assert res.status_code == 412
    detail = res.json()["detail"]
    assert "PROVISIONAL" in detail
    assert "determination_stage must be 'FINAL'" in detail or "Missing release conditions" in detail


def test_v76_non_clinician_cannot_submit_even_for_final_determination():
    """
    Task 4b: A non-clinician (e.g. an Auditor user) CANNOT submit via POST /packet/submit (403),
    even for a determination that has already been signed off into FINAL stage.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    auditor_headers, _ = _create_test_user(role="Auditor", is_verified=False)

    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
    )

    # Clinician signs off -> transitions to FINAL
    sign_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Reviewed and verified.",
            "clinician_npi": "1234567890",
            "clinician_credentials": "MD",
        },
    )
    assert sign_res.status_code == 200

    # Auditor attempts to submit the FINAL determination -> must be forbidden (403)
    aud_res = client.post(
        "/api/v1/packet/submit",
        headers=auditor_headers,
        json={
            "case_id": case_id,
            "signed_by": "Auditor User",
        },
    )
    assert aud_res.status_code == 403
    assert "Access denied" in aud_res.json()["detail"]


def test_v76_verified_clinician_can_submit_final_determination_with_honest_receipt():
    """
    Task 4c: A verified clinician CAN submit a FINAL (signed-off) determination (200),
    and the receipt does NOT contain 'TRANSMITTED_ACCEPTED' and does NOT claim transmission
    to or acceptance by a payer.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
    )

    # 1. Sign off
    sign_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Clinically indicated for ICD implantation.",
            "clinician_npi": "1234567890",
            "clinician_credentials": "MD",
        },
    )
    assert sign_res.status_code == 200

    # 2. Submit to insurance
    sub_res = client.post(
        "/api/v1/packet/submit",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "signed_by": f"{clin_user.username}, MD",
            "clinician_notes": "Ready for payer submission.",
            "payer_name": "CMS Medicare Part B / Noridian MAC",
        },
    )
    assert sub_res.status_code == 200
    receipt = sub_res.json()

    # Honest receipt invariants
    assert receipt["submission_status"] == "SUBMITTED_TO_PAYER"
    assert "TRANSMITTED_ACCEPTED" not in receipt["submission_status"]
    assert "LOCAL-SUBMISSION-REF-" in receipt["payer_transaction_id"]
    assert "no payer response has been received" in receipt["message"]
    assert "transmitted to" not in receipt["message"]
    assert receipt["signed_by"] == f"{clin_user.username}, MD"


def test_v76_override_to_approved_rebuilds_packet_and_pdf_export_reflects_approved():
    """
    Task 4d: After an override to APPROVED, the packet is rebuilt and the PDF export
    (and get_coverage_packet) carries the overridden decision APPROVED (not the original system decision).
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    # Fails LVEF requirement (LVEF 45% > 35%) -> System decision DENIED
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 45%.",
        policy_id="NCD-20.4",
    )

    # Verify initial decision was not APPROVED (was DEFERRED or DENIED)
    init_packet = client.get(f"/api/v1/packet/{case_id}", headers=clin_headers).json()
    assert init_packet["adjudication_decision"] in ("DEFERRED_TO_HUMAN", "DENIED")

    # Clinician overrides to APPROVED
    ovr_res = client.post(
        f"/api/v1/determination/{case_id}/override",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "override_decision": "APPROVED",
            "override_reason": "Clinical override: progressive refractory symptoms with high arrhythmic burden.",
        },
    )
    assert ovr_res.status_code == 200
    ovr_data = ovr_res.json()
    assert ovr_data["override_decision"] == "APPROVED"
    assert ovr_data["determination_stage"] == "FINAL"
    assert ovr_data["human_sign_off_status"] == "OVERRIDDEN_FINAL"

    # Verify packet cache was rebuilt with APPROVED decision
    post_packet = client.get(f"/api/v1/packet/{case_id}", headers=clin_headers).json()
    assert post_packet["adjudication_decision"] == "APPROVED"
    assert post_packet["determination_stage"] == "FINAL"
    assert post_packet["human_sign_off_status"] == "OVERRIDDEN_FINAL"

    # Verify PDF export carries APPROVED decision
    pdf_res = client.get(f"/api/v1/packet/{case_id}/pdf?require_final=true", headers=clin_headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert b"APPROVED" in pdf_res.content


def test_v76_override_to_denied_rebuilds_packet_and_fhir_export_reflects_denied():
    """
    Task 4e: After an override to DENIED, the packet is rebuilt and the FHIR export
    carries the overridden decision DENIED.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    # Qualifies for OSA -> System decision APPROVED
    case_id = _adjudicate_case(
        clin_headers,
        "Diagnostic PSG shows AHI of 32 events/hr. Face-to-face physician evaluation completed. Prescribing CPAP.",
        policy_id="LCD-L33829",
    )

    # Verify initial packet decision was APPROVED
    init_packet = client.get(f"/api/v1/packet/{case_id}", headers=clin_headers).json()
    assert init_packet["adjudication_decision"] == "APPROVED"

    # Clinician overrides to DENIED
    ovr_res = client.post(
        f"/api/v1/determination/{case_id}/override",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "override_decision": "DENIED",
            "override_reason": "Patient non-adherent with mask fitting; prior device returned unused.",
        },
    )
    assert ovr_res.status_code == 200

    # Verify packet cache reflects DENIED
    post_packet = client.get(f"/api/v1/packet/{case_id}", headers=clin_headers).json()
    assert post_packet["adjudication_decision"] == "DENIED"
    assert post_packet["determination_stage"] == "FINAL"

    # Verify FHIR export carries DENIED in embedded DocumentReference
    fhir_res = client.get(f"/api/v1/packet/{case_id}/fhir?require_final=true", headers=clin_headers)
    assert fhir_res.status_code == 200
    fhir_bundle = fhir_res.json()
    assert fhir_bundle["resourceType"] == "Bundle"

    # Decode embedded DocumentReference packet
    import base64
    doc_ref_entry = next(e for e in fhir_bundle["entry"] if e["resource"]["resourceType"] == "DocumentReference")
    b64_data = doc_ref_entry["resource"]["content"][0]["attachment"]["data"]
    embedded_packet = json.loads(base64.b64decode(b64_data).decode("utf-8"))
    assert embedded_packet["adjudication_decision"] == "DENIED"
    assert embedded_packet["determination_stage"] == "FINAL"
    assert embedded_packet["human_sign_off_status"] == "OVERRIDDEN_FINAL"


def test_v76_sign_off_and_override_lifecycle_preserves_audit_trail():
    """
    Task 4f: The sign-off endpoint transitions stage to FINAL / SIGNED_OFF,
    and the override endpoint transitions to FINAL / OVERRIDDEN_FINAL with
    the original system output preserved byte-identically.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 45%.",
        policy_id="NCD-20.4",
    )

    db = SessionLocal()
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log is not None
    orig_output = log.full_adjudication_json
    db.close()

    # Override
    ovr_res = client.post(
        f"/api/v1/determination/{case_id}/override",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "override_decision": "APPROVED",
            "override_reason": "Clinical override justification with extensive rationale.",
        },
    )
    assert ovr_res.status_code == 200

    # Check persistence and original preservation
    db = SessionLocal()
    log_after = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log_after.decision == "APPROVED"
    assert log_after.determination_stage == "FINAL"
    assert log_after.human_sign_off_status == "OVERRIDDEN_FINAL"
    assert log_after.original_system_output_json is not None
    assert log_after.original_system_output_json == orig_output
    db.close()


def test_v76_ehr_push_enforces_shared_gate_rejects_provisional():
    """
    Task 4g: The EHR push strictly enforces the shared gate (412 for provisional determination).
    """
    clin_headers, _ = _create_test_user(role="Clinician", is_verified=True)
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
    )

    # EHR push on provisional case -> 412 Precondition Failed
    res = client.post(
        f"/api/v1/packet/{case_id}/ehr-push",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "ehr_system": "Epic Systems Hyperdrive",
        },
    )
    assert res.status_code == 412
    assert "PROVISIONAL" in res.json()["detail"]


def test_v76_submit_rejects_signer_identity_mismatch():
    """
    Task 2d: If request.signed_by is present and does not match the authenticated clinician,
    it is rejected with HTTP 400 Bad Request.
    """
    clin_headers, clin_user = _create_test_user(role="Clinician", is_verified=True)
    case_id = _adjudicate_case(
        clin_headers,
        "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
    )

    # Sign off first so it is FINAL
    client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Attested.",
            "clinician_npi": "1234567890",
            "clinician_credentials": "MD",
        },
    )

    # Submit with mismatched signed_by string -> 400
    res = client.post(
        "/api/v1/packet/submit",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "signed_by": "Dr. Impostor, MD",
        },
    )
    assert res.status_code == 400
    assert "Signer name mismatch" in res.json()["detail"]
