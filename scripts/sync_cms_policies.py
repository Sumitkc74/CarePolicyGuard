#!/usr/bin/env python3
"""
CMS Policy Synchronization CLI.

Synchronizes the application database (carepolicyguard.db) with the canonical
verified Medicare policy catalog from app/data/policies/ and app/data/policies_extended/.

Usage:
    python scripts/sync_cms_policies.py
    python scripts/sync_cms_policies.py --force
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.services.cms_sync import sync_cms_policies


def main():
    parser = argparse.ArgumentParser(description="Synchronize CMS Medicare Policy Catalog")
    parser.add_argument("--force", action="store_true", help="Force refresh all criteria")
    args = parser.parse_args()

    print("[*] Starting policy catalog synchronization from verified JSON store...")
    db = SessionLocal()
    try:
        result = sync_cms_policies(db, force_update=args.force)
        print(f"[+] Policy Synchronization Complete at {result['sync_timestamp']}")
        print(f"    - Source:           {result['source']}")
        print(f"    - Policies Checked: {result['summary']['policies_checked']}")
        print(f"    - Policies Updated: {result['summary']['policies_updated']}")
        print(f"    - Policies Added:   {result['summary']['policies_added']}")
    except Exception as e:  # noqa: BLE001
        print(f"[-] Policy Sync Failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
