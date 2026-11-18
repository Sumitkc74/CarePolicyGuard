"""
Policy Provenance and MCD Verification Tests (Session v66).

Validates:
1. All 50 policies load cleanly into DeclarativePolicyEngine.
2. Every policy carries an authoritative cms_reference object.
3. Provenance status is strictly VERIFIED_FROM_MCD (40) or NO_MCD_DOCUMENT_FOUND (10).
4. No policy carries legacy UNVERIFIED_AUTHOR_SUMMARY or MISMATCH statuses.
5. All 40 verified policies have valid CMS MCD URLs, citations, and real_cms_ids.
6. All 10 NO_MCD policies have explicit search_terms_tried and statutory authority.
7. Fake transmittal feed (CMS_LATEST_TRANSMITTAL_FEED) is permanently gone.
8. The extraction evidence manifest exists and covers all 50 policies.
"""

import json
from pathlib import Path

import app.services.cms_sync as cms_sync_mod
from app.services.declarative_engine import DeclarativePolicyEngine


def test_no_fake_cms_transmittal_feed():
    """Confirms CMS_LATEST_TRANSMITTAL_FEED is completely removed from the project."""
    assert not hasattr(cms_sync_mod, "CMS_LATEST_TRANSMITTAL_FEED"), (
        "CMS_LATEST_TRANSMITTAL_FEED must not exist in app.services.cms_sync"
    )


def test_all_50_policies_provenance_structure():
    """Validates provenance schema and verification statuses across all 50 policies."""
    policies = DeclarativePolicyEngine.get_all_policies()
    assert len(policies) == 50, f"Expected 50 policies, got {len(policies)}"

    verified_count = 0
    no_mcd_count = 0

    for pol in policies:
        pid = pol.policy_id
        ref = pol.cms_reference
        assert ref is not None, f"Policy {pid} is missing cms_reference"
        assert isinstance(ref, dict), f"Policy {pid} cms_reference must be a dict"

        status = ref.get("provenance_status")
        assert status in ("VERIFIED_FROM_MCD", "NO_MCD_DOCUMENT_FOUND"), (
            f"Policy {pid} has invalid provenance status '{status}'. "
            "Must be VERIFIED_FROM_MCD or NO_MCD_DOCUMENT_FOUND."
        )

        assert ref.get("checked_date") == "2026-11-18", (
            f"Policy {pid} checked_date must be '2026-11-18'"
        )

        if status == "VERIFIED_FROM_MCD":
            verified_count += 1
            real_id = ref.get("real_cms_id")
            assert real_id and real_id != "NONE", f"Policy {pid} must have real_cms_id"
            assert "url" in ref and "cms.gov/medicare-coverage-database" in ref["url"], (
                f"Policy {pid} must have valid cms.gov MCD URL"
            )
            assert ref.get("citation"), f"Policy {pid} must have citation"
            assert ref.get("document_title"), f"Policy {pid} must have document_title"
        else:
            no_mcd_count += 1
            assert ref.get("real_cms_id") == "NONE", f"Policy {pid} real_cms_id must be NONE"
            assert ref.get("search_terms_tried"), f"Policy {pid} must record search_terms_tried"
            assert ref.get("authority"), f"Policy {pid} must declare governing authority"
            assert ref.get("citation"), f"Policy {pid} must declare statutory citation"

    assert verified_count == 40, f"Expected 40 VERIFIED_FROM_MCD policies, got {verified_count}"
    assert no_mcd_count == 10, f"Expected 10 NO_MCD_DOCUMENT_FOUND policies, got {no_mcd_count}"


def test_criteria_source_traceability():
    """Validates that all criteria across all 50 policies have non-empty verbatim excerpts."""
    policies = DeclarativePolicyEngine.get_all_policies()
    total_criteria = 0

    for pol in policies:
        for crit in pol.criteria:
            total_criteria += 1
            code = crit.criterion_code
            status = getattr(crit, "source_traceability_status", None)
            excerpt = getattr(crit, "source_text_excerpt", None)

            assert status in ("VERIFIED_FROM_MCD", "STATUTORY_RULE", "BENEFIT_STATUTE"), (
                f"Criterion {code} in {pol.policy_id} has invalid traceability status: {status}"
            )
            assert excerpt and len(excerpt.strip()) > 10, (
                f"Criterion {code} in {pol.policy_id} must have non-empty source_text_excerpt"
            )

    assert total_criteria >= 140, f"Expected >= 140 criteria, found {total_criteria}"


def test_extraction_manifest_integrity():
    """Validates the audit extraction manifest in app/data/policies_extended/."""
    manifest_path = Path("app/data/policies_extended/cms_extraction_manifest.json")
    assert manifest_path.exists(), "cms_extraction_manifest.json must exist"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("total_policies") == 50
    assert manifest.get("verified_from_mcd_count") == 40
    assert manifest.get("no_mcd_document_count") == 10
    assert len(manifest.get("policies", {})) == 50
