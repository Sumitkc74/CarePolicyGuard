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
    assert "apple" in data["supported_providers"]
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
    assert "dev_preview_code" in data

    # 2. Complete MFA verification
    verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
        "mfa_session_token": data["mfa_session_token"],
        "verification_code": data["dev_preview_code"]
    })
    assert verify_res.status_code == 200
    token_data = verify_res.json()
    assert "access_token" in token_data
    assert token_data["role"] == "Clinician"
    assert token_data["username"] == "dr.smith@pacificheart.org"

    # 3. Verify user record in database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "dr.smith@pacificheart.org").first()
        assert user is not None
        assert user.oauth_provider == "google"
        assert user.is_verified_medical_pro is True
        assert user.verification_method == "OAUTH_GOOGLE_VERIFIED"
    finally:
        db.close()

def test_apple_sso_auto_provision_and_direct_bypass():
    # Test Apple sign-in with bypass header
    apple_res = client.post(
        "/api/v1/auth/oauth/apple",
        json={"id_token": "mock_apple_dr.jones@hospital.org"},
        headers={"X-Test-Bypass-MFA": "true"}
    )
    assert apple_res.status_code == 200
    token_data = apple_res.json()
    assert "access_token" in token_data
    assert token_data["role"] == "Clinician"
    assert token_data["username"] == "dr.jones@hospital.org"
    assert token_data["oauth_provider"] == "apple"

    # Verify user record in database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "dr.jones@hospital.org").first()
        assert user is not None
        assert user.oauth_provider == "apple"
        assert user.is_verified_medical_pro is True
    finally:
        db.close()

def test_oauth_invalid_token_returns_401():
    res = client.post("/api/v1/auth/oauth/google", json={
        "credential": "completely_invalid_garbage_token"
    })
    assert res.status_code == 401
    assert "Google authentication failed" in res.json()["detail"]

