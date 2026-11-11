"""
Database User Audit & Bulk Account Purge Utility.

Finds and removes orphaned test/bulk accounts from previous automated test runs,
preserving seeded demo accounts and real accounts.
Can operate on carepolicyguard.db or test_ci.db.
"""
import sqlite3
import sys
from pathlib import Path

PRESERVED_USERNAMES = {
    "admin@carepolicyguard.med",
    "auditor@medicare.cms.gov",
    "clinician@hospital.org",
    "doctor@hospital.org",
    "demo_eval_admin@carepolicyguard.med",
    "super_admin_0a684f@hospital.org"
}

def purge_bulk_accounts(db_path: str) -> dict:
    p = Path(db_path)
    if not p.exists():
        return {"error": f"Database file not found: {db_path}"}

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Pre-count by role
    cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
    before_counts = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM users")
    total_before = cur.fetchone()[0]

    # Find users with active foreign key references
    cur.execute("SELECT DISTINCT user_id FROM user_sessions WHERE user_id IS NOT NULL")
    session_user_ids = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT DISTINCT user_id FROM adjudication_logs WHERE user_id IS NOT NULL")
    adj_user_ids = {r[0] for r in cur.fetchall()}

    # Also check if assigned_to_user_id column exists in deferral_queue_records
    deferral_cols = [r[1] for r in cur.execute("PRAGMA table_info(deferral_queue_records)").fetchall()]
    deferral_user_ids = set()
    if "assigned_to_user_id" in deferral_cols:
        cur.execute("SELECT DISTINCT assigned_to_user_id FROM deferral_queue_records WHERE assigned_to_user_id IS NOT NULL")
        deferral_user_ids = {r[0] for r in cur.fetchall()}

    referenced_user_ids = session_user_ids | adj_user_ids | deferral_user_ids

    # Query all users
    cur.execute("SELECT id, username, role, is_demo_user, is_bootstrap FROM users")
    all_users = cur.fetchall()

    deleted_users = []
    for uid, uname, role, is_demo, is_boot in all_users:
        if uname in PRESERVED_USERNAMES or is_demo or is_boot:
            continue
        # If user is referenced in active sessions, logs, or deferrals, skip deleting
        if uid in referenced_user_ids:
            continue
        deleted_users.append((uid, uname))

    for uid, _ in deleted_users:
        # Clean user_sessions first if any
        cur.execute("DELETE FROM user_sessions WHERE user_id = ?", (uid,))
        cur.execute("DELETE FROM users WHERE id = ?", (uid,))

    con.commit()

    # Post-count by role
    cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
    after_counts = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM users")
    total_after = cur.fetchone()[0]

    con.close()

    return {
        "db_path": db_path,
        "total_before": total_before,
        "total_after": total_after,
        "deleted_count": len(deleted_users),
        "before_by_role": before_counts,
        "after_by_role": after_counts
    }

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "carepolicyguard.db"
    res = purge_bulk_accounts(target)
    print(res)
