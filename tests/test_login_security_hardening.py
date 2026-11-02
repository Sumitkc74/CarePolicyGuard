import secrets
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import User
from app.db.seed import seed_demo_users
from app.core.security import get_password_hash

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
                totp_secret="JBSWY3DPEHPK3PXP"
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
