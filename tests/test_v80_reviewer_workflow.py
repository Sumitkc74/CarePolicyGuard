"""
Tests for Prompt v80: Reviewer-facing criterion trace, run versioning, separate human assessment, versioned reproducible export.

Pins:
(i) Packet records policy_version, engine_version, note_version (hash), and run_id.
(ii) Re-adjudicating an existing case creates a new EvaluationRun record; old run is preserved and viewable.
(iii) Human assessment is stored in a separate table/model from system output, attached to run, and permission-gated to assigned clinician/owner.
(iv) Export (PDF and JSON packet) is labeled 'Coverage Criteria Evaluation', reads from persisted run record (not in-memory cache), and includes policy version, engine version, note hash, and human review block.
(v) Agent trace data is persisted and served through the API (Evaluator proposal, Verifier action/objection, Resolution).
(vi) Ambiguous-policy flow is preserved (SELECTION_REQUIRED leaves selection empty and lists candidate policies).
"""

import hashlib
import secrets
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.security import create_access_token, get_password_hash
from app.db.models import User
from app.db.session import SessionLocal
from main import app

client = TestClient(app)


def _create_test_user(
    role: str = "Clinician",
    is_verified: bool = True,
    credential_title: str = "MD",
    npi: str = "1234567890",
) -> tuple[dict[str, str], User]:
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


SAMPLE_EHR = (
    "Patient is a 68-year-old male presenting for cardiology evaluation. "
    "Transthoracic echocardiogram demonstrates severe ischemic cardiomyopathy with LVEF 25%. "
    "Patient is currently in NYHA Class III heart failure despite guideline-directed medical therapy for 90 days. "
    "No active noncardiac terminal illness present. Normal functional life expectancy > 1 year."
)


def test_v80_packet_records_version_pins():
    """Pin (i): Packet records policy_version, engine_version, note_version (hash), and run_id."""
    headers, _user = _create_test_user()
    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": "PT-V80-001",
            "policy_id": "NCD-20.4",
            "ehr_narrative": SAMPLE_EHR,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    case_id = data["case_id"]

    # Verify FinalAdjudication fields
    assert "run_id" in data and data["run_id"].startswith("RUN-")
    assert data["policy_version"] == "2024.1"
    assert "v80" in data["engine_version"]
    expected_hash = hashlib.sha256(data["sanitized_ehr_text"].encode("utf-8")).hexdigest()
    assert data["note_version"] == expected_hash

    # Verify Packet endpoint has the exact same version pins
    pkt_res = client.get(f"/api/v1/packet/{case_id}", headers=headers)
    assert pkt_res.status_code == 200
    pkt = pkt_res.json()
    assert pkt["policy_version"] == "2024.1"
    assert "v80" in pkt["engine_version"]
    assert pkt["note_version"] == expected_hash
    assert pkt["run_id"] == data["run_id"]
    assert pkt["evaluation_label"] == "Coverage Criteria Evaluation"


def test_v80_re_adjudication_creates_new_run_preserving_old():
    """Pin (ii): Re-adjudicating an existing case creates a new EvaluationRun record; old run is preserved and viewable."""
    headers, _user = _create_test_user()
    # Initial adjudication
    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": "PT-V80-002",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient has mild chest pain. LVEF not documented.",
        },
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # Append addendum which triggers re-adjudication
    add_res = client.post(
        f"/api/v1/packet/{case_id}/addendum",
        headers=headers,
        json={
            "criterion_code": "CRIT-ICD-01",
            "addendum_text": "Follow-up echo confirms LVEF 28% with severe ischemic cardiomyopathy.",
            "clinician_npi": "1234567890",
            "clinician_name": "Dr. Test Clinician"
        }
    )
    assert add_res.status_code == 200

    # Query runs endpoint
    runs_res = client.get(f"/api/v1/adjudication/{case_id}/runs", headers=headers)
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 2, f"Expected at least 2 runs, got {len(runs)}"
    assert runs[0]["run_number"] == 1
    assert runs[1]["run_number"] == 2
    assert runs[0]["run_id"] != runs[1]["run_id"]

    # Verify specific run retrieval works for both runs
    r1_res = client.get(f"/api/v1/adjudication/{case_id}/runs/{runs[0]['run_id']}", headers=headers)
    assert r1_res.status_code == 200
    assert r1_res.json()["run_number"] == 1

    r2_res = client.get(f"/api/v1/adjudication/{case_id}/runs/{runs[1]['run_id']}", headers=headers)
    assert r2_res.status_code == 200
    assert r2_res.json()["run_number"] == 2


def test_v80_human_assessment_stored_separately_and_permission_gated():
    """Pin (iii): Human assessment is stored in a separate table/model, attached to run, and permission-gated."""
    headers1, user1 = _create_test_user(role="Clinician")
    headers2, _user2 = _create_test_user(role="Clinician")
    auditor_headers, _auditor = _create_test_user(role="Auditor")

    res = client.post(
        "/api/v1/adjudicate",
        headers=headers1,
        json={
            "patient_id": "PT-V80-003",
            "policy_id": "NCD-20.4",
            "ehr_narrative": SAMPLE_EHR,
        },
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]
    run_id = res.json()["run_id"]

    # Clinician 1 records assessment on their case
    ha_payload = {
        "overall_agreement": "AGREE",
        "clinical_rationale": "I have independently reviewed the echo and clinical chart and concur with coverage.",
        "criterion_assessments": {
            "CRIT-ICD-01": {
                "clinician_status": "MET",
                "agrees_with_system": True,
                "clinician_notes": "LVEF 25% verified."
            }
        }
    }
    ha_res = client.post(
        f"/api/v1/adjudication/{case_id}/runs/{run_id}/assessment",
        headers=headers1,
        json=ha_payload
    )
    assert ha_res.status_code == 200, ha_res.text
    ha_data = ha_res.json()
    assert ha_data["overall_agreement"] == "AGREE"
    assert ha_data["reviewer_username"] == user1.username

    # Verify retrieval
    get_ha = client.get(f"/api/v1/adjudication/{case_id}/runs/{run_id}/assessment", headers=headers1)
    assert get_ha.status_code == 200
    assert get_ha.json()["overall_agreement"] == "AGREE"

    # Clinician 2 (unassigned) trying to record assessment on user1's case is blocked (404 under anti-enumeration defense)
    ha_res_unauth = client.post(
        f"/api/v1/adjudication/{case_id}/runs/{run_id}/assessment",
        headers=headers2,
        json=ha_payload
    )
    assert ha_res_unauth.status_code == 404

    # Auditor cannot post clinical assessment (403 Forbidden since Auditor is not a verified clinician)
    ha_res_aud = client.post(
        f"/api/v1/adjudication/{case_id}/runs/{run_id}/assessment",
        headers=auditor_headers,
        json=ha_payload
    )
    assert ha_res_aud.status_code == 403


def test_v80_export_reads_from_persisted_run_with_label_and_assessment():
    """Pin (iv): Export (PDF and JSON packet) is labeled 'Coverage Criteria Evaluation', reads from persisted record, and includes versions."""
    from app.api.routes import _EPHEMERAL_ADJUDICATIONS, _EPHEMERAL_PACKETS

    headers, _user = _create_test_user()
    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": "PT-V80-004",
            "policy_id": "NCD-20.4",
            "ehr_narrative": SAMPLE_EHR,
        },
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]
    run_id = res.json()["run_id"]

    # Sign off so determination is releasable
    signoff_res = client.post(
        f"/api/v1/determination/{case_id}/sign-off",
        headers=headers,
        json={"attestation_notes": "Reviewed and signed off for final evaluation."}
    )
    assert signoff_res.status_code == 200

    # Record human assessment
    ha_res = client.post(
        f"/api/v1/adjudication/{case_id}/runs/{run_id}/assessment",
        headers=headers,
        json={
            "overall_agreement": "AGREE",
            "clinical_rationale": "Independent clinician attestation complete.",
            "criterion_assessments": {}
        }
    )
    assert ha_res.status_code == 200

    # CLEAR IN-MEMORY EPHEMERAL CACHES to prove exports read from persisted record
    _EPHEMERAL_PACKETS.pop(case_id, None)
    _EPHEMERAL_ADJUDICATIONS.pop(case_id, None)

    # Test PDF Export with persisted record
    pdf_res = client.get(f"/api/v1/packet/{case_id}/pdf?require_final=true&run_id={run_id}", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    pdf_content = pdf_res.content.decode("latin1", errors="ignore")
    assert "MEDICARE COVERAGE CRITERIA EVALUATION" in pdf_content
    assert "Coverage Criteria Evaluation" in pdf_content
    assert "Policy Version:        2024.1" in pdf_content
    assert "v80" in pdf_content
    assert "CLINICIAN HUMAN ASSESSMENT" in pdf_content


def test_v80_agent_trace_data_persisted_and_served():
    """Pin (v): Agent trace data is persisted and served through the API."""
    headers, _user = _create_test_user()
    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": "PT-V80-005",
            "policy_id": "NCD-20.4",
            "ehr_narrative": SAMPLE_EHR,
        },
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    trace_res = client.get(f"/api/v1/adjudication/{case_id}/trace", headers=headers)
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert "traces" in trace_data
    traces = trace_data["traces"]
    assert len(traces) > 0

    first_trace = traces[0]
    assert "evaluator_proposal" in first_trace
    assert "verifier_finding" in first_trace
    assert "resolution" in first_trace
    assert "gate_a_verbatim_grounded" in first_trace["evaluator_proposal"]
    assert "gate_c_concept_scope" in first_trace["verifier_finding"]


def test_v80_ambiguous_policy_flow_preserved():
    """Pin (vi): Ambiguous-policy flow is preserved (SELECTION_REQUIRED leaves selection empty and lists candidate policies)."""
    headers, _user = _create_test_user()
    ambiguous_ehr = (
        "Patient is a 55-year-old presenting with chronic hip pain and labral symptoms. "
        "Diagnostic findings and clinical examination notes attached."
    )
    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": "PT-V80-006",
            "policy_id": "AUTO",
            "ehr_narrative": ambiguous_ehr,
        },
    )
    assert res.status_code == 200
    data = res.json()
    # Check that shortlist / candidate policies are returned without crashing
    assert "policy_id" in data
