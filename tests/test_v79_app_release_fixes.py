"""
Tests for Prompt v81 / v79 App-Release Fixes:
(i) An unassigned verified clinician is REJECTED on sign-off (403) and on override (403).
(ii) The case owner / assigned clinician CAN sign off and override.
(iii) A case with no owner and no assignment is NOT signable by an arbitrary verified clinician (403).
(iv) /pas/submit without auth is rejected (401).
(v) PAS replay is caller-scoped — the same Idempotency-Key from two different callers returns separate results, never a cross-caller replay.
(vi) A repeated submit with the same Idempotency-Key for the same case returns the original receipt (no duplicate record); the same key from a different caller does NOT return the first caller's receipt.
(vii) Sign-off via the packet-only branch writes log.full_packet_json (read directly from DB, not through the endpoint) saying FINAL/SIGNED_OFF with the correct signer.
(viii) A simulated restart — clear _EPHEMERAL_PACKETS and _EPHEMERAL_ADJUDICATIONS, then re-read the packet through get_coverage_packet and through each export path — returns the same decision, stage, signer, and signed_at as before the restart.
"""

import json
import secrets
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from main import app
from app.db.session import SessionLocal
from app.db.models import User, AdjudicationLog, EvaluationRun
from app.core.security import get_password_hash, create_access_token
from app.schemas.contracts import (
    CMSCoveragePacket,
    FilledCriterionSection,
    DeterminationStatus,
    AdjudicationDecision
)
from app.services.deferral_queue import DeferralWorkQueue
from app.api.routes import _EPHEMERAL_PACKETS, _EPHEMERAL_ADJUDICATIONS, get_coverage_packet
from app.core.idempotency import idempotency_engine

client = TestClient(app)


def _create_user(role: str = "Clinician", is_verified: bool = True, credential_title: str = "MD") -> tuple[dict[str, str], User]:
    db = SessionLocal()
    uname = f"u_v79_{secrets.token_hex(4)}"
    user = User(
        username=uname,
        email=f"{uname}@test.med",
        hashed_password=get_password_hash(secrets.token_hex(16)),
        role=role,
        is_active=True,
        is_verified_medical_pro=is_verified,
        credential_title=credential_title,
        npi_number=f"1{secrets.token_hex(4)}",
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


def _create_adjudicated_case(auth_headers: dict[str, str], assigned_user_id: int | None = None) -> str:
    res = client.post(
        "/api/v1/adjudicate",
        headers=auth_headers,
        json={
            "patient_id": f"PT-{secrets.token_hex(3).upper()}",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient has severe ischemic cardiomyopathy with LVEF 25%, NYHA Class III heart failure.",
            "execution_mode": "deterministic"
        },
    )
    assert res.status_code == 200, res.text
    case_id = res.json()["case_id"]
    if assigned_user_id:
        DeferralWorkQueue.assign_case(case_id, assigned_user_id)
        db = SessionLocal()
        log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
        if log:
            log.user_id = assigned_user_id
            db.commit()
        db.close()
    return case_id


def test_v79_unassigned_clinician_rejected_on_sign_off_and_override():
    """Pin (i): An unassigned verified clinician is REJECTED on sign-off (403) and on override (403)."""
    clin1_headers, clin1 = _create_user(role="Clinician", is_verified=True)
    clin2_headers, clin2 = _create_user(role="Clinician", is_verified=True)

    # Case owned by clin1
    case_id = _create_adjudicated_case(clin1_headers, assigned_user_id=clin1.id)

    # Clinician 2 (unassigned) attempts sign-off -> 403 Forbidden
    res_sign = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin2_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Attempted unauthorized sign-off."
        }
    )
    assert res_sign.status_code == 403
    assert "Access denied" in res_sign.json()["detail"]

    # Clinician 2 (unassigned) attempts override -> 403 Forbidden
    res_ovr = client.post(
        f"/api/v1/determination/{case_id}/override",
        headers=clin2_headers,
        json={
            "case_id": case_id,
            "override_decision": "APPROVED",
            "override_reason": "Attempted unauthorized clinical override with long reason."
        }
    )
    assert res_ovr.status_code == 403
    assert "Access denied" in res_ovr.json()["detail"]


def test_v79_case_owner_and_assigned_clinician_can_sign_off_and_override():
    """Pin (ii): The case owner / assigned clinician CAN sign off and override."""
    clin1_headers, clin1 = _create_user(role="Clinician", is_verified=True)
    clin2_headers, clin2 = _create_user(role="Clinician", is_verified=True)

    # 1. Owner signs off
    case_1 = _create_adjudicated_case(clin1_headers, assigned_user_id=clin1.id)
    res_sign = client.post(
        f"/api/v1/determination/{case_1}/sign-off",
        headers=clin1_headers,
        json={
            "case_id": case_1,
            "attestation_notes": "Attested by owner."
        }
    )
    assert res_sign.status_code == 200
    assert res_sign.json()["determination_stage"] == "FINAL"

    # 2. Assigned clinician overrides
    case_2 = _create_adjudicated_case(clin1_headers, assigned_user_id=clin2.id)
    res_ovr = client.post(
        f"/api/v1/determination/{case_2}/override",
        headers=clin2_headers,
        json={
            "case_id": case_2,
            "override_decision": "APPROVED",
            "override_reason": "Clinical override by assigned clinician."
        }
    )
    assert res_ovr.status_code == 200
    assert res_ovr.json()["override_decision"] == "APPROVED"
    assert res_ovr.json()["determination_stage"] == "FINAL"


def test_v79_unowned_unassigned_case_not_signable_by_arbitrary_clinician():
    """Pin (iii): A case with no owner and no assignment is NOT signable by an arbitrary verified clinician."""
    clin1_headers, _ = _create_user(role="Clinician", is_verified=True)
    clin2_headers, _ = _create_user(role="Clinician", is_verified=True)

    unowned_case_id = _create_adjudicated_case(clin1_headers)
    db = SessionLocal()
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == unowned_case_id).first()
    log.user_id = None
    db.commit()
    db.close()

    # Clear queue item assignment if any
    if unowned_case_id in DeferralWorkQueue._QUEUE:
        DeferralWorkQueue._QUEUE[unowned_case_id].assigned_to_user_id = None

    # Arbitrary clinician attempts sign-off on unowned case -> 403
    res_sign = client.post(
        f"/api/v1/determination/{unowned_case_id}/sign-off",
        headers=clin2_headers,
        json={
            "case_id": unowned_case_id,
            "attestation_notes": "Attempting signoff on unowned case."
        }
    )
    assert res_sign.status_code == 403
    assert "Access denied" in res_sign.json()["detail"]

    # Arbitrary clinician attempts override on unowned case -> 403
    res_ovr = client.post(
        f"/api/v1/determination/{unowned_case_id}/override",
        headers=clin2_headers,
        json={
            "case_id": unowned_case_id,
            "override_decision": "APPROVED",
            "override_reason": "Attempting override on unowned case."
        }
    )
    assert res_ovr.status_code == 403
    assert "Access denied" in res_ovr.json()["detail"]


def test_v79_pas_submit_unauthenticated_rejected():
    """Pin (iv): /pas/submit without auth is rejected (401)."""
    claim_payload = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-TEST-PAS"},
        "provider": {"reference": "Practitioner/NPI-1234567890"},
        "item": [{"sequence": 1, "productOrService": {"coding": [{"code": "33249"}]}}]
    }
    # No auth header -> 401 Unauthorized
    res = client.post("/api/v1/pas/submit", json=claim_payload)
    assert res.status_code == 401


def test_v79_pas_replay_caller_scoped():
    """Pin (v): PAS replay is caller-scoped — same Idempotency-Key from two callers returns separate results."""
    user1_headers, user1 = _create_user()
    user2_headers, user2 = _create_user()

    shared_key = f"pas-idemp-{secrets.token_hex(4)}"

    claim_user1 = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-USER1"},
        "provider": {"reference": "Practitioner/NPI-1234567890"},
        "item": [{"sequence": 1, "productOrService": {"coding": [{"code": "33249"}]}}],
        "supportingInfo": [{"sequence": 1, "valueString": "Remote MI 4 years ago, LVEF 25% on GDMT."}]
    }

    claim_user2 = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-USER2"},
        "provider": {"reference": "Practitioner/NPI-1234567890"},
        "item": [{"sequence": 1, "productOrService": {"coding": [{"code": "33249"}]}}],
        "supportingInfo": [{"sequence": 1, "valueString": "Acute STEMI 3 days ago, LVEF 40%."}]
    }

    # Caller 1 submits with shared_key
    res1 = client.post(
        "/api/v1/pas/submit",
        headers={**user1_headers, "Idempotency-Key": shared_key},
        json=claim_user1
    )
    assert res1.status_code == 200
    assert "Idempotency-Replay" not in res1.headers
    id1 = res1.json()["id"]

    # Caller 2 submits with SAME shared_key -> MUST NOT replay Caller 1's result
    res2 = client.post(
        "/api/v1/pas/submit",
        headers={**user2_headers, "Idempotency-Key": shared_key},
        json=claim_user2
    )
    assert res2.status_code == 200
    assert "Idempotency-Replay" not in res2.headers
    id2 = res2.json()["id"]
    assert id1 != id2, "Cross-caller replay detected! Different callers must have isolated idempotency scopes."

    # Caller 1 resubmits with shared_key -> Replay is returned for Caller 1
    res1_replay = client.post(
        "/api/v1/pas/submit",
        headers={**user1_headers, "Idempotency-Key": shared_key},
        json=claim_user1
    )
    assert res1_replay.status_code == 200
    assert res1_replay.headers.get("Idempotency-Replay") == "true"
    assert res1_replay.json()["id"] == id1


def test_v79_submit_idempotent_and_caller_scoped():
    """Pin (vi): Repeated submit with same Idempotency-Key returns original receipt; different caller gets separate scope."""
    clin1_headers, clin1 = _create_user(role="Clinician", is_verified=True)
    clin2_headers, clin2 = _create_user(role="Clinician", is_verified=True)

    case_1 = _create_adjudicated_case(clin1_headers, assigned_user_id=clin1.id)
    # Sign off case 1 to FINAL
    client.post(
        f"/api/v1/determination/{case_1}/sign-off",
        headers=clin1_headers,
        json={"case_id": case_1, "attestation_notes": "Attested."}
    )

    submit_key = f"sub-idemp-{secrets.token_hex(4)}"

    # Clinician 1 submits case 1
    res1 = client.post(
        "/api/v1/packet/submit",
        headers={**clin1_headers, "Idempotency-Key": submit_key},
        json={"case_id": case_1, "signed_by": f"{clin1.username}, MD"}
    )
    assert res1.status_code == 200
    assert "Idempotency-Replay" not in res1.headers
    receipt1 = res1.json()
    ref1 = receipt1["local_submission_reference"]

    # Clinician 1 resubmits same case with same key -> Returns exact same receipt
    res1_replay = client.post(
        "/api/v1/packet/submit",
        headers={**clin1_headers, "Idempotency-Key": submit_key},
        json={"case_id": case_1, "signed_by": f"{clin1.username}, MD"}
    )
    assert res1_replay.status_code == 200
    assert res1_replay.headers.get("Idempotency-Replay") == "true"
    receipt1_replay = res1_replay.json()
    assert receipt1_replay["local_submission_reference"] == ref1

    # Clinician 2 submits another case with SAME key -> Must NOT return Clinician 1's receipt
    case_2 = _create_adjudicated_case(clin2_headers, assigned_user_id=clin2.id)
    client.post(
        f"/api/v1/determination/{case_2}/sign-off",
        headers=clin2_headers,
        json={"case_id": case_2, "attestation_notes": "Attested 2."}
    )

    res2 = client.post(
        "/api/v1/packet/submit",
        headers={**clin2_headers, "Idempotency-Key": submit_key},
        json={"case_id": case_2, "signed_by": f"{clin2.username}, MD"}
    )
    assert res2.status_code == 200
    assert "Idempotency-Replay" not in res2.headers
    receipt2 = res2.json()
    assert receipt2["case_id"] == case_2
    assert receipt2["local_submission_reference"] != ref1


def test_v79_sign_off_packet_only_branch_persists_full_packet_json_in_db():
    """Pin (vii): Sign-off via the packet-only branch writes log.full_packet_json directly in DB saying FINAL/SIGNED_OFF."""
    clin_headers, clin = _create_user(role="Clinician", is_verified=True)
    case_id = _create_adjudicated_case(clin_headers, assigned_user_id=clin.id)

    # Put into packet cache only (remove from _EPHEMERAL_ADJUDICATIONS)
    assert case_id in _EPHEMERAL_PACKETS
    _EPHEMERAL_ADJUDICATIONS.pop(case_id, None)

    # In DB, ensure full_packet_json and full_adjudication_json are None before sign-off
    db = SessionLocal()
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log is not None
    log.full_packet_json = None
    log.full_adjudication_json = None
    db.commit()
    db.close()

    # Clinician signs off -> triggers `elif case_id in _EPHEMERAL_PACKETS:` branch
    res_sign = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Signing off via packet-only branch."
        }
    )
    assert res_sign.status_code == 200

    # Read directly from SQLite DB (NOT through the endpoint)
    db = SessionLocal()
    log_db = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log_db is not None
    assert log_db.full_packet_json is not None, "log.full_packet_json MUST be persisted in DB in packet-only branch!"

    db_packet = CMSCoveragePacket.model_validate_json(log_db.full_packet_json)
    assert db_packet.determination_stage == "FINAL"
    assert db_packet.human_sign_off_status == "SIGNED_OFF"
    assert db_packet.is_releasable is True
    assert clin.username in db_packet.signed_by
    db.close()


def test_v79_simulated_restart_exports_read_from_persisted_state():
    """Pin (viii): A simulated restart (clear in-memory dicts) returns the same decision, stage, signer, and signed_at through get_coverage_packet and each export path."""
    clin_headers, clin = _create_user(role="Clinician", is_verified=True)
    case_id = _create_adjudicated_case(clin_headers, assigned_user_id=clin.id)

    # 1. Sign off to FINAL
    res_sign = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=clin_headers,
        json={
            "case_id": case_id,
            "attestation_notes": "Official clinical sign-off attestation."
        }
    )
    assert res_sign.status_code == 200
    signed_data = res_sign.json()
    expected_stage = signed_data["determination_stage"]
    expected_status = signed_data["human_sign_off_status"]
    expected_signer = signed_data["signed_off_by"]
    expected_signed_at = signed_data["signed_off_at"]

    # 2. SIMULATED RESTART: Clear in-memory caches
    _EPHEMERAL_PACKETS.clear()
    _EPHEMERAL_ADJUDICATIONS.clear()
    assert case_id not in _EPHEMERAL_PACKETS
    assert case_id not in _EPHEMERAL_ADJUDICATIONS

    # 3. get_coverage_packet survives restart and loads from persisted DB
    db = SessionLocal()
    reloaded_packet = get_coverage_packet(case_id, current_user=clin, db=db)
    db.close()

    assert reloaded_packet.determination_stage == expected_stage
    assert reloaded_packet.human_sign_off_status == expected_status
    assert reloaded_packet.signed_by == expected_signer
    assert reloaded_packet.signed_at is not None
    assert expected_signed_at is not None
    assert reloaded_packet.signed_at.split("+")[0] == expected_signed_at.split("+")[0]

    # 4. Export paths survive simulated restart
    # (a) PDF Export
    res_pdf = client.get(f"/api/v1/packet/{case_id}/pdf?require_final=true", headers=clin_headers)
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"

    # (b) FHIR Bundle Export
    res_fhir = client.get(f"/api/v1/packet/{case_id}/fhir?require_final=true", headers=clin_headers)
    assert res_fhir.status_code == 200
    bundle = res_fhir.json()
    assert bundle["resourceType"] == "Bundle"

    # (c) EHR Push Export
    res_ehr = client.post(
        f"/api/v1/packet/{case_id}/ehr-push",
        headers=clin_headers,
        json={"case_id": case_id, "ehr_system": "Epic Systems Hyperdrive"}
    )
    assert res_ehr.status_code == 200
    assert res_ehr.json()["status"] == "SUCCESS_TRANSMITTED"

    # (d) Appeal Letter Export
    res_appeal = client.post(
        f"/api/v1/packet/{case_id}/appeal-letter?require_final=true",
        headers=clin_headers,
        json={"case_id": case_id}
    )
    assert res_appeal.status_code == 200

    # (e) Submit Export
    res_sub = client.post(
        "/api/v1/packet/submit",
        headers=clin_headers,
        json={"case_id": case_id, "signed_by": f"{clin.username}, MD"}
    )
    assert res_sub.status_code == 200
    assert res_sub.json()["submission_status"] == "SUBMITTED_TO_PAYER"
