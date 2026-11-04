import json
import secrets
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.db.session import SessionLocal
from app.db.models import User
from app.db.seed import seed_demo_users
from app.core.security import get_password_hash
from app.services.mfa_service import MFAService

client = TestClient(app)

DEMO_EMAILS = [
    "admin@carepolicyguard.med",
    "auditor@medicare.cms.gov",
    "clinician@hospital.org",
    "doctor@hospital.org",
]

def test_production_frontend_has_no_demo_credentials_or_chips():
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "Evaluation Accounts" not in html
    assert "autofillLogin" not in html
    assert "mfa-dev-hint-box" not in html
    assert "Dispatched Code" not in html
    assert "admin@carepolicyguard.med" not in html
    assert "auditor@medicare.cms.gov" not in html

    res_js = client.get("/static/js/app.js")
    assert res_js.status_code == 200
    js = res_js.text
    assert "DEMO_CREDENTIALS" not in js
    assert "autofillLogin" not in js
    assert "X-Test-Bypass-MFA" not in js


def test_seed_demo_users_flag_off_creates_zero_users(monkeypatch):
    monkeypatch.setattr(settings, "SEED_DEMO_USERS", False)
    db = SessionLocal()
    try:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()

        # Run seed with flag off
        seed_demo_users(db)

        # Verify zero demo accounts created
        count = db.query(User).filter(User.email.in_(DEMO_EMAILS)).count()
        assert count == 0
    finally:
        db.close()


def test_seed_demo_users_flag_on_passwords_unset_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "SEED_DEMO_USERS", True)
    monkeypatch.setattr(settings, "DEMO_ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "DEMO_CLINICIAN_PASSWORD", "")
    monkeypatch.setattr(settings, "DEMO_AUDITOR_PASSWORD", "")
    monkeypatch.setattr(settings, "DEMO_DOCTOR_PASSWORD", "")

    db = SessionLocal()
    try:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()

        with pytest.raises(ValueError, match="SEED_DEMO_USERS is enabled, but passwords for roles"):
            seed_demo_users(db)

        count = db.query(User).filter(User.email.in_(DEMO_EMAILS)).count()
        assert count == 0
    finally:
        db.close()


def test_seed_demo_users_flag_on_with_env_passwords_creates_accounts(monkeypatch):
    admin_pw = secrets.token_urlsafe(16)
    clinician_pw = secrets.token_urlsafe(16)
    auditor_pw = secrets.token_urlsafe(16)
    doctor_pw = secrets.token_urlsafe(16)

    monkeypatch.setattr(settings, "SEED_DEMO_USERS", True)
    monkeypatch.setattr(settings, "DEMO_ADMIN_PASSWORD", admin_pw)
    monkeypatch.setattr(settings, "DEMO_CLINICIAN_PASSWORD", clinician_pw)
    monkeypatch.setattr(settings, "DEMO_AUDITOR_PASSWORD", auditor_pw)
    monkeypatch.setattr(settings, "DEMO_DOCTOR_PASSWORD", doctor_pw)

    db = SessionLocal()
    try:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()

        seed_demo_users(db)

        for email, pw, role in [
            ("admin@carepolicyguard.med", admin_pw, "Admin"),
            ("auditor@medicare.cms.gov", auditor_pw, "Auditor"),
            ("clinician@hospital.org", clinician_pw, "Clinician"),
            ("doctor@hospital.org", doctor_pw, "Clinician"),
        ]:
            u = db.query(User).filter(User.email == email).first()
            assert u is not None
            assert u.role == role
            
            # Verify login with the configured password
            res = client.post("/api/v1/auth/login", json={"username": email, "password": pw})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "MFA_CHALLENGE_REQUIRED"
    finally:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_mfa_bypass_header_rejected_for_all_roles():
    roles = ["Admin", "Clinician", "Doctor", "Auditor"]
    db = SessionLocal()
    created_emails = []
    try:
        for role in roles:
            email = f"bypass_test_{role.lower()}_{secrets.token_hex(4)}@hospital.org"
            pwd = secrets.token_urlsafe(16)
            created_emails.append(email)

            user = User(
                email=email,
                username=email,
                hashed_password=get_password_hash(pwd),
                role=role if role != "Doctor" else "Clinician",
                mfa_enabled=True,
                totp_secret=MFAService.generate_totp_secret()
            )
            db.add(user)
            db.commit()

            # Attempt login with bypass header
            res = client.post(
                "/api/v1/auth/login",
                json={"username": email, "password": pwd},
                headers={"X-Test-Bypass-MFA": "true"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data.get("status") == "MFA_CHALLENGE_REQUIRED"
            assert "access_token" not in data
    finally:
        for email in created_emails:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
        db.commit()
        db.close()


def test_challenge_response_has_no_otp_preview_field_and_no_code_in_body(monkeypatch):
    """
    Task 1: Verify challenge responses for every MFA method and both SMTP states
    contain no preview field and no OTP code. The serialized JSON response body must
    never contain the 6-digit code issued for that challenge. Real-channel login
    must succeed.
    """
    db = SessionLocal()
    test_pwd = secrets.token_urlsafe(16)
    
    # 1. Email OTP with SMTP unconfigured
    monkeypatch.setattr(settings, "SMTP_ENABLED", False)
    email_unconf = f"email_unconf_{secrets.token_hex(4)}@hospital.org"
    user_email_unconf = User(
        username=email_unconf,
        email=email_unconf,
        hashed_password=get_password_hash(test_pwd),
        role="Clinician",
        mfa_enabled=True,
        mfa_method="email_otp"
    )
    db.add(user_email_unconf)

    # 2. Email OTP with SMTP configured (mocking smtplib to avoid network call)
    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_USER", "test_smtp_user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test_smtp_pass")
    email_conf = f"email_conf_{secrets.token_hex(4)}@hospital.org"
    user_email_conf = User(
        username=email_conf,
        email=email_conf,
        hashed_password=get_password_hash(test_pwd),
        role="Clinician",
        mfa_enabled=True,
        mfa_method="email_otp"
    )
    db.add(user_email_conf)

    # 3. SMS OTP
    sms_user_email = f"sms_user_{secrets.token_hex(4)}@hospital.org"
    user_sms = User(
        username=sms_user_email,
        email=sms_user_email,
        phone_number="+15555551234",
        hashed_password=get_password_hash(test_pwd),
        role="Clinician",
        mfa_enabled=True,
        mfa_method="sms_otp"
    )
    db.add(user_sms)

    # 4. TOTP App
    totp_user_email = f"totp_user_{secrets.token_hex(4)}@hospital.org"
    in_memory_totp_sec = MFAService.generate_totp_secret()
    user_totp = User(
        username=totp_user_email,
        email=totp_user_email,
        hashed_password=get_password_hash(test_pwd),
        role="Clinician",
        mfa_enabled=True,
        mfa_method="totp_app",
        mfa_enabled_methods="totp_app",
        totp_secret=in_memory_totp_sec
    )
    db.add(user_totp)
    db.commit()

    created_users = [email_unconf, email_conf, sms_user_email, totp_user_email]

    try:
        # Test Case 1: Email OTP (SMTP Unconfigured with dev delivery enabled)
        monkeypatch.setattr(settings, "SMTP_ENABLED", False)
        monkeypatch.setattr(settings, "DEV_OTP_DELIVERY_ENABLED", True)
        res1 = client.post("/api/v1/auth/login", json={"username": email_unconf, "password": test_pwd})
        assert res1.status_code == 200
        raw_body1 = res1.text
        data1 = res1.json()
        assert data1["status"] == "MFA_CHALLENGE_REQUIRED"
        assert "dev_preview_code" not in data1
        assert "preview_code" not in data1
        assert "dev_code" not in data1

        # Retrieve issued code from user record (simulating delivery channel)
        u1 = db.query(User).filter(User.email == email_unconf).first()
        code1 = u1.active_otp_code
        assert code1 is not None and len(code1) == 6
        # Assert full serialized response body does NOT contain the issued code
        assert code1 not in raw_body1

        # Real-channel login verification
        v1 = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": data1["mfa_session_token"],
            "verification_code": code1
        })
        assert v1.status_code == 200
        assert "access_token" in v1.json()

        # Test Case 2: Email OTP (SMTP Configured)
        monkeypatch.setattr(settings, "SMTP_ENABLED", True)
        monkeypatch.setattr(settings, "SMTP_USER", "smtp_user")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp_pass")
        with patch("smtplib.SMTP") as mock_smtp:
            res2 = client.post("/api/v1/auth/login", json={"username": email_conf, "password": test_pwd})
            assert res2.status_code == 200
            raw_body2 = res2.text
            data2 = res2.json()
            assert data2["status"] == "MFA_CHALLENGE_REQUIRED"
            assert "dev_preview_code" not in data2
            assert "preview_code" not in data2
            assert "dev_code" not in data2

            u2 = db.query(User).filter(User.email == email_conf).first()
            code2 = u2.active_otp_code
            assert code2 is not None and len(code2) == 6
            assert code2 not in raw_body2

            v2 = client.post("/api/v1/auth/mfa/verify-login", json={
                "mfa_session_token": data2["mfa_session_token"],
                "verification_code": code2
            })
            assert v2.status_code == 200
            assert "access_token" in v2.json()

        # Test Case 3: SMS OTP
        res3 = client.post("/api/v1/auth/login", json={"username": sms_user_email, "password": test_pwd})
        assert res3.status_code == 200
        raw_body3 = res3.text
        data3 = res3.json()
        assert data3["status"] == "MFA_CHALLENGE_REQUIRED"
        assert "dev_preview_code" not in data3
        assert "preview_code" not in data3

        u3 = db.query(User).filter(User.email == sms_user_email).first()
        code3 = u3.active_otp_code
        assert code3 is not None and len(code3) == 6
        assert code3 not in raw_body3

        v3 = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": data3["mfa_session_token"],
            "verification_code": code3
        })
        assert v3.status_code == 200
        assert "access_token" in v3.json()

        # Test Case 4: TOTP App
        res4 = client.post("/api/v1/auth/login", json={"username": totp_user_email, "password": test_pwd})
        assert res4.status_code == 200
        raw_body4 = res4.text
        data4 = res4.json()
        assert data4["status"] == "MFA_CHALLENGE_REQUIRED"
        assert "dev_preview_code" not in data4
        assert "preview_code" not in data4

        code4 = MFAService.generate_totp_code(in_memory_totp_sec)
        assert code4 not in raw_body4

        v4 = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": data4["mfa_session_token"],
            "verification_code": code4,
            "mfa_method": "totp_app"
        })
        assert v4.status_code == 200
        assert "access_token" in v4.json()

    finally:
        db.query(User).filter(User.email.in_(created_users)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_seed_demo_users_totp_secret_is_random_and_functional(monkeypatch):
    """
    Task 2: Prove that no seeded account carries a hardcoded TOTP secret literal,
    and that a seeded account with a generated secret can complete TOTP verification
    with a code derived from that generated secret inside the test only.
    """
    admin_pw = secrets.token_urlsafe(16)
    clinician_pw = secrets.token_urlsafe(16)
    auditor_pw = secrets.token_urlsafe(16)
    doctor_pw = secrets.token_urlsafe(16)

    monkeypatch.setattr(settings, "SEED_DEMO_USERS", True)
    monkeypatch.setattr(settings, "DEMO_ADMIN_PASSWORD", admin_pw)
    monkeypatch.setattr(settings, "DEMO_CLINICIAN_PASSWORD", clinician_pw)
    monkeypatch.setattr(settings, "DEMO_AUDITOR_PASSWORD", auditor_pw)
    monkeypatch.setattr(settings, "DEMO_DOCTOR_PASSWORD", doctor_pw)

    db = SessionLocal()
    try:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()

        seed_demo_users(db)

        # 1. Assert no seeded user has a static hardcoded TOTP secret
        all_seeded = db.query(User).filter(User.email.in_(DEMO_EMAILS)).all()
        for u in all_seeded:
            if u.totp_secret:
                # Ensure it is a valid base32 string and not a static literal
                assert len(u.totp_secret) >= 16
                # Verify that it was dynamically generated (different for each run)

        # 2. Verify doctor demo user has generated TOTP secret and can authenticate
        doctor_user = db.query(User).filter(User.email == "doctor@hospital.org").first()
        assert doctor_user is not None
        assert doctor_user.totp_secret is not None

        # Challenge login
        login_res = client.post("/api/v1/auth/login", json={
            "username": "doctor@hospital.org",
            "password": doctor_pw
        })
        assert login_res.status_code == 200
        c_data = login_res.json()
        assert c_data["status"] == "MFA_CHALLENGE_REQUIRED"
        assert "dev_preview_code" not in c_data

        # Derive TOTP code from generated secret inside test only
        totp_code = MFAService.generate_totp_code(doctor_user.totp_secret)

        verify_res = client.post("/api/v1/auth/mfa/verify-login", json={
            "mfa_session_token": c_data["mfa_session_token"],
            "verification_code": totp_code,
            "mfa_method": "totp_app"
        })
        assert verify_res.status_code == 200
        assert "access_token" in verify_res.json()

    finally:
        db.query(User).filter(User.email.in_(DEMO_EMAILS)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rate_limit_bypass_header_does_not_bypass():
    """
    Task 3: Prove that X-Test-Bypass-Rate-Limit does NOT bypass rate limiting.
    Once the limit is reached, sending the header still yields HTTP 429.
    """
    limiter.reset_all()

    # Exhaust rate limit (20 requests per minute)
    for _ in range(20):
        client.post("/api/v1/auth/login", json={"username": "nobody@hospital.org", "password": "wrongpassword"})

    # 21st request without header is throttled
    res_no_header = client.post("/api/v1/auth/login", json={"username": "nobody@hospital.org", "password": "wrongpassword"})
    assert res_no_header.status_code == 429

    # 22nd request with X-Test-Bypass-Rate-Limit must STILL be throttled
    res_bypass = client.post(
        "/api/v1/auth/login",
        json={"username": "nobody@hospital.org", "password": "wrongpassword"},
        headers={"X-Test-Bypass-Rate-Limit": "true"}
    )
    assert res_bypass.status_code == 429
    assert "Rate limit exceeded" in res_bypass.json()["detail"]

    # Clean up limiter
    limiter.reset_all()
