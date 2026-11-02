import secrets
import pytest
from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import get_password_hash

client = TestClient(app)

def test_multi_device_session_revocation():
    db = SessionLocal()
    test_email = f"clinician.revocation.{secrets.token_hex(6)}@hospital.org"
    in_memory_pass = secrets.token_urlsafe(16)
    user = User(
        username=test_email,
        email=test_email,
        hashed_password=get_password_hash(in_memory_pass),
        role="Clinician",
        mfa_enabled=False,
    )
    db.add(user)
    db.commit()

    try:
        # 1. Doctor logs in from Device A (e.g. Hospital Desktop)
        headers_device_a = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hospital Desktop"}
        res_a = client.post("/api/v1/auth/login", json={
            "username": test_email,
            "password": in_memory_pass
        }, headers=headers_device_a)
        assert res_a.status_code == 200
        token_a = res_a.json()["access_token"]

        # 2. Doctor logs in from Device B (e.g. iPhone on Hospital Rounds)
        headers_device_b = {"User-Agent": "CarePolicyGuard Mobile/1.0 (iOS; iPhone 15 Pro)"}
        res_b = client.post("/api/v1/auth/login", json={
            "username": test_email,
            "password": in_memory_pass
        }, headers=headers_device_b)
        assert res_b.status_code == 200
        token_b = res_b.json()["access_token"]

        # Both devices can access protected clinical data simultaneously
        auth_a = {"Authorization": f"Bearer {token_a}"}
        auth_b = {"Authorization": f"Bearer {token_b}"}

        sess_res_a = client.get("/api/v1/auth/sessions", headers=auth_a)
        assert sess_res_a.status_code == 200
        sessions = sess_res_a.json()
        assert len(sessions) >= 2

        # Find Device B's session ID from Device A's screen
        device_b_sess = next((s for s in sessions if "iPhone" in s["device_name"]), None)
        assert device_b_sess is not None
        assert device_b_sess["is_current"] is False

        # 3. Doctor on Device A remotely terminates Device B's session
        revoke_res = client.post(
            f"/api/v1/auth/sessions/{device_b_sess['session_id']}/revoke",
            headers=auth_a
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "SUCCESS_REVOKED"

        # 4. Device A is STILL active and functioning
        check_a = client.get("/api/v1/auth/sessions", headers=auth_a)
        assert check_a.status_code == 200

        # 5. Device B tries to make a request -> Immediately REJECTED with 401
        check_b = client.get("/api/v1/auth/sessions", headers=auth_b)
        assert check_b.status_code == 401
        assert "Session has been terminated" in check_b.json()["detail"]
    finally:
        u = db.query(User).filter(User.email == test_email).first()
        if u:
            db.delete(u)
            db.commit()
        db.close()
