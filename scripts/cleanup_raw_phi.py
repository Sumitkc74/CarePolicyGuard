"""
CarePolicyGuard One-Time Database PHI Sanitization & Cleanup Utility.
HIPAA Safe Harbor & Data Minimization (45 CFR § 164.502(b), § 164.514).

Iterates through all historical AdjudicationLog records in the database:
1. Sanitizes full_ehr_text and sanitized_ehr_preview using regex/NLP PHI masking.
2. Ensures JSON fields contain only sanitized narratives.
3. Preserves existing case records, SHA-256 audit hashes, determination stages,
   and clinician sign-offs without silent auto-wipe or data destruction.
"""

import sys
import os
import json
from typing import Dict, Any, Tuple

# Add root directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.db.models import AdjudicationLog
from app.core.security import sanitize_phi


def cleanup_raw_phi_in_database(dry_run: bool = False) -> Dict[str, Any]:
    db = SessionLocal()
    total_inspected = 0
    total_updated = 0
    total_redactions_applied = 0

    try:
        logs = db.query(AdjudicationLog).all()
        total_inspected = len(logs)

        for log in logs:
            updated = False

            # 1. Sanitize full_ehr_text
            if log.full_ehr_text:
                sanitized_text = sanitize_phi(log.full_ehr_text)
                if sanitized_text != log.full_ehr_text:
                    total_redactions_applied += 1
                    if not dry_run:
                        log.full_ehr_text = sanitized_text
                    updated = True

            # 2. Sanitize sanitized_ehr_preview
            if log.sanitized_ehr_preview:
                preview_sanitized = sanitize_phi(log.sanitized_ehr_preview)
                if preview_sanitized != log.sanitized_ehr_preview:
                    total_redactions_applied += 1
                    if not dry_run:
                        log.sanitized_ehr_preview = preview_sanitized
                    updated = True

            # 3. Sanitize narrative in full_adjudication_json
            if log.full_adjudication_json:
                try:
                    data = json.loads(log.full_adjudication_json)
                    if "sanitized_ehr_text" in data and data["sanitized_ehr_text"]:
                        s_text = sanitize_phi(data["sanitized_ehr_text"])
                        if s_text != data["sanitized_ehr_text"]:
                            data["sanitized_ehr_text"] = s_text
                            total_redactions_applied += 1
                            if not dry_run:
                                log.full_adjudication_json = json.dumps(data)
                            updated = True
                except Exception:
                    pass

            if updated:
                total_updated += 1

        if not dry_run and total_updated > 0:
            db.commit()

        return {
            "status": "success",
            "dry_run": dry_run,
            "total_inspected": total_inspected,
            "total_updated": total_updated,
            "total_redactions_applied": total_redactions_applied
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    print(f"[*] Starting PHI Cleanup Script (dry_run={is_dry})...")
    result = cleanup_raw_phi_in_database(dry_run=is_dry)
    print(f"[+] Cleanup completed: {result}")
