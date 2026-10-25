import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.mfa_service import MFAService
from app.db.session import SessionLocal
from app.db.models import User

client = TestClient(app)

def test_mfa_all_three_options():
    try:
        # 0. Log in as a clinician
        login_res = client.post("/api/v1/auth/login", json={
            "username": "clinician@hospital.org",
            "password": "ClinicianCare!2026"
        }, headers={"X-Test-Bypass-MFA": "true"})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        auth_header = {"Authorization": f"Bearer {token}"}

        # =========================================================================
        # OPTION 1: AUTHENTICATOR APP (RFC 6238 TOTP)
        # =========================================================================
        setup_app = client.post("/api/v1/auth/mfa/setup?method=totp_app", headers=auth_header)
        assert setup_app.status_code == 200
        app_data = setup_app.json()
        secret = app_data["totp_secret"]
        assert secret is not None
        assert app_data["otpauth_uri"].startswith("otpauth://totp/")

        # Generate current 6-digit code using the secret
        app_code = MFAService.generate_totp_code(secret)
        enable_app = client.post("/api/v1/auth/mfa/enable", json={
            "mfa_method": "totp_app",
            "verification_code": app_code
        }, headers=auth_header)
        assert enable_app.status_code == 200
        assert enable_app.json()["status"] == "MFA_ENABLED"

        # Now attempt login -> Expect MFA_CHALLENGE_REQUIRED
        challenge_res = client.post("/api/v1/auth/login", json={
            "username": "clinician@hospital.org",
            "password": "ClinicianCare!2026"
        })
        assert challenge_res.status_code == 200
        challenge_data = challenge_res.json()
        assert challenge_data["status"] == "MFA_CHALLENGE_REQUIRED"
        assert challenge_data["mfa_method"] == "totp_app"
        challenge_token = challenge_data["mfa_session_token"]

        # Submit second-factor Authenticator code
        valid_code = MFAService.generate_totp_code(secret)
        verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": challenge_token,
            "verification_code": valid_code
        })
        assert verify_res.status_code == 200
        final_jwt = verify_res.json()
        assert "access_token" in final_jwt
        assert final_jwt["mfa_verified"] is True

        # =========================================================================
        # OPTION 2: EMAIL OTP
        # =========================================================================
        new_auth = {"Authorization": f"Bearer {final_jwt['access_token']}"}
        setup_email = client.post("/api/v1/auth/mfa/setup?method=email_otp", headers=new_auth)
        assert setup_email.status_code == 200
        email_data = setup_email.json()
        assert email_data["mfa_method"] == "email_otp"
        email_code = email_data["dev_preview_code"]

        enable_email = client.post("/api/v1/auth/mfa/enable", json={
            "mfa_method": "email_otp",
            "verification_code": email_code
        }, headers=new_auth)
        assert enable_email.status_code == 200

        # =========================================================================
        # OPTION 3: SMS / PHONE NUMBER OTP
        # =========================================================================
        setup_sms = client.post("/api/v1/auth/mfa/setup?method=sms_otp&phone=%2B14155552671", headers=new_auth)
        assert setup_sms.status_code == 200
        sms_data = setup_sms.json()
        assert sms_data["mfa_method"] == "sms_otp"
        sms_code = sms_data["dev_preview_code"]

        enable_sms = client.post("/api/v1/auth/mfa/enable", json={
            "mfa_method": "sms_otp",
            "verification_code": sms_code
        }, headers=new_auth)
        assert enable_sms.status_code == 200
        assert enable_sms.json()["status"] == "MFA_ENABLED"

        # OPTION 4: Disabling MFA is strictly forbidden under mandatory MFA policy
        dis_res = client.post("/api/v1/auth/mfa/disable", headers=new_auth)
        assert dis_res.status_code == 400
        assert "MFA cannot be disabled" in dis_res.json()["detail"]

    finally:
        # Always tear down MFA state so other test files run with standard credentials
        db = SessionLocal()
        u = db.query(User).filter(User.username == "clinician@hospital.org").first()
        if u:
            u.mfa_enabled = True
            u.mfa_method = "email_otp"
            u.totp_secret = None
            u.active_otp_code = None
            u.phone_number = None
            db.commit()
        db.close()

