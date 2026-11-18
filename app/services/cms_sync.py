"""
CMS Policy Synchronization Service.

Synchronizes the application database (carepolicyguard.db) with the canonical
verified Medicare Coverage Determination JSON definitions stored in
app/data/policies/ and app/data/policies_extended/.

Single Source of Truth:
Canonical DeclarativePolicyEngine JSON store, seeded via app.db.seed::seed_policies.
Zero hardcoded transmittal feeds or unverified external polling claims.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import MedicarePolicy
from app.db.seed import seed_policies
from app.services.declarative_engine import DeclarativePolicyEngine

logger = logging.getLogger("carepolicyguard.cms_sync")

_LAST_SYNC_META: dict[str, Any] = {
    "last_sync_timestamp": None,
    "last_status": "NEVER_RUN",
    "policies_checked": 0,
    "policies_updated": 0,
    "policies_added": 0,
    "source": "Canonical Declarative Policy Store (CMS Verified)"
}


def sync_cms_policies(db: Session, force_update: bool = False) -> dict[str, Any]:
    """
    Synchronizes local database policies and criteria from the verified declarative
    policy store using the authoritative seed_policies routine.
    """
    now = datetime.now(UTC)
    logger.info("[*] Starting policy catalog synchronization from verified JSON store...")

    pre_count = db.query(MedicarePolicy).count()

    # Authoritative load path
    seed_policies(db)

    post_count = db.query(MedicarePolicy).count()
    all_declarative = DeclarativePolicyEngine.get_all_policies()
    policies_checked = len(all_declarative)
    policies_added = max(0, post_count - pre_count)
    policies_updated = policies_checked - policies_added

    details = []
    for pol in all_declarative:
        details.append({
            "policy_id": pol.policy_id,
            "action": "SYNCED",
            "message": f"Synchronized {len(pol.criteria)} criteria from verified declarative store."
        })

    _LAST_SYNC_META["last_sync_timestamp"] = now.isoformat()
    _LAST_SYNC_META["last_status"] = "SUCCESS"
    _LAST_SYNC_META["policies_checked"] = policies_checked
    _LAST_SYNC_META["policies_updated"] = policies_updated
    _LAST_SYNC_META["policies_added"] = policies_added

    logger.info(
        f"[+] Policy sync complete. Checked: {policies_checked}, "
        f"Updated: {policies_updated}, Added: {policies_added}."
    )

    return {
        "status": "success",
        "sync_timestamp": _LAST_SYNC_META["last_sync_timestamp"],
        "source": _LAST_SYNC_META["source"],
        "summary": {
            "policies_checked": policies_checked,
            "policies_updated": policies_updated,
            "policies_added": policies_added
        },
        "details": details
    }


def get_sync_status() -> dict[str, Any]:
    """Returns the latest synchronization status and metadata."""
    return _LAST_SYNC_META
