import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.mfa_service import MFAService
from app.db.session import SessionLocal
from app.db.models import User

client = TestClient(app)

def test_multiple_mfa_methods_and_login_selection():
    # 0. Ensure doctor@hospital.org has both email_otp and totp_app
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "doctor@hospital.org").first()
        if user:
            user.mfa_enabled = True
            user.mfa_method = "email_otp"
            user.mfa_enabled_methods = "email_otp,totp_app"
            user.totp_secret = "JBSWY3DPEHPK3PXP"
            user.active_otp_code = None
            user.otp_expires_at = None
            db.commit()
    finally:
        db.close()

    try:
        # 1. Login with doctor@hospital.org who has multiple MFA methods (Email OTP + TOTP App)
        login_res = client.post("/api/v1/auth/login", json={
            "username": "doctor@hospital.org",
            "password": "password123"
        })
        assert login_res.status_code == 200
        challenge = login_res.json()
        assert challenge["status"] == "MFA_CHALLENGE_REQUIRED"
        assert "available_methods" in challenge
        assert "email_otp" in challenge["available_methods"]
        assert "totp_app" in challenge["available_methods"]
        session_token = challenge["mfa_session_token"]

        # 2. Switch verification factor to Authenticator App during login
        switch_res = client.post("/api/v1/auth/mfa/challenge-method", json={
            "mfa_session_token": session_token,
            "requested_method": "totp_app"
        })
        assert switch_res.status_code == 200
        switch_data = switch_res.json()
        assert switch_data["status"] == "CHALLENGE_METHOD_SWITCHED"
        assert switch_data["mfa_method"] == "totp_app"

        # 3. Verify login using Authenticator App RFC 6238 TOTP code
        totp_code = MFAService.generate_totp_code("JBSWY3DPEHPK3PXP")
        verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": session_token,
            "verification_code": totp_code,
            "mfa_method": "totp_app"
        })
        assert verify_res.status_code == 200
        jwt_token = verify_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # 4. Check user profile MFA status - shows multiple active factors
        status_res = client.get("/api/v1/auth/mfa/status", headers=headers)
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert "email_otp" in status_data["enabled_methods"]
        assert "totp_app" in status_data["enabled_methods"]

        # 5. Add a 3rd factor: SMS OTP
        sms_setup = client.post("/api/v1/auth/mfa/setup?method=sms_otp&phone=%2B15555559876", headers=headers)
        assert sms_setup.status_code == 200
        sms_code = sms_setup.json()["dev_preview_code"]

        enable_sms = client.post("/api/v1/auth/mfa/enable", headers=headers, json={
            "mfa_method": "sms_otp",
            "verification_code": sms_code
        })
        assert enable_sms.status_code == 200
        assert "sms_otp" in enable_sms.json()["enabled_methods"]

        # 6. Remove a factor (SMS OTP) - allowed because 2 other factors remain
        rm_res = client.post("/api/v1/auth/mfa/remove-method?method=sms_otp", headers=headers)
        assert rm_res.status_code == 200
        assert "sms_otp" not in rm_res.json()["enabled_methods"]

        # 7. Remove TOTP App - leaves 1 factor (Email OTP)
        rm_totp = client.post("/api/v1/auth/mfa/remove-method?method=totp_app", headers=headers)
        assert rm_totp.status_code == 200
        assert rm_totp.json()["enabled_methods"] == ["email_otp"]

        # 8. Attempting to remove the last remaining factor is forbidden
        rm_last = client.post("/api/v1/auth/mfa/remove-method?method=email_otp", headers=headers)
        assert rm_last.status_code == 400
        assert "at least one active MFA factor" in rm_last.json()["detail"]

    finally:
        # Restore doctor clean state
        db = SessionLocal()
        u = db.query(User).filter(User.username == "doctor@hospital.org").first()
        if u:
            u.mfa_enabled = True
            u.mfa_method = "email_otp"
            u.mfa_enabled_methods = "email_otp,totp_app"
            u.totp_secret = "JBSWY3DPEHPK3PXP"
            u.active_otp_code = None
            u.otp_expires_at = None
            db.commit()
        db.close()

