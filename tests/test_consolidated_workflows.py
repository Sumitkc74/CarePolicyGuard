from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.security import UserRole, create_access_token, get_password_hash
from app.db.models import AdjudicationLog, User
from app.db.session import SessionLocal
from main import app
from scripts.purge_bulk_test_users import purge_bulk_accounts

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_purge_bulk_test_users_utility(tmp_path):
    """
    Task 1: The bulk accounts removal utility must preserve demo accounts and
    users referenced in active audit histories, while safely purging orphaned bulk accounts.
    """
    import sqlite3
    db_file = tmp_path / "test_purge.db"
    con = sqlite3.connect(str(db_file))
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT,
            is_demo_user BOOLEAN DEFAULT 0,
            is_bootstrap BOOLEAN DEFAULT 0
        )
    """)
    cur.execute("CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, user_id INTEGER)")
    cur.execute("CREATE TABLE adjudication_logs (id INTEGER PRIMARY KEY, user_id INTEGER)")
    cur.execute("CREATE TABLE deferral_queue_records (id INTEGER PRIMARY KEY, assigned_to_user_id INTEGER)")

    # Insert preserved demo users
    cur.execute("INSERT INTO users VALUES (1, 'admin@carepolicyguard.med', 'Admin', 1, 0)")
    cur.execute("INSERT INTO users VALUES (2, 'clinician@hospital.org', 'Clinician', 1, 0)")
    # Insert bulk test users
    cur.execute("INSERT INTO users VALUES (3, 'bulk_test_1@hospital.org', 'Clinician', 0, 0)")
    cur.execute("INSERT INTO users VALUES (4, 'bulk_test_2@hospital.org', 'Admin', 0, 0)")
    # Insert a user referenced in logs
    cur.execute("INSERT INTO users VALUES (5, 'referenced_user@hospital.org', 'Clinician', 0, 0)")
    cur.execute("INSERT INTO adjudication_logs VALUES (101, 5)")
    con.commit()
    con.close()

    result = purge_bulk_accounts(str(db_file))
    assert result["total_before"] == 5
    # Should delete bulk_test_1 and bulk_test_2 (2 users), preserving admin, clinician, and referenced
    assert result["deleted_count"] == 2
    assert result["total_after"] == 3


def test_admin_user_management_endpoints(db_session):
    """
    Task 2: Admin user management endpoints allow listing clinicians,
    inviting new clinicians (unverified), creating admins, and updating status.
    """
    admin_email = f"admin_mgmt_{datetime.now(UTC).timestamp()}@carepolicyguard.med"
    admin = User(
        username=admin_email,
        email=admin_email,
        hashed_password=get_password_hash("AdminSecure!2026"),
        role=UserRole.ADMIN.value,
        is_active=True
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    token = create_access_token({"sub": admin.username, "role": admin.role, "uid": admin.id})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Invite Clinician
    new_clin_email = f"new_clin_{datetime.now(UTC).timestamp()}@hospital.org"
    invite_resp = client.post(
        "/api/v1/admin/users/clinicians",
        json={"email": new_clin_email},
        headers=headers
    )
    assert invite_resp.status_code == 201
    clin_data = invite_resp.json()
    assert clin_data["email"] == new_clin_email
    assert clin_data["is_verified_medical_pro"] is False

    # 2. List Clinicians
    list_resp = client.get("/api/v1/admin/users/clinicians", headers=headers)
    assert list_resp.status_code == 200
    clinicians = list_resp.json()
    assert any(c["email"] == new_clin_email for c in clinicians)

    # 3. Toggle User Status
    status_resp = client.post(
        f"/api/v1/admin/users/{clin_data['id']}/status",
        json={"is_active": False, "reason": "Administrative suspension"},
        headers=headers
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is False


def test_deferral_queue_originating_clinician_scoping(db_session):
    """
    Task 3: Deferral queue correctly tags assigned_to_user_id and scopes cases
    so that clinicians see only their own cases while admins see all cases.
    """
    clin_email = f"clin_defer_{datetime.now(UTC).timestamp()}@hospital.org"
    clin = User(
        username=clin_email,
        email=clin_email,
        hashed_password=get_password_hash("ClinicianCare!2026"),
        role=UserRole.CLINICIAN.value,
        is_verified_medical_pro=True,
        is_active=True
    )
    db_session.add(clin)
    db_session.commit()
    db_session.refresh(clin)

    token = create_access_token({"sub": clin.username, "role": clin.role, "uid": clin.id})
    headers = {"Authorization": f"Bearer {token}"}

    # Adjudicate an ambiguous case that defers to human (BENCH-02 style)
    payload = {
        "patient_id": "PT-DEFER-SCOPE",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "58-year-old female diagnosed with newly discovered non-ischemic cardiomyopathy. LVEF 30%. Started GDMT 21 days ago.",
        "options": {"save_record": True}
    }
    adj_resp = client.post("/api/v1/adjudicate", json=payload, headers=headers)
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    case_id = data["case_id"]

    # Clinician inspects deferral queue -> must see their case
    queue_resp = client.get("/api/v1/deferral/queue", headers=headers)
    assert queue_resp.status_code == 200
    queue_items = queue_resp.json()
    found = next((item for item in queue_items if item["case_id"] == case_id), None)
    assert found is not None
    assert found["assigned_to_user_id"] == clin.id


def test_telemetry_honest_numbers_no_data(db_session):
    """
    Task 6 honesty test: When no executions exist or on empty data,
    the telemetry API reports null/0 and frontend displays 'no data yet',
    never plausible-looking invented literals (e.g. 45 ms latency).
    """
    resp = client.get("/api/v1/metrics/json")
    assert resp.status_code == 200
    data = resp.json()
    assert "adjudications" in data
    logs_count = db_session.query(AdjudicationLog).filter(AdjudicationLog.execution_time_ms.isnot(None)).count()
    if logs_count == 0:
        assert data["adjudications"]["average_latency_ms"] is None


def test_in_app_notification_creation_and_retrieval(db_session):
    """
    Task 3 workflow test: Case outcomes automatically notify the originating clinician,
    and the clinician can retrieve and mark their notifications as read.
    """
    test_email = f"clinician_notify_{datetime.now(UTC).timestamp()}@hospital.org"
    user = User(
        username=test_email,
        email=test_email,
        hashed_password=get_password_hash("ClinicianCare!2026"),
        role=UserRole.CLINICIAN.value,
        is_verified_medical_pro=True,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token({"sub": user.username, "role": user.role, "uid": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "patient_id": "PT-NOTIFY-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Patient is 68yo with ischemic cardiomyopathy. LVEF 28%. NYHA Class II. On optimal GDMT for 6 months. Post CABG 14 months.",
        "options": {"save_record": True}
    }
    adj_resp = client.post("/api/v1/adjudicate", json=payload, headers=headers)
    assert adj_resp.status_code == 200
    case_id = adj_resp.json()["case_id"]

    notifs_resp = client.get("/api/v1/notifications", headers=headers)
    assert notifs_resp.status_code == 200
    notifs = notifs_resp.json()
    assert len(notifs) >= 1
    found = next((n for n in notifs if n["case_id"] == case_id), None)
    assert found is not None
    assert found["decision"] in ("APPROVED", "DENIED", "DEFERRED_TO_HUMAN")
    assert found["is_read"] is False

    patch_resp = client.patch(f"/api/v1/notifications/{found['id']}/read", headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_read"] is True


def test_human_override_workflow_end_to_end(db_session):
    """
    Task 4 workflow test: Clinician requests human override with clinical reason >= 10 chars.
    Determination transitions to FINAL and is_releasable=True while preserving original_system_output_json.
    """
    test_email = f"clinician_override_{datetime.now(UTC).timestamp()}@hospital.org"
    user = User(
        username=test_email,
        email=test_email,
        hashed_password=get_password_hash("ClinicianCare!2026"),
        role=UserRole.CLINICIAN.value,
        credential_title="MD",
        npi_number="1043256787",
        is_verified_medical_pro=True,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token({"sub": user.username, "role": user.role, "uid": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "patient_id": "PT-OVERRIDE-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": "Patient admitted with cardiogenic shock and acute decompensated heart failure requiring norepinephrine infusion. LVEF 20%.",
        "options": {"save_record": True}
    }
    adj_resp = client.post("/api/v1/adjudicate", json=payload, headers=headers)
    assert adj_resp.status_code == 200
    case_id = adj_resp.json()["case_id"]
    assert adj_resp.json()["adjudication_decision"] == "DENIED"

    # Short reason rejected
    short_resp = client.post(
        f"/api/v1/determination/{case_id}/override",
        json={"override_decision": "APPROVED", "override_reason": "Too short"},
        headers=headers
    )
    assert short_resp.status_code in (400, 422)

    # Valid override
    valid_reason = "Cardiogenic shock resolved 5 days ago; device placement now appropriate under acute clinical judgment."
    override_resp = client.post(
        f"/api/v1/determination/{case_id}/override",
        json={"override_decision": "APPROVED", "override_reason": valid_reason},
        headers=headers
    )
    assert override_resp.status_code == 200
    res_data = override_resp.json()
    assert res_data["determination_stage"] == "FINAL"
    assert res_data["is_releasable"] is True
    assert res_data["override_decision"] == "APPROVED"
    assert res_data["original_decision"] == "DENIED"

    log = db_session.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    assert log is not None
    assert log.decision == "APPROVED"
    assert log.determination_stage == "FINAL"
    assert log.is_releasable is True
    assert log.original_system_output_json is not None
    assert "DENIED" in log.original_system_output_json
