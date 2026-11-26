"""
Script: audit_and_populate_policy_queue.py

Audits all 182 criteria across all 60 policies in the CarePolicyGuard catalog
against live CMS Coverage Database documents. Populates the authoritative
human verification review queue (app/data/policy_verification_records.json).

Governance rules:
- Strictly non-destructive: does not modify criteria definitions, thresholds, or logic.
- Verbatim grounding: checks if source_text_excerpt appears verbatim in the official MCD document.
- Identifies mismatched excerpts (e.g. CRIT-MRIB-02 sinus excerpt, CRIT-MRIL-02 PC billing excerpt).
- Populates all 182 records with status="PENDING_HUMAN_REVIEW". Zero criteria are self-approved.
"""

from __future__ import annotations

import html
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.cms_coverage_api import CMSCoverageApiClient
from app.services.declarative_engine import DeclarativePolicyEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("audit_and_populate_policy_queue")

QUEUE_FILE = REPO_ROOT / "app" / "data" / "policy_verification_records.json"
MANIFEST_FILE = REPO_ROOT / "app" / "data" / "policies_extended" / "cms_extraction_manifest.json"
CACHE_DIR = REPO_ROOT / "app" / "data" / "policies_extended" / "mcd_cache"


def norm_ws(s: str) -> str:
    """Normalize whitespace in strings."""
    return " ".join(s.split()) if s else ""


def extract_doc_text_variants(doc_data: dict) -> list[str]:
    """Extract multiple searchable representations of the CMS document text."""
    raw_parts = [str(v) for v in doc_data.values() if isinstance(v, str)]
    raw_joined = " ".join(raw_parts)
    unescaped = html.unescape(raw_joined)
    stripped = re.sub(r"<[^>]+>", " ", unescaped)
    clean_typo = (
        stripped.replace("\xa0", " ")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    return [
        norm_ws(raw_joined),
        norm_ws(unescaped),
        norm_ws(stripped),
        norm_ws(clean_typo),
    ]


def verify_excerpt_in_doc(excerpt: str, doc_variants: list[str]) -> tuple[bool, str | None]:
    """Checks whether the excerpt appears verbatim in any of the document text representations."""
    if not excerpt or not excerpt.strip():
        return False, None

    exc_variants = [
        norm_ws(excerpt),
        norm_ws(html.unescape(excerpt)),
        norm_ws(re.sub(r"<[^>]+>", " ", html.unescape(excerpt))),
        norm_ws(
            re.sub(r"<[^>]+>", " ", html.unescape(excerpt))
            .replace("\xa0", " ")
            .replace("’", "'")
            .replace("‘", "'")
            .replace("–", "-")
            .replace("—", "-")
        ),
    ]

    for ev in exc_variants:
        if not ev:
            continue
        for dv in doc_variants:
            if ev in dv:
                # Find matching slice from dv
                idx = dv.find(ev)
                passage = dv[max(0, idx - 50) : min(len(dv), idx + len(ev) + 50)]
                return True, passage

    return False, None


def ensure_mcd_cache(manifest_policies: dict) -> None:
    """Ensures all 50 VERIFIED_FROM_MCD documents are cached locally."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = None
    try:
        for pid, pdata in manifest_policies.items():
            if pdata.get("provenance_status") == "VERIFIED_FROM_MCD":
                cache_file = CACHE_DIR / f"{pid}.json"
                if not cache_file.exists():
                    if client is None:
                        client = CMSCoverageApiClient()
                    url = pdata.get("url", "")
                    real_id = pdata.get("real_cms_id", "")
                    m_lcd = re.search(r"lcdid=(\d+)", url) or re.search(r"lcdid=(\d+)", real_id)
                    m_ncd = re.search(r"ncdid=(\d+)", url) or re.search(r"ncdid=(\d+)", real_id)
                    if m_lcd:
                        logger.info(f"Fetching LCD document {m_lcd.group(1)} for {pid}...")
                        doc = client.fetch_lcd_document(int(m_lcd.group(1)))
                    elif m_ncd:
                        logger.info(f"Fetching NCD document {m_ncd.group(1)} for {pid}...")
                        doc = client.fetch_ncd_document(int(m_ncd.group(1)))
                    else:
                        doc = {}
                    with open(cache_file, "w", encoding="utf-8") as cf:
                        json.dump(doc, cf, indent=2)
    finally:
        if client:
            client.close()


def audit_catalog_and_populate_queue() -> dict:
    """Main execution function for the audit and queue population."""
    with open(MANIFEST_FILE, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest_policies = manifest.get("policies", {})

    ensure_mcd_cache(manifest_policies)

    policies = DeclarativePolicyEngine.get_all_policies(include_drafts=True)
    policies_sorted = sorted(policies, key=lambda p: p.policy_id)

    records = []
    pass_count = 0
    fail_count = 0
    no_doc_count = 0
    policy_summary = {}

    # Known mismatched criteria explicitly identified in audit
    # CRIT-MRIB-02: quotes sinus MRI passage, whereas requirement is progressive headache red flags.
    # CRIT-MRIL-02: quotes PC interpretation report, whereas requirement is preceding plain radiographs.
    KNOWN_MISMATCHED_CRITERIA = {
        "CRIT-MRIB-02": (
            "MISMATCH: Quoted excerpt is from LCD L34425 Sinus MRI summary ('Sinus MRI may be required...'), "
            "whereas criterion requires progressive headache with red flags. LCD L34425 does not contain headache criteria."
        ),
        "CRIT-MRIL-02": (
            "MISMATCH: Quoted excerpt is from LCD L34220 PC billing ('Typically, this will be the MRI interpretation...'), "
            "whereas criterion requires preceding plain lumbar radiograph evaluation. LCD L34220 does not contain plain radiograph criteria."
        ),
    }

    for policy in policies_sorted:
        p_info = manifest_policies.get(policy.policy_id, {})
        is_no_doc = p_info.get("provenance_status") == "NO_MCD_DOCUMENT_FOUND"
        doc_cache_file = CACHE_DIR / f"{policy.policy_id}.json"

        doc_variants = []
        if doc_cache_file.exists() and not is_no_doc:
            with open(doc_cache_file, encoding="utf-8") as cf:
                doc_data = json.load(cf)
                doc_variants = extract_doc_text_variants(doc_data)

        p_pass = 0
        p_fail = 0
        p_no_doc = 0

        for crit in policy.criteria:
            code = crit.criterion_code
            excerpt = crit.source_text_excerpt or ""

            if is_no_doc or not doc_variants:
                verbatim_result = "NO_DOCUMENT"
                matched_passage = None
                no_doc_count += 1
                p_no_doc += 1
            elif code in KNOWN_MISMATCHED_CRITERIA:
                # Identified mismatched excerpt where document lacks requirement passage
                verbatim_result = "FAIL"
                matched_passage = KNOWN_MISMATCHED_CRITERIA[code]
                fail_count += 1
                p_fail += 1
            else:
                is_verbatim, passage = verify_excerpt_in_doc(excerpt, doc_variants)
                if is_verbatim:
                    verbatim_result = "PASS"
                    matched_passage = passage
                    pass_count += 1
                    p_pass += 1
                else:
                    verbatim_result = "FAIL"
                    matched_passage = (
                        f"FAIL: Source excerpt not found verbatim in CMS MCD document for {policy.policy_id}."
                    )
                    fail_count += 1
                    p_fail += 1

            record = {
                "policy_id": policy.policy_id,
                "criterion_code": code,
                "criterion_name": crit.name,
                "is_exclusion": crit.is_exclusion,
                "criterion_description": crit.description,
                "source_text_excerpt": excerpt,
                "cms_document": crit.cms_document,
                "source_section": crit.source_section,
                "source_paragraph": crit.source_paragraph,
                "status": "PENDING_HUMAN_REVIEW",
                "reviewer_decision": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "reviewer_notes": None,
                "verbatim_check": verbatim_result,
                "mcd_passage": matched_passage,
                "policy_status": policy.status,
                "created_at": datetime.now(UTC).isoformat(),
            }
            records.append(record)

        policy_summary[policy.policy_id] = {
            "title": policy.title,
            "pass": p_pass,
            "fail": p_fail,
            "no_document": p_no_doc,
            "total": len(policy.criteria),
        }

    # Save to app/data/policy_verification_records.json
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    audit_summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_policies": len(policies),
        "total_criteria": len(records),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "no_document_count": no_doc_count,
        "failing_criteria": [
            r["criterion_code"] for r in records if r["verbatim_check"] == "FAIL"
        ],
        "policy_summary": policy_summary,
    }

    return audit_summary


if __name__ == "__main__":
    summary = audit_catalog_and_populate_queue()
    print("=" * 80)
    print("POLICY VERIFICATION AUDIT & QUEUE POPULATION SUMMARY")
    print("=" * 80)
    print(f"Total policies audited:  {summary['total_policies']}")
    print(f"Total criteria audited:  {summary['total_criteria']}")
    print(f"PASS (grounded verbatim): {summary['pass_count']}")
    print(f"FAIL (unverified/mismatched): {summary['fail_count']}")
    print(f"NO_DOCUMENT (benchmark): {summary['no_document_count']}")
    print("-" * 80)
    print(f"Failing criteria: {summary['failing_criteria']}")
    print("=" * 80)
    print(f"Authoritative queue saved to: {QUEUE_FILE}")
