import pytest
from datetime import datetime, timezone, timedelta
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
    compute_audit_hash,
    sanitize_phi
)

def test_pbkdf2_password_hashing():
    raw_pass = "ClinicalCare!2026"
    hashed = get_password_hash(raw_pass)
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False

def test_jwt_token_generation_and_decoding():
    payload = {"sub": "auditor@medicare.cms.gov", "role": "Auditor"}
    token = create_access_token(payload, expires_delta=timedelta(minutes=30))
    decoded = decode_access_token(token)
    assert decoded["sub"] == "auditor@medicare.cms.gov"
    assert decoded["role"] == "Auditor"
    assert "exp" in decoded

def test_deterministic_audit_hash_tamper_evidence():
    ts = datetime.now(timezone.utc)
    base_criteria = [
        {"criterion_code": "CRIT-01", "status": "MET", "clinical_rationale": "LVEF 28%"},
        {"criterion_code": "CRIT-02", "status": "MET", "clinical_rationale": "NYHA II"}
    ]
    spans = [
        {"start_char": 100, "end_char": 120, "source_text": "LVEF 28%"}
    ]

    hash1 = compute_audit_hash("PT-***8821", "NCD-20.4", "APPROVED", 0.94, base_criteria, spans, ts)
    hash2 = compute_audit_hash("PT-***8821", "NCD-20.4", "APPROVED", 0.94, base_criteria, spans, ts)
    # Must be deterministic
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex string

    # Tamper test 1: Modify decision
    tampered_hash_decision = compute_audit_hash("PT-***8821", "NCD-20.4", "DENIED", 0.94, base_criteria, spans, ts)
    assert tampered_hash_decision != hash1

    # Tamper test 2: Modify character offset
    tampered_spans = [{"start_char": 105, "end_char": 125, "source_text": "LVEF 28%"}]
    tampered_hash_spans = compute_audit_hash("PT-***8821", "NCD-20.4", "APPROVED", 0.94, base_criteria, tampered_spans, ts)
    assert tampered_hash_spans != hash1

    # Tamper test 3: Modify criterion rationale
    tampered_criteria = [
        {"criterion_code": "CRIT-01", "status": "MET", "clinical_rationale": "LVEF 45%"},
        {"criterion_code": "CRIT-02", "status": "MET", "clinical_rationale": "NYHA II"}
    ]
    tampered_hash_crit = compute_audit_hash("PT-***8821", "NCD-20.4", "APPROVED", 0.94, tampered_criteria, spans, ts)
    assert tampered_hash_crit != hash1

def test_phi_sanitization():
    raw_ehr = """
    Patient Name: Robert Johnson
    DOB: 04/12/1958 | MRN: 9481023
    Phone: (555) 234-5678 | Email: r.johnson@email.com
    SSN: 987-65-4321
    Clinical assessment: Patient with ischemic heart failure and LVEF 28%.
    """
    sanitized = sanitize_phi(raw_ehr)
    assert "[REDACTED-NAME]" in sanitized
    assert "[REDACTED-DOB]" in sanitized
    assert "[REDACTED-MRN]" in sanitized
    assert "[REDACTED-PHONE]" in sanitized
    assert "[REDACTED-EMAIL]" in sanitized
    assert "[REDACTED-SSN]" in sanitized
    # Clinical values must be preserved
    assert "LVEF 28%" in sanitized
    assert "ischemic heart failure" in sanitized

def test_phi_sanitization_mbi_and_address():
    raw_ehr = """
    Patient: Eleanor Vance
    Medicare MBI: 1EG4-TE5-MK72
    Address: 450 Medical Center Boulevard, Suite 300
    Zip: 94143
    Clinical notes: Patient with NYHA Class III heart failure and LVEF 28%.
    """
    sanitized = sanitize_phi(raw_ehr)
    assert "[REDACTED-NAME]" in sanitized
    assert "[REDACTED-MBI]" in sanitized
    assert "[REDACTED-ADDRESS]" in sanitized
    assert "[REDACTED-ZIP]" in sanitized
    assert "LVEF 28%" in sanitized
    assert "NYHA Class III" in sanitized

def test_file_upload_security_disallowed_extension():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    malicious_payload = b"echo 'malicious script'"
    res = client.post(
        "/api/v1/extract-text",
        files={"file": ("malicious.exe", malicious_payload, "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "not permitted" in res.json()["detail"]

def test_zero_retention_mode():
    from fastapi.testclient import TestClient
    from main import app
    from app.db.session import SessionLocal
    from app.db.models import AdjudicationLog
    client = TestClient(app)

    db = SessionLocal()
    initial_count = db.query(AdjudicationLog).count()

    res = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-ZERO-RETENTION",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient with NYHA III heart failure, LVEF 28% on echo, on GDMT for 6 months. No acute MI.",
            "options": {"zero_retention": True}
        }
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # Verify that in zero retention mode, no record was persisted to SQLite
    final_count = db.query(AdjudicationLog).count()
    assert final_count == initial_count
    assert db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first() is None
    db.close()

def test_right_to_erasure_audit_delete():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # Run regular adjudication (persisted)
    res = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-ERASURE-TEST",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient with NYHA III heart failure, LVEF 28% on echo, on GDMT for 6 months. No acute MI.",
            "options": {"zero_retention": False}
        }
    )
    assert res.status_code == 200
    case_id = res.json()["case_id"]

    # Ensure it exists
    get_res = client.get(f"/api/v1/audit-logs/{case_id}")
    assert get_res.status_code == 200

    # Purge record under Right to Erasure
    del_res = client.delete(f"/api/v1/audit-logs/{case_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify it is deleted
    get_after = client.get(f"/api/v1/audit-logs/{case_id}")
    assert get_after.status_code == 404

def test_verify_clinical_document_authenticity():
    from app.core.security import verify_clinical_document_authenticity

    # Note with physician name and digital signature
    valid_note = """
    CARDIOLOGY CLINIC CONSULTATION NOTE
    PATIENT: Eleanor Vance | MRN: 94819201
    
    HPI: 67-year-old female with LVEF 28% and NYHA Class II symptoms.
    GDMT stable for 6 months.
    
    PLAN: Recommend ICD placement.
    
    ATTENDING PHYSICIAN:
    Dr. Sarah Jenkins, MD, FACC (NPI: 1487293810)
    
    SIGNATURE:
    Electronically signed by Dr. Sarah Jenkins, MD on 02/10/2026.
    """
    res = verify_clinical_document_authenticity(valid_note)
    assert res["is_authentic_clinical_note"] is True
    assert res["has_doctor_name"] is True
    assert "Jenkins" in res["doctor_name"]
    assert res["has_doctor_signature"] is True

    # Note missing doctor signature
    unsigned_note = """
    CLINICAL NOTE:
    Patient evaluated for LVEF 30% and heart failure symptoms.
    Provider: Dr. Robert Cole, MD.
    """
    res_unsigned = verify_clinical_document_authenticity(unsigned_note)
    assert res_unsigned["has_doctor_name"] is True
    assert res_unsigned["has_doctor_signature"] is False
    assert res_unsigned["is_authentic_clinical_note"] is False

    # Random non-medical text
    random_text = "This is a recipe for chocolate cake. Take 2 cups of flour and 1 cup of sugar."
    res_random = verify_clinical_document_authenticity(random_text)
    assert res_random["is_authentic_clinical_note"] is False
    assert res_random["has_doctor_name"] is False
    assert res_random["has_doctor_signature"] is False

def test_npi_luhn_algorithm_validation():
    from app.core.security import validate_npi_luhn
    # Valid NPIs under CMS ISO 7812 80840 Luhn standard
    assert validate_npi_luhn("1234567893") is True
    assert validate_npi_luhn("1043256787") is True
    # Invalid NPIs (checksum mismatch, wrong length, bad chars)
    assert validate_npi_luhn("1234567890") is False
    assert validate_npi_luhn("12345") is False
    assert validate_npi_luhn("123456789X") is False
    assert validate_npi_luhn("") is False
    assert validate_npi_luhn("9999999999") is False

def test_medical_professional_credential_verification_rules():
    from app.core.security import verify_medical_professional_credentials

    # Valid clinical provider
    valid_provider = {
        "full_name": "Dr. Sarah Jenkins",
        "email": "sjenkins@cardiology.hospital.org",
        "npi_number": "1043256787",
        "credential_title": "MD",
        "medical_license": "C194820",
        "license_state": "CA",
        "specialty": "Cardiology",
        "organization": "Pacific Heart & Vascular Institute"
    }
    result = verify_medical_professional_credentials(valid_provider)
    assert result["is_verified"] is True
    assert result["npi_valid"] is True
    assert result["email_valid"] is True
    assert result["credentials_valid"] is True
    assert result["state_license_valid"] is True

    # Disallowed personal email (@gmail.com)
    gmail_provider = valid_provider.copy()
    gmail_provider["email"] = "doctor_john@gmail.com"
    res_gmail = verify_medical_professional_credentials(gmail_provider)
    assert res_gmail["is_verified"] is False
    assert res_gmail["email_valid"] is False
    assert any("Personal webmail" in r for r in res_gmail["reasons"])

    # Invalid NPI number
    bad_npi_provider = valid_provider.copy()
    bad_npi_provider["npi_number"] = "1111111111"
    res_npi = verify_medical_professional_credentials(bad_npi_provider)
    assert res_npi["is_verified"] is False
    assert res_npi["npi_valid"] is False

    # Unrecognized clinical degree
    fake_degree_provider = valid_provider.copy()
    fake_degree_provider["credential_title"] = "MBA"
    res_degree = verify_medical_professional_credentials(fake_degree_provider)
    assert res_degree["is_verified"] is False
    assert res_degree["credentials_valid"] is False

def test_api_medical_registration_gate():
    from fastapi.testclient import TestClient
    from main import app
    import uuid
    client = TestClient(app)

    unique_user = f"dr_{uuid.uuid4().hex[:6]}"
    # 1. Attempt registering with personal email or invalid NPI -> rejected with 422
    reject_res = client.post("/api/v1/auth/register", json={
        "username": f"{unique_user}_fake",
        "email": f"{unique_user}@gmail.com",
        "password": "SecurePassword!2026",
        "role": "Clinician",
        "npi_number": "0000000000",
        "credential_title": "MD",
        "medical_license": "C12345",
        "license_state": "CA",
        "organization": "City Clinic"
    })
    assert reject_res.status_code == 422
    assert "reasons" in reject_res.json()["detail"]

    # 2. Register valid medical professional -> succeeds with 201 Created
    accept_res = client.post("/api/v1/auth/register", json={
        "username": unique_user,
        "email": f"{unique_user}@memorialhealth.org",
        "password": "SecurePassword!2026",
        "role": "Clinician",
        "full_name": "Dr. Eleanor Vance",
        "npi_number": "1043256787",
        "credential_title": "MD",
        "medical_license": "C194820",
        "license_state": "CA",
        "specialty": "Cardiology",
        "organization": "Memorial Health System"
    })
    assert accept_res.status_code == 201
    user_data = accept_res.json()
    assert user_data["username"] == unique_user
    assert user_data["role"] == "Clinician"
    assert user_data["is_verified_medical_pro"] is True
    assert user_data["npi_number"] == "1043256787"



