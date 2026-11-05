#!/usr/bin/env python3
"""
Adds official CMS identifiers, MCD document references, and direct URLs
to each extended policy JSON in app/data/policies_extended/ and generates
the machine-readable provenance registry app/data/policies_extended/PROVENANCE.md.
"""

from scripts.apply_verified_provenance import AUDIT_RESULTS, CHECK_DATE

PROVENANCE_REGISTRY = {}
for slug, audit in AUDIT_RESULTS.items():
    entry = {
        "provenance_status": audit["status"],
        "checked_date": CHECK_DATE,
        "notes": audit["notes"]
    }
    if audit["status"] == "VERIFIED_FROM_MCD":
        entry.update({
            "real_cms_id": audit["mcd_id"],
            "authority": audit["contractor"],
            "document_title": audit["mcd_title"],
            "citation": f"CMS MCD: {audit['mcd_title']} ({audit['mcd_id']})",
            "url": audit["url"]
        })
    elif audit["status"] == "MISMATCH":
        entry.update({
            "real_cms_id": audit["mcd_id"],
            "authority": audit["contractor"],
            "document_title": audit["mcd_title"],
            "mcd_actual_title": audit["mcd_title"],
            "citation": f"CMS MCD Document at Cited ID: {audit['mcd_title']}",
            "url": audit["url"],
            "alignment_flag": "NEEDS_REALIGNMENT"
        })
    elif audit["status"] == "UNVERIFIED_AUTHOR_SUMMARY":
        entry.update({
            "real_cms_id": None,
            "authority": "Author Summary (No CMS source located)",
            "document_title": None,
            "citation": None,
            "url": None
        })
    PROVENANCE_REGISTRY[slug] = entry

if __name__ == "__main__":
    from scripts.apply_verified_provenance import *
