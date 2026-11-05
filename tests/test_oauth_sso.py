import pytest
from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.db.models import User

client = TestClient(app)

def test_oauth_config_endpoint():
    res = client.get("/api/v1/auth/oauth/config")
    assert res.status_code == 200
    data = res.json()
    assert "google" in data["supported_providers"]
    assert data["dev_mode"] is True

def test_google_sso_auto_provision_and_mfa():
    # 1. Sign in with Google (triggers MFA challenge for new clinical user)
    google_res = client.post("/api/v1/auth/oauth/google", json={
        "credential": "mock_google_dr.smith@pacificheart.org"
    })
    assert google_res.status_code == 200
    data = google_res.json()
    assert data["status"] == "MFA_CHALLENGE_REQUIRED"
    assert data["oauth_provider"] == "google"
    assert "mfa_session_token" in data
    assert "dev_preview_code" not in data

    # Retrieve dispatched OTP code delivered to user via real channel / database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "dr.smith@pacificheart.org").first()
        assert user is not None
        otp_code = user.active_otp_code
        assert otp_code is not None
    finally:
        db.close()

    # 2. Complete MFA verification
    verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
        "mfa_session_token": data["mfa_session_token"],
        "verification_code": otp_code
    })
    assert verify_res.status_code == 200
    token_data = verify_res.json()
    assert "access_token" in token_data
    assert token_data["role"] == "Clinician"
    assert token_data["username"] == "dr.smith@pacificheart.org"

    # 3. Verify user record in database: OAuth auto-provisioned accounts are created UNVERIFIED
    # with no invented NPI, title, specialty, or organization
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "dr.smith@pacificheart.org").first()
        assert user is not None
        assert user.oauth_provider == "google"
        assert user.is_verified_medical_pro is False
        assert user.npi_number is None
        assert user.credential_title is None
        assert user.specialty is None
        assert user.organization is None
    finally:
        db.close()

def test_google_sso_ignores_bypass_header_and_requires_mfa():
    # Test Google sign-in with bypass header: verify bypass is NOT permitted and MFA challenge is required
    google_res = client.post(
        "/api/v1/auth/oauth/google",
        json={"credential": "mock_google_dr.bypass@hospital.org"},
        headers={"X-Test-Bypass-MFA": "true"}
    )
    assert google_res.status_code == 200
    data = google_res.json()
    assert data["status"] == "MFA_CHALLENGE_REQUIRED"
    assert "access_token" not in data
    assert "mfa_session_token" in data

def test_oauth_invalid_token_returns_401():
    res = client.post("/api/v1/auth/oauth/google", json={
        "credential": "completely_invalid_garbage_token"
    })
    assert res.status_code == 401
    assert "Google authentication failed" in res.json()["detail"]
