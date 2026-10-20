#!/usr/bin/env python3
"""
Automated CMS Policy Sync Script (Method 2)
Periodically connects to the CMS Medicare Coverage Database (MCD),
detects updated NCDs/LCDs, and synchronizes the local carepolicyguard.db.

Usage:
    python scripts/sync_cms_policies.py
    python scripts/sync_cms_policies.py --force
"""

import sys
import os
import argparse
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.services.cms_sync import sync_cms_policies

def main():
    parser = argparse.ArgumentParser(description="Automated CMS Medicare Policy Synchronizer")
    parser.add_argument("--force", action="store_true", help="Force refresh all criteria regardless of timestamp")
    args = parser.parse_args()

    print("[*] Starting Automated CMS Medicare Coverage Database (MCD) Sync...")
    db = SessionLocal()
    try:
        result = sync_cms_policies(db, force_update=args.force)
        print(f"[+] CMS Synchronization Complete at {result['sync_timestamp']}")
        print(f"    - Policies Checked: {result['summary']['policies_checked']}")
        print(f"    - Policies Updated: {result['summary']['policies_updated']}")
        print(f"    - Policies Added:   {result['summary']['policies_added']}")
        print("\nPolicy Details:")
        for d in result["details"]:
            action = d["action"]
            pid = d["policy_id"]
            msg = d["message"]
            print(f"    [{action}] {pid}: {msg}")
    except Exception as e:
        print(f"[-] CMS Sync Failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()

