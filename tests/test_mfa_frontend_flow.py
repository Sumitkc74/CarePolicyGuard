import secrets
import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.mfa_service import MFAService
from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import get_password_hash

client = TestClient(app)

def test_mfa_end_to_end_flow():
    test_pwd = secrets.token_urlsafe(16)
    test_email = f"test_doc_flow_{secrets.token_hex(4)}@hospital.org"
    db = SessionLocal()
    try:
        user = User(
            username=test_email,
            email=test_email,
            hashed_password=get_password_hash(test_pwd),
            role="Clinician",
            mfa_enabled=True,
            mfa_method="email_otp"
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    try:
        # 1. Test clinician login challenge
        login_resp = client.post("/api/v1/auth/login", json={
            "username": test_email,
            "password": test_pwd
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert data["status"] == "MFA_CHALLENGE_REQUIRED"
        assert data["mfa_method"] == "email_otp"
        assert "mfa_session_token" in data
        assert "dev_preview_code" not in data

        db_check = SessionLocal()
        try:
            u_check = db_check.query(User).filter(User.email == test_email).first()
            otp_code = u_check.active_otp_code
            assert otp_code is not None
        finally:
            db_check.close()

        # 2. Test MFA verification completes login and returns JWT
        verify_resp = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": data["mfa_session_token"],
            "verification_code": otp_code
        })
        assert verify_resp.status_code == 200
        token_data = verify_resp.json()
        assert "access_token" in token_data
        assert token_data["mfa_verified"] is True
        assert token_data["role"] == "Clinician"
        jwt_token = token_data["access_token"]

        auth_headers = {"Authorization": f"Bearer {jwt_token}"}

        # 3. Test check MFA status endpoint
        status_resp = client.get("/api/v1/auth/mfa/status", headers=auth_headers)
        assert status_resp.status_code == 200
        mfa_status = status_resp.json()
        assert mfa_status["mfa_enabled"] is True
        assert mfa_status["mfa_method"] == "email_otp"

        # 4. Test Authenticator App (RFC 6238 TOTP) setup
        setup_resp = client.post("/api/v1/auth/mfa/setup?method=totp_app", headers=auth_headers)
        assert setup_resp.status_code == 200
        setup_data = setup_resp.json()
        assert setup_data["mfa_method"] == "totp_app"
        assert setup_data["totp_secret"] is not None
        assert "api.qrserver.com" in setup_data["channel_destination"]

        # 5. Enable Authenticator App using real TOTP code
        current_totp_code = MFAService.generate_totp_code(setup_data["totp_secret"])
        enable_resp = client.post("/api/v1/auth/mfa/enable", headers=auth_headers, json={
            "mfa_method": "totp_app",
            "verification_code": current_totp_code
        })
        assert enable_resp.status_code == 200
        assert enable_resp.json()["status"] == "MFA_ENABLED"

        # 6. Test login now requires Authenticator App TOTP code
        login_totp = client.post("/api/v1/auth/login", json={
            "username": test_email,
            "password": test_pwd
        })
        assert login_totp.status_code == 200
        totp_challenge = login_totp.json()
        assert totp_challenge["status"] == "MFA_CHALLENGE_REQUIRED"
        assert totp_challenge["mfa_method"] == "totp_app"

        # Verify with generated TOTP code
        new_totp_code = MFAService.generate_totp_code(setup_data["totp_secret"])
        verify_totp = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": totp_challenge["mfa_session_token"],
            "verification_code": new_totp_code
        })
        assert verify_totp.status_code == 200
        new_token = verify_totp.json()["access_token"]
        new_headers = {"Authorization": f"Bearer {new_token}"}

        # 7. Test active device sessions listing
        sess_resp = client.get("/api/v1/auth/sessions", headers=new_headers)
        assert sess_resp.status_code == 200
        sessions = sess_resp.json()
        assert len(sessions) >= 1
        assert any(s["is_current"] for s in sessions)

    finally:
        db = SessionLocal()
        u = db.query(User).filter(User.username == test_email).first()
        if u:
            db.delete(u)
            db.commit()
        db.close()
