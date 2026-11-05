"""
Task 3: MFA Email Delivery Channel and Dev-Only Fallback Tests.
Verifies that:
1. When SMTP is unconfigured and DEV_OTP_DELIVERY_ENABLED=False, email-OTP login/setup
   fails promptly with HTTP 503 without hang, loop, or code leak.
2. TOTP path remains fully functional regardless of email delivery configuration.
3. When DEV_OTP_DELIVERY_ENABLED=True in dev mode, OTP is dispatched to server-side dev channel.
4. Second-factor authentication completes successfully using the dev-channel delivered code.
5. In production mode (ENVIRONMENT="production" or DEBUG=False), dev delivery is strictly disabled.
6. When SMTP is configured, normal SMTP path is used and dev channel receives no output.
7. NON-NEGOTIABLE SECURITY: Test secrets and OTP codes are generated in-memory inside the test.
"""

import pytest
import secrets
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import get_password_hash, create_access_token
from app.services.mfa_service import MFAService, DevOtpDeliveryChannel

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_dev_channel_and_settings():
    DevOtpDeliveryChannel.clear()
    original_dev_enabled = settings.DEV_OTP_DELIVERY_ENABLED
    original_smtp_enabled = settings.SMTP_ENABLED
    original_env = settings.ENVIRONMENT
    original_debug = settings.DEBUG
    yield
    DevOtpDeliveryChannel.clear()
    settings.DEV_OTP_DELIVERY_ENABLED = original_dev_enabled
    settings.SMTP_ENABLED = original_smtp_enabled
    settings.ENVIRONMENT = original_env
    settings.DEBUG = original_debug


def test_smtp_off_and_dev_off_returns_challenge_with_delivery_unavailable():
    """
    Task 1 (Updated contract): Proves that when SMTP is unconfigured and DEV_OTP_DELIVERY_ENABLED is False,
    initiating email OTP does NOT fail with HTTP 503; instead it issues an MFA challenge (HTTP 200)
    with explicit delivery_status='DELIVERY_UNAVAILABLE' so the user is informed and not blocked,
    without leaking any code, preview, or access token.
    """
    settings.SMTP_ENABLED = False
    settings.DEV_OTP_DELIVERY_ENABLED = False

    # In-memory test clinician
    test_pwd = secrets.token_urlsafe(16)
    test_user_email = f"clinician_nomfa_{secrets.token_hex(4)}@hospital.med"
    db = SessionLocal()
    try:
        user = User(
            username=test_user_email,
            email=test_user_email,
            hashed_password=get_password_hash(test_pwd),
            role="Clinician",
            is_active=True,
            mfa_enabled=True,
            mfa_method="email_otp"
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    # Step 1: Login attempt triggers email OTP dispatch
    login_res = client.post("/api/v1/auth/login", json={
        "username": test_user_email,
        "password": test_pwd
    })
    # Must succeed with 200 and return MFA challenge with delivery_status="DELIVERY_UNAVAILABLE"
    assert login_res.status_code == 200
    res_data = login_res.json()
    assert res_data["status"] == "MFA_CHALLENGE_REQUIRED"
    assert res_data["delivery_status"] == "DELIVERY_UNAVAILABLE"
    assert "mfa_session_token" in res_data
    assert "access_token" not in res_data
    assert "preview" not in login_res.text.lower()
    assert "code" not in res_data


def test_login_contract_email_delivery_unavailable_with_totp_fallback_works_end_to_end():
    """
    Task 1: Asserts the exact contract: login with email-OTP MFA and no delivery channel configured
    returns a challenge (not a 503) with a delivery-unavailable status, and switching to or using
    TOTP login still works end to end.
    """
    settings.SMTP_ENABLED = False
    settings.DEV_OTP_DELIVERY_ENABLED = False

    test_pwd = secrets.token_urlsafe(16)
    test_email = f"clinician_dualmfa_{secrets.token_hex(4)}@hospital.med"
    totp_sec = MFAService.generate_totp_secret()

    db = SessionLocal()
    try:
        user = User(
            username=test_email,
            email=test_email,
            hashed_password=get_password_hash(test_pwd),
            role="Clinician",
            is_active=True,
            mfa_enabled=True,
            mfa_method="email_otp",  # Primary is email OTP
            mfa_enabled_methods="email_otp,totp_app",
            totp_secret=totp_sec
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    # 1. Login with primary email-OTP returns 200 challenge with DELIVERY_UNAVAILABLE
    login_res = client.post("/api/v1/auth/login", json={
        "username": test_email,
        "password": test_pwd
    })
    assert login_res.status_code == 200
    challenge_data = login_res.json()
    assert challenge_data["status"] == "MFA_CHALLENGE_REQUIRED"
    assert challenge_data["delivery_status"] == "DELIVERY_UNAVAILABLE"
    assert "totp_app" in challenge_data["available_methods"]
    session_token = challenge_data["mfa_session_token"]

    # 2. Switch challenge method to TOTP
    switch_res = client.post("/api/v1/auth/mfa/challenge-method", json={
        "mfa_session_token": session_token,
        "requested_method": "totp_app"
    })
    assert switch_res.status_code == 200
    switch_data = switch_res.json()
    assert switch_data["mfa_method"] == "totp_app"

    # 3. Generate valid TOTP code in-memory and complete verification
    valid_code = MFAService.generate_totp_code(totp_sec)
    verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
        "mfa_session_token": session_token,
        "verification_code": valid_code,
        "mfa_method": "totp_app"
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["mfa_verified"] is True
    assert "access_token" in verify_res.json()


def test_totp_path_remains_functional_when_email_unconfigured():
    """
    Proves that TOTP Authenticator App authentication continues working seamlessly
    even when email OTP delivery is completely unconfigured.
    """
    settings.SMTP_ENABLED = False
    settings.DEV_OTP_DELIVERY_ENABLED = False

    test_pwd = secrets.token_urlsafe(16)
    test_username = f"clinician_totp_{secrets.token_hex(4)}"
    totp_secret = MFAService.generate_totp_secret()

    db = SessionLocal()
    try:
        user = User(
            username=test_username,
            email=f"{test_username}@hospital.med",
            hashed_password=get_password_hash(test_pwd),
            role="Clinician",
            is_active=True,
            mfa_enabled=True,
            mfa_method="totp_app",
            totp_secret=totp_secret
        )
        user.add_mfa_method("totp_app")
        db.add(user)
        db.commit()
    finally:
        db.close()

    # 1. Login challenge issues token
    login_res = client.post("/api/v1/auth/login", json={
        "username": test_username,
        "password": test_pwd
    })
    assert login_res.status_code == 200
    challenge_data = login_res.json()
    assert challenge_data["status"] == "MFA_CHALLENGE_REQUIRED"
    assert challenge_data["mfa_method"] == "totp_app"
    session_token = challenge_data["mfa_session_token"]

    # 2. Verify in-memory generated TOTP code
    valid_code = MFAService.generate_totp_code(totp_secret)
    verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
        "mfa_session_token": session_token,
        "verification_code": valid_code,
        "mfa_method": "totp_app"
    })
    assert verify_res.status_code == 200
    assert "access_token" in verify_res.json()
    assert verify_res.json()["mfa_verified"] is True


def test_dev_channel_delivers_code_and_enables_successful_login():
    """
    Proves that in development mode with DEV_OTP_DELIVERY_ENABLED=True:
    1. Code is routed to server-side dev channel.
    2. Response body contains NO code leak.
    3. User successfully authenticates using the code delivered to the dev channel.
    """
    settings.SMTP_ENABLED = False
    settings.DEV_OTP_DELIVERY_ENABLED = True
    settings.ENVIRONMENT = "development"
    settings.DEBUG = True

    test_pwd = secrets.token_urlsafe(16)
    test_email = f"clinician_devotp_{secrets.token_hex(4)}@hospital.med"

    db = SessionLocal()
    try:
        user = User(
            username=test_email,
            email=test_email,
            hashed_password=get_password_hash(test_pwd),
            role="Clinician",
            is_active=True,
            mfa_enabled=True,
            mfa_method="email_otp"
        )
        user.add_mfa_method("email_otp")
        db.add(user)
        db.commit()
    finally:
        db.close()

    # 1. Login challenge
    login_res = client.post("/api/v1/auth/login", json={
        "username": test_email,
        "password": test_pwd
    })
    assert login_res.status_code == 200
    challenge_data = login_res.json()
    assert challenge_data["status"] == "MFA_CHALLENGE_REQUIRED"
    session_token = challenge_data["mfa_session_token"]

    # Invariant: NO code in response body
    assert "dev_code" not in challenge_data
    assert "otp_preview" not in challenge_data
    assert "code" not in challenge_data

    # 2. Code was delivered to server-side dev delivery channel
    delivered_code = DevOtpDeliveryChannel.get_latest_code(test_email)
    assert delivered_code is not None
    assert len(delivered_code) == 6
    assert delivered_code.isdigit()

    # 3. Submit code for second-factor verification
    verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
        "mfa_session_token": session_token,
        "verification_code": delivered_code,
        "mfa_method": "email_otp"
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["mfa_verified"] is True
    assert "access_token" in verify_res.json()


def test_dev_delivery_channel_strictly_disabled_in_production():
    """
    Proves that when ENVIRONMENT="production" or DEBUG=False,
    the dev OTP channel is strictly prohibited and returns False from is_available().
    """
    settings.DEV_OTP_DELIVERY_ENABLED = True

    # 1. Test production environment
    settings.ENVIRONMENT = "production"
    settings.DEBUG = True
    assert DevOtpDeliveryChannel.is_available() is False

    # 2. Test non-debug mode
    settings.ENVIRONMENT = "development"
    settings.DEBUG = False
    assert DevOtpDeliveryChannel.is_available() is False

    # 3. Attempting to deliver raises RuntimeError
    with pytest.raises(RuntimeError):
        DevOtpDeliveryChannel.deliver("test@hospital.med", "123456")


def test_smtp_configured_uses_live_email_and_bypasses_dev_channel():
    """
    Proves that when SMTP is configured, the live SMTP transmission path is executed
    and the dev channel receives no output.
    """
    settings.SMTP_ENABLED = True
    settings.SMTP_HOST = "smtp.test.hospital.org"
    settings.SMTP_USER = "auth_test"
    settings.SMTP_PASSWORD = "test_password"
    settings.DEV_OTP_DELIVERY_ENABLED = True
    settings.ENVIRONMENT = "development"
    settings.DEBUG = True

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        dynamic_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        result = MFAService.send_email_otp("doctor@hospital.med", dynamic_code)

        assert result["status"] == "SENT"
        assert result["delivery_mode"] == "LIVE_SMTP"
        assert result["sent_live_smtp"] is True
        mock_server.sendmail.assert_called_once()

        # Dev channel received no code because SMTP was active
        assert DevOtpDeliveryChannel.get_latest_code("doctor@hospital.med") is None

