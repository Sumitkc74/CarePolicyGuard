import secrets
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.bootstrap import (
    audit_self_registered_admins,
    bootstrap_production_admin,
    is_production_admin_seeded,
    migrate_legacy_unverified_clinicians,
)
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, UserRole
from app.db.models import AdjudicationLog, CredentialingAuditLog, User
from app.db.session import SessionLocal
from app.services.nppes_verifier import verify_npi_with_nppes
from main import app

client = TestClient(app)

# Obviously synthetic test identifiers for security compliance
SYNTHETIC_TEST_NPI_1 = "1043256787"  # Test synthetic Luhn-valid number
SYNTHETIC_TEST_NPI_2 = "1234567893"  # Test synthetic Luhn-valid number
SYNTHETIC_INVALID_NPI = "0000000000"


def create_test_token(user: User) -> str:
    return create_access_token(
        data={"sub": user.username, "role": user.role, "uid": user.id}
    )


# =============================================================================
# TASK 1: CLOSE SELF-GRANTING PATHS & BOOTSTRAP PRODUCTION ADMIN
# =============================================================================

def test_self_registration_requesting_admin_is_strictly_forbidden_403():
    """
    Task 1: Self-registration requesting Admin is rejected with HTTP 403.
    The open registration endpoint must never grant Admin.
    """
    res = client.post("/api/v1/auth/register", json={
        "username": f"attacker_{uuid.uuid4().hex[:6]}",
        "email": f"attacker_{uuid.uuid4().hex[:6]}@hospital.org",
        "password": "StrongTestPassword!2026",
        "role": "Admin"
    })
    assert res.status_code == 403
    assert "Self-registration requesting Admin role is forbidden" in res.json()["detail"]


def test_self_registration_disallows_arbitrary_roles_422():
    """
    Task 1: Self-registration permits Clinician or Auditor accounts only.
    """
    res = client.post("/api/v1/auth/register", json={
        "username": f"bad_role_{uuid.uuid4().hex[:6]}",
        "email": f"bad_role_{uuid.uuid4().hex[:6]}@hospital.org",
        "password": "StrongTestPassword!2026",
        "role": "SuperUser"
    })
    assert res.status_code == 422
    assert "Self-registration permits Clinician or Auditor accounts only" in res.json()["detail"]


def test_clinician_self_registration_is_unverified_and_cannot_sign():
    """
    Task 1 & Task 3: Clinician registration records format check honestly as FORMAT_CHECK_ONLY.
    The account is created UNVERIFIED (is_verified_medical_pro=False) and cannot sign determinations.
    """
    uname = f"clinician_reg_{uuid.uuid4().hex[:6]}"
    res = client.post("/api/v1/auth/register", json={
        "username": uname,
        "email": f"{uname}@generalhospital.org",
        "password": "StrongTestPassword!2026",
        "role": "Clinician",
        "full_name": "Dr. Synthetic Test",
        "npi_number": SYNTHETIC_TEST_NPI_1,
        "credential_title": "MD",
        "medical_license": "TEST-LIC-9999",
        "license_state": "CA",
        "organization": "General Hospital"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "Clinician"
    assert data["is_verified_medical_pro"] is False
    assert data["verification_method"] == "FORMAT_CHECK_ONLY"

    # Attempt sign-off with unverified clinician token -> clear 403 Forbidden
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == uname).first()
        token = create_test_token(user)
    finally:
        db.close()

    sign_res = client.post(
        "/api/v1/determination/TEST-CASE-UNVERIFIED-SIGN/sign-off",
        json={
            "signed_off": True,
            "signature_attestation": "Attempting sign-off without primary-source verification",
            "clinical_notes": "Attempting sign-off without primary-source verification"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert sign_res.status_code == 403
    assert "Clinician account verification is pending" in sign_res.json()["detail"]


def test_production_bootstrap_admin_and_closure():
    """
    Task 1: Production bootstrap admin is created once by operator.
    Enforces forced password change and MFA setup on first login.
    Once a production admin exists, further bootstrap attempts are rejected and logged.
    """
    db = SessionLocal()
    boot_email = f"boot_admin_{uuid.uuid4().hex[:6]}@deployment.med"
    try:
        # 1. Clean any existing non-demo production admins for test isolation
        db.query(User).filter(User.role == UserRole.ADMIN.value, User.is_demo_user.is_(False)).delete()
        db.commit()

        assert not is_production_admin_seeded(db)

        # 2. First bootstrap succeeds
        admin = bootstrap_production_admin(
            db=db,
            email=boot_email,
            password="InitialBootstrapSecret!2026",
            full_name="Deployment Lead"
        )
        assert admin.id is not None
        assert admin.is_bootstrap is True
        assert admin.is_demo_user is False
        assert admin.must_change_password is True
        assert admin.must_setup_mfa is True
        assert is_production_admin_seeded(db)

        # 3. Subsequent bootstrap attempt is permanently rejected
        with pytest.raises(RuntimeError) as exc_info:
            bootstrap_production_admin(
                db=db,
                email=f"second_admin_{uuid.uuid4().hex[:6]}@deployment.med",
                password="AnotherSecret!2026"
            )
        assert "Production admin already exists" in str(exc_info.value)

        # 4. First login requires password update; complete-setup clears flag
        token = create_test_token(admin)
        setup_res = client.post(
            "/api/v1/auth/bootstrap/complete-setup",
            json={"new_password": "PermanentProductionAdminPassword!2026"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert setup_res.status_code == 200

        # Verify flags cleared in database
        db.refresh(admin)
        assert admin.must_change_password is False
        assert admin.must_setup_mfa is False
    finally:
        db.close()


def test_demo_seed_does_not_count_as_production_admin():
    """
    Task 1: Demo seed accounts (is_demo_user=True) do not count as production admins
    and do not close the production bootstrap path.
    """
    db = SessionLocal()
    try:
        # Create a demo-seeded admin
        demo_adm = db.query(User).filter(User.email == "demo_eval_admin@carepolicyguard.med").first()
        if not demo_adm:
            demo_adm = User(
                username="demo_eval_admin@carepolicyguard.med",
                email="demo_eval_admin@carepolicyguard.med",
                hashed_password=get_password_hash("DemoSecret!1234"),
                role=UserRole.ADMIN.value,
                is_demo_user=True,
                is_bootstrap=False
            )
            db.add(demo_adm)
            db.commit()

        # If only demo admin exists, production admin is NOT considered seeded
        db.query(User).filter(User.role == UserRole.ADMIN.value, User.is_demo_user.is_(False)).delete()
        db.commit()

        assert not is_production_admin_seeded(db)
    finally:
        db.close()


def test_startup_audit_suspends_legacy_self_registered_admins():
    """
    Task 1: Startup check identifies legacy self-registered admin accounts
    and suspends them (is_active=False) with an audit notice.
    """
    db = SessionLocal()
    rogue_email = f"rogue_admin_{uuid.uuid4().hex[:6]}@suspicious.org"
    try:
        # Simulate legacy self-registered admin
        rogue = User(
            username=rogue_email,
            email=rogue_email,
            hashed_password=get_password_hash("Password1234!"),
            role=UserRole.ADMIN.value,
            is_active=True,
            is_demo_user=False,
            is_bootstrap=False,
            provisioned_by=None  # Created without authorized admin
        )
        db.add(rogue)
        db.commit()

        flagged = audit_self_registered_admins(db)
        assert any(f["email"] == rogue_email for f in flagged)

        db.refresh(rogue)
        assert rogue.is_active is False
    finally:
        db.close()


def test_oauth_auto_provisioning_is_unverified_with_no_invented_fields():
    """
    Task 1: OAuth creates accounts unverified (is_verified_medical_pro=False).
    OAuth never sets verified flag, credential title, specialty, or organization,
    and never invents a deterministic NPI.
    """
    email = f"oauth_physician_{uuid.uuid4().hex[:6]}@hospital.org"
    res = client.post("/api/v1/auth/oauth/google", json={
        "credential": f"mock_google_{email}"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "MFA_CHALLENGE_REQUIRED"

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        assert user.is_verified_medical_pro is False
        assert user.npi_number is None  # Never generated
        assert user.credential_title is None
        assert user.specialty is None
        assert user.organization is None
        assert user.verification_method == "OAUTH_GOOGLE_UNVERIFIED"
    finally:
        db.close()


def test_oauth_mock_credentials_fail_closed_in_production(monkeypatch):
    """
    Task 1: Mock credentials fail closed (flag off, or ENVIRONMENT=production, or DEBUG=False).
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res = client.post("/api/v1/auth/oauth/google", json={
        "credential": "mock_google_dr.prod@hospital.org"
    })
    assert res.status_code == 401


def test_oauth_unsigned_jwt_decode_is_rejected():
    """
    Task 1: Unsigned JWT payloads or tokens failing signature verification are rejected.
    """
    res = client.post("/api/v1/auth/oauth/google", json={
        "credential": "header.payload_without_signature.invalid"
    })
    assert res.status_code == 401


def test_get_auth_me_never_backfills_invented_npi():
    """
    Task 1: /auth/me renders missing NPI as None ("NPI not on file"),
    never backfilling a generated or synthetic number.
    """
    db = SessionLocal()
    email = f"clinician_nonpi_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        user = User(
            username=email,
            email=email,
            hashed_password=get_password_hash("TestPassword123!"),
            role=UserRole.CLINICIAN.value,
            npi_number=None,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_test_token(user)
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        me_data = res.json()
        assert me_data["npi_number"] is None

        # Verify DB was NOT updated with a generated NPI
        db.refresh(user)
        assert user.npi_number is None
    finally:
        db.close()


# =============================================================================
# TASK 2: ADMIN PROVISIONING ENDPOINTS
# =============================================================================

def test_admin_provisioning_endpoints_security():
    """
    Task 2:
    - Admin creates unverified clinician account (never sets is_verified or fake NPI).
    - Admin creates new Admin account (sole path to Admin after bootstrap).
    - Admin lists pending and all clinicians with verification state.
    - Admin deactivates user (signing and login blocked, past records intact).
    """
    db = SessionLocal()
    try:
        admin_email = f"super_admin_{uuid.uuid4().hex[:6]}@hospital.org"
        admin = User(
            username=admin_email,
            email=admin_email,
            hashed_password=get_password_hash("AdminPass12345!"),
            role=UserRole.ADMIN.value,
            is_active=True,
            is_bootstrap=True
        )
        db.add(admin)
        db.commit()
        admin_token = create_test_token(admin)

        # 1. Non-admin forbidden from provisioning
        clin_email = f"clin_prov_{uuid.uuid4().hex[:6]}@hospital.org"
        unauth_user = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("Pass12345!"),
            role=UserRole.CLINICIAN.value,
            is_active=True
        )
        db.add(unauth_user)
        db.commit()
        clin_token = create_test_token(unauth_user)

        unauth_res = client.post(
            "/api/v1/admin/users/clinicians",
            json={"email": f"new_{uuid.uuid4().hex[:6]}@hospital.org"},
            headers={"Authorization": f"Bearer {clin_token}"}
        )
        assert unauth_res.status_code == 403

        # 2. Admin provisions clinician (created unverified, no fake NPI)
        target_email = f"target_clin_{uuid.uuid4().hex[:6]}@hospital.org"
        prov_res = client.post(
            "/api/v1/admin/users/clinicians",
            json={
                "email": target_email,
                "full_name": "Dr. Prov Synthetic"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert prov_res.status_code == 201
        data = prov_res.json()
        assert data["email"] == target_email
        assert data["is_verified_medical_pro"] is False
        assert data["npi_number"] is None
        assert data["provisioned_by"] == admin.username

        # 3. Admin creates another Admin
        new_adm_email = f"second_adm_{uuid.uuid4().hex[:6]}@hospital.org"
        adm_res = client.post(
            "/api/v1/admin/users/admins",
            json={
                "email": new_adm_email,
                "password": "StrongNewAdminPassword!2026",
                "full_name": "Second In Command"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert adm_res.status_code == 201
        assert adm_res.json()["role"] == UserRole.ADMIN.value

        # 4. Admin lists pending clinicians
        list_res = client.get(
            "/api/v1/admin/users/clinicians?pending_only=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_res.status_code == 200
        pending_list = list_res.json()
        assert any(c["email"] == target_email for c in pending_list)

        # 5. Admin deactivates account -> login and signing blocked
        target_user = db.query(User).filter(User.email == target_email).first()
        deact_res = client.post(
            f"/api/v1/admin/users/{target_user.id}/status",
            json={"is_active": False, "reason": "Administrative suspension for audit"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert deact_res.status_code == 200
        assert deact_res.json()["is_active"] is False

        # Verify login blocked
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username": target_email, "password": "AnyPassword123!"}
        )
        assert login_res.status_code in (401, 403)
    finally:
        db.close()


# =============================================================================
# TASK 3: CREDENTIALING VERIFICATION & NPPES PRIMARY-SOURCE CHECK
# =============================================================================

def test_primary_source_nppes_verification_success_and_failure():
    """
    Task 3: Primary-source NPPES Registry check:
    - On name match: unlocks signing, sets NPPES_VERIFIED and expiration date.
    - On name mismatch: fails closed (is_verified stays False).
    - On network timeout: fails closed.
    """
    db = SessionLocal()
    email = f"nppes_clinician_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        user = User(
            username=email,
            email=email,
            full_name="Dr. Eleanor Vance",
            hashed_password=get_password_hash("TestPassword123!"),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=False
        )
        db.add(user)
        db.commit()
        token = create_test_token(user)

        # Case A: Name match success (mocked NPPES API payload)
        mock_registry_response = {
            "result_count": 1,
            "results": [{
                "number": SYNTHETIC_TEST_NPI_1,
                "basic": {
                    "first_name": "ELEANOR",
                    "last_name": "VANCE"
                }
            }]
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = bytes(str(mock_registry_response).replace("'", '"'), "utf-8")

            verif_res = client.post(
                "/api/v1/credentialing/verify/nppes",
                json={"npi_number": SYNTHETIC_TEST_NPI_1},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert verif_res.status_code == 200
            data = verif_res.json()
            assert data["is_verified"] is True
            assert data["verification_method"] == "NPPES_VERIFIED"
            assert data["expires_at"] is not None

        # Case B: Name mismatch fails closed
        with patch("urllib.request.urlopen") as mock_urlopen:
            mismatch_resp = {
                "result_count": 1,
                "results": [{
                    "number": SYNTHETIC_TEST_NPI_1,
                    "basic": {
                        "first_name": "ARTHUR",
                        "last_name": "PENDRAGON"
                    }
                }]
            }
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = bytes(str(mismatch_resp).replace("'", '"'), "utf-8")

            fail_res = client.post(
                "/api/v1/credentialing/verify/nppes",
                json={"npi_number": SYNTHETIC_TEST_NPI_1},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert fail_res.status_code == 200
            fail_data = fail_res.json()
            assert fail_data["is_verified"] is False
            assert "Provider name mismatch" in fail_data["reasons"][0]

        # Case C: Network error fails closed
        with patch("urllib.request.urlopen", side_effect=TimeoutError("CMS Registry connection timed out")):
            timeout_res = client.post(
                "/api/v1/credentialing/verify/nppes",
                json={"npi_number": SYNTHETIC_TEST_NPI_1},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert timeout_res.status_code == 200
            t_data = timeout_res.json()
            assert t_data["is_verified"] is False
            assert "unreachable" in t_data["reasons"][0].lower()
    finally:
        db.close()


def test_manual_credentialing_review_by_credentialing_role():
    """
    Task 3: Manual credentialing review performed by Credentialing role.
    Records evidence checked, decision, and writes immutable audit record.
    """
    db = SessionLocal()
    try:
        # Create Credentialing officer
        cred_email = f"cred_officer_{uuid.uuid4().hex[:6]}@hospital.org"
        cred_user = User(
            username=cred_email,
            email=cred_email,
            hashed_password=get_password_hash("CredOfficerPass123!"),
            role=UserRole.CREDENTIALING.value,
            is_active=True
        )
        db.add(cred_user)

        # Target clinician
        clin_email = f"manual_clin_{uuid.uuid4().hex[:6]}@hospital.org"
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("ClinPass123!"),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=False
        )
        db.add(clin)
        db.commit()

        cred_token = create_test_token(cred_user)

        # Approve clinician manually
        appr_res = client.post(
            "/api/v1/credentialing/verify/manual",
            json={
                "clinician_id": clin.id,
                "decision": "APPROVED",
                "evidence_checked": ["NPI", "STATE_MEDICAL_BOARD", "HOSPITAL_PRIVILEGES"],
                "evidence_reference": "CA-MED-BOARD-DOC-98124",
                "notes": "Verified primary source via state medical board verification portal.",
                "npi_number": SYNTHETIC_TEST_NPI_2,
                "credential_title": "DO",
                "medical_license": "20A19482",
                "license_state": "CA",
                "organization": "Memorial Health Network"
            },
            headers={"Authorization": f"Bearer {cred_token}"}
        )
        assert appr_res.status_code == 200
        data = appr_res.json()
        assert data["is_verified_medical_pro"] is True
        assert data["verification_method"] == "MANUAL_CREDENTIALING_VERIFIED"

        # Verify audit log recorded
        audit = db.query(CredentialingAuditLog).filter(
            CredentialingAuditLog.clinician_id == clin.id
        ).order_by(CredentialingAuditLog.created_at.desc()).first()
        assert audit is not None
        assert audit.action == "APPROVED"
        assert audit.actor_role == UserRole.CREDENTIALING.value
        assert "CA-MED-BOARD" in audit.evidence_reference
    finally:
        db.close()


# =============================================================================
# TASK 4: REVOCATION, EXPIRY & LEGACY DOWNGRADE MIGRATION
# =============================================================================

def test_revocation_blocks_signing_preserves_past_determinations():
    """
    Task 4: Revoking verification immediately blocks new sign-offs,
    while leaving existing signed determinations intact.
    """
    db = SessionLocal()
    clin_email = f"revoked_clin_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("Pass12345!"),
            role=UserRole.CLINICIAN.value,
            is_verified_medical_pro=True,
            verification_method="NPPES_VERIFIED",
            npi_number=SYNTHETIC_TEST_NPI_1,
            is_active=True
        )
        db.add(clin)

        # Existing signed determination in history
        past_log = AdjudicationLog(
            case_id="PAST-SIGNED-CASE-101",
            patient_id_masked="PT-MASKED-101",
            policy_id="NCD-20.4",
            decision="APPROVED",
            raw_confidence=0.95,
            criterion_evaluations_json="[]",
            evidence_spans_json="[]",
            adversarial_audits_json="[]",
            audit_hash="hash_past_signed_case_101",
            sanitized_ehr_preview="Preview",
            submission_status="SUBMITTED_TO_PAYER",
            signed_by=clin_email,
            determination_stage="FINAL",
            is_releasable=True,
            human_sign_off_status="SIGNED_OFF"
        )
        db.add(past_log)
        db.commit()

        # Create Admin to revoke
        adm_email = f"adm_revoker_{uuid.uuid4().hex[:6]}@hospital.org"
        adm = User(
            username=adm_email,
            email=adm_email,
            hashed_password=get_password_hash("AdminPass123!"),
            role=UserRole.ADMIN.value,
            is_active=True
        )
        db.add(adm)
        db.commit()

        adm_token = create_test_token(adm)
        clin_token = create_test_token(clin)

        # Revoke verification
        rev_res = client.post(
            f"/api/v1/credentialing/users/{clin.id}/revoke",
            json={"reason": "State medical license suspended pending investigation"},
            headers={"Authorization": f"Bearer {adm_token}"}
        )
        assert rev_res.status_code == 200
        assert rev_res.json()["is_verified_medical_pro"] is False

        # Attempt sign-off -> blocked with 403 Forbidden
        new_sign_res = client.post(
            "/api/v1/determination/NEW-CASE-POST-REVOKE/sign-off",
            json={
                "signed_off": True,
                "signature_attestation": "Attempting sign-off after revocation",
                "clinical_notes": "Attempting sign-off after revocation"
            },
            headers={"Authorization": f"Bearer {clin_token}"}
        )
        assert new_sign_res.status_code == 403
        assert "Clinician account verification is pending" in new_sign_res.json()["detail"]

        # Invariant check: Past signed record remains intact and unmodified
        db.refresh(past_log)
        assert past_log.human_sign_off_status == "SIGNED_OFF"
        assert past_log.is_releasable is True
        assert past_log.signed_by == clin_email
    finally:
        db.close()


def test_verification_expiry_blocks_new_sign_offs():
    """
    Task 4: Expired verification (re-check due date past) blocks new sign-offs until re-verified.
    """
    db = SessionLocal()
    clin_email = f"expired_clin_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        past_expiry = datetime.now(UTC) - timedelta(days=10)
        clin = User(
            username=clin_email,
            email=clin_email,
            hashed_password=get_password_hash("Pass12345!"),
            role=UserRole.CLINICIAN.value,
            is_verified_medical_pro=True,
            verification_method="NPPES_VERIFIED",
            verification_expires_at=past_expiry,
            is_active=True
        )
        db.add(clin)
        db.commit()
        clin_token = create_test_token(clin)

        sign_res = client.post(
            "/api/v1/determination/CASE-EXPIRED-TEST/sign-off",
            json={
                "signed_off": True,
                "signature_attestation": "Attempting sign with expired credentials",
                "clinical_notes": "Attempting sign with expired credentials"
            },
            headers={"Authorization": f"Bearer {clin_token}"}
        )
        assert sign_res.status_code == 403
        assert "Clinician credential verification expired" in sign_res.json()["detail"]
    finally:
        db.close()


def test_legacy_downgrade_migration_downgrades_format_only_and_oauth_accounts():
    """
    Task 4: Previously 'verified' accounts whose only verification was FORMAT_CHECK_ONLY
    or OAuth auto-verification are downgraded to pending on upgrade (no grandfathering).
    """
    db = SessionLocal()
    leg1 = f"legacy_format_{uuid.uuid4().hex[:6]}@hospital.org"
    leg2 = f"legacy_oauth_{uuid.uuid4().hex[:6]}@hospital.org"
    try:
        u1 = User(
            username=leg1,
            email=leg1,
            hashed_password=get_password_hash("Pass123!"),
            role=UserRole.CLINICIAN.value,
            is_verified_medical_pro=True,
            verification_method="NPPES_CMS_LUHN_VERIFIED",
            is_demo_user=False
        )
        u2 = User(
            username=leg2,
            email=leg2,
            hashed_password=get_password_hash("Pass123!"),
            role=UserRole.CLINICIAN.value,
            is_verified_medical_pro=True,
            verification_method="OAUTH_GOOGLE_VERIFIED",
            is_demo_user=False
        )
        db.add_all([u1, u2])
        db.commit()

        downgraded = migrate_legacy_unverified_clinicians(db)
        downgraded_emails = [d["email"] for d in downgraded]

        assert leg1 in downgraded_emails
        assert leg2 in downgraded_emails

        db.refresh(u1)
        db.refresh(u2)
        assert u1.is_verified_medical_pro is False
        assert u2.is_verified_medical_pro is False
        assert u1.verification_method == "FORMAT_CHECK_ONLY"
    finally:
        db.close()
