import uuid
from fastapi.testclient import TestClient
from app.core.security import create_access_token, get_password_hash, UserRole
from app.db.models import User
from app.db.session import SessionLocal
from main import app

client = TestClient(app)

def create_test_token(user: User) -> str:
    return create_access_token(
        data={"sub": user.username, "role": user.role, "uid": user.id}
    )

def test_non_preset_case_without_patient_name_renders_not_on_file():
    """
    Task 4: A non-preset case submitted without a patient name renders "Not on file"
    in the signed packet, not a default name (such as Eleanor Vance).
    """
    db = SessionLocal()
    clin_email = f"clin_auth_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("ClinPass123!"),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=True,
            verification_method="NPPES_VERIFIED",
            npi_number="1043256787"
        )
        db.add(clin)
        db.commit()
        token = create_test_token(clin)

        clinical_note = """CLINICAL PROGRESS NOTE
CHIEF COMPLAINT: Follow-up of ischemic cardiomyopathy.
LVEF 28% confirmed on echocardiogram. NYHA Class II symptoms.
GDMT stable on Carvedilol and Lisinopril for 6 months. Prior MI 2 years ago.
ASSESSMENT & PLAN: Implantable cardioverter-defibrillator indicated under NCD 20.4."""

        # Adjudicate without providing patient_name
        adj_res = client.post(
            "/api/v1/adjudicate",
            json={
                "ehr_narrative": clinical_note,
                "policy_id": "NCD-20.4",
                "patient_id": "PT-CUSTOM-9921",
                "patient_name": None
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert adj_res.status_code == 200
        case_id = adj_res.json()["case_id"]

        # Fetch packet prior to sign-off
        pkt_res = client.get(
            f"/api/v1/packet/{case_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert pkt_res.status_code == 200
        packet = pkt_res.json()
        assert packet["patient_name"] == "Not on file"
        assert "Eleanor" not in packet["patient_name"]
        assert "Vance" not in packet["patient_name"]

        # Sign-off on determination
        sign_res = client.post(
            f"/api/v1/determination/{case_id}/sign-off",
            json={
                "attestation_notes": "Medical necessity verified by attending clinician."
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert sign_res.status_code == 200
        assert sign_res.json()["human_sign_off_status"] == "SIGNED_OFF"

        # Fetch signed packet
        signed_pkt_res = client.get(
            f"/api/v1/packet/{case_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert signed_pkt_res.status_code == 200
        signed_pkt = signed_pkt_res.json()
        assert signed_pkt["patient_name"] == "Not on file"
        assert signed_pkt["human_sign_off_status"] == "SIGNED_OFF"
    finally:
        db.close()


def test_preset_cases_render_synthetic_data_notice_not_invented_dob():
    """
    Task 4: Preset cases render synthetic-data notice, not an invented DOB.
    """
    res = client.get("/api/v1/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) >= 5

    invented_dobs = ["05/14/1958", "09/22/1961", "11/03/1955", "03/17/1964", "08/12/1970", "02/10/1962"]

    for p in presets:
        assert p["patient_name"] == "Not on file" or "Synthetic" in p["patient_name"]
        ehr = p["ehr_text"]
        assert "[SYNTHETIC TEST DATA" in ehr
        assert "NOT A REAL PATIENT RECORD" in ehr
        # Ensure no invented real-looking dates of birth exist in preset EHRs
        for dob in invented_dobs:
            assert f"DOB: {dob}" not in ehr


def test_auditor_redaction_still_functions():
    """
    Task 4: Auditor view enforces privacy redaction; clinicians see authentic details.
    """
    db = SessionLocal()
    aud_email = f"aud_{uuid.uuid4().hex[:6]}@regulator.gov"
    clin_email = f"clin_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        aud = User(
            username=aud_email,
            email=aud_email,
            hashed_password=get_password_hash("AuditorPass123!"),
            role=UserRole.AUDITOR.value,
            is_active=True
        )
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("ClinPass123!"),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=True,
            verification_method="NPPES_VERIFIED",
            npi_number="1043256787"
        )
        db.add_all([aud, clin])
        db.commit()

        clin_token = create_test_token(clin)
        aud_token = create_test_token(aud)

        clinical_note = """CLINICAL PROGRESS NOTE
CHIEF COMPLAINT: Follow-up of ischemic cardiomyopathy.
LVEF 28% confirmed on echocardiogram. NYHA Class II symptoms.
GDMT stable on Carvedilol and Lisinopril for 6 months. Prior MI 2 years ago.
ASSESSMENT & PLAN: Implantable cardioverter-defibrillator indicated under NCD 20.4."""

        # Clinician submits with an authentic patient name
        adj_res = client.post(
            "/api/v1/adjudicate",
            json={
                "ehr_narrative": clinical_note,
                "policy_id": "NCD-20.4",
                "patient_id": "PT-VERIFIED-7712",
                "patient_name": "Authentic Patient Name"
            },
            headers={"Authorization": f"Bearer {clin_token}"}
        )
        assert adj_res.status_code == 200
        case_id = adj_res.json()["case_id"]

        # 1. Clinician sees the authentic patient name
        clin_pkt_res = client.get(
            f"/api/v1/packet/{case_id}",
            headers={"Authorization": f"Bearer {clin_token}"}
        )
        assert clin_pkt_res.status_code == 200
        assert clin_pkt_res.json()["patient_name"] == "Authentic Patient Name"

        # 2. Auditor sees [REDACTED (Auditor Mode)] and masked ID
        aud_pkt_res = client.get(
            f"/api/v1/packet/{case_id}",
            headers={"Authorization": f"Bearer {aud_token}"}
        )
        assert aud_pkt_res.status_code == 200
        aud_pkt = aud_pkt_res.json()
        assert aud_pkt["patient_name"] == "[REDACTED (Auditor Mode)]"
        assert "***" in aud_pkt["patient_id"]
    finally:
        db.close()


def test_clinician_view_shows_true_name_when_provided_and_not_on_file_when_omitted():
    """
    Task 4: Clinician view shows true name when provided, and 'Not on file' when omitted.
    Never an invented fallback name.
    """
    db = SessionLocal()
    clin_email = f"clin_view_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("ClinPass123!"),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=True,
            verification_method="NPPES_VERIFIED",
            npi_number="1043256787"
        )
        db.add(clin)
        db.commit()
        token = create_test_token(clin)

        note = """CLINICAL PROGRESS NOTE: Severe OSA evaluation.
Polysomnography shows AHI 32 events/hr. Documented face-to-face evaluation.
PLAN: CPAP titration and DME order."""

        # Case 1: Provided true name
        r1 = client.post(
            "/api/v1/adjudicate",
            json={
                "ehr_narrative": note,
                "policy_id": "LCD-L33829",
                "patient_id": "PT-CUSTOM-111",
                "patient_name": "Real Name Provided"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r1.status_code == 200
        p1 = client.get(f"/api/v1/packet/{r1.json()['case_id']}", headers={"Authorization": f"Bearer {token}"}).json()
        assert p1["patient_name"] == "Real Name Provided"

        # Case 2: Omitted patient name
        r2 = client.post(
            "/api/v1/adjudicate",
            json={
                "ehr_narrative": note,
                "policy_id": "LCD-L33829",
                "patient_id": "PT-CUSTOM-222",
                "patient_name": None
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r2.status_code == 200
        p2 = client.get(f"/api/v1/packet/{r2.json()['case_id']}", headers={"Authorization": f"Bearer {token}"}).json()
        assert p2["patient_name"] == "Not on file"
    finally:
        db.close()
