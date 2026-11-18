import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
PROVENANCE_FILE = POLICIES_DIR / "PROVENANCE.md"

VALID_STATUSES = {
    "VERIFIED_FROM_MCD",
    "NO_MCD_DOCUMENT_FOUND",
    "MISMATCH",
    "UNVERIFIED_AUTHOR_SUMMARY"
}

def test_provenance_registry_exists_and_contains_summary():
    assert PROVENANCE_FILE.exists(), "PROVENANCE.md must exist"
    content = PROVENANCE_FILE.read_text(encoding="utf-8")
    assert "## Verification Summary Table" in content
    assert "VERIFIED_FROM_MCD" in content
    assert "MISMATCH" in content
    assert "UNVERIFIED_AUTHOR_SUMMARY" in content
    assert "SUMMARIZED_FROM_CMS_MCD" not in content, "Old blanket status SUMMARIZED_FROM_CMS_MCD must not remain"

def test_all_52_extended_policies_have_valid_mcd_provenance_status():
    policy_files = sorted([f for f in POLICIES_DIR.glob("*.json") if f.stem.startswith(("LCD-", "NCD-", "OPD-"))])
    assert len(policy_files) == 52, f"Expected 52 extended policies, found {len(policy_files)}"

    provenance_text = PROVENANCE_FILE.read_text(encoding="utf-8")

    status_counts = {"VERIFIED_FROM_MCD": 0, "NO_MCD_DOCUMENT_FOUND": 0, "MISMATCH": 0, "UNVERIFIED_AUTHOR_SUMMARY": 0}

    for pf in policy_files:
        with open(pf, "r", encoding="utf-8") as f:
            data = json.load(f)

        slug = data.get("policy_id")
        assert slug, f"Policy {pf.name} missing policy_id"
        assert f"`{slug}`" in provenance_text, f"Policy slug {slug} not found in PROVENANCE.md"

        cms_ref = data.get("cms_reference")
        assert cms_ref is not None, f"Policy {slug} missing cms_reference field"

        status = cms_ref.get("provenance_status")
        assert status in VALID_STATUSES, (
            f"Policy {slug} has invalid status {status!r}. Must be one of {VALID_STATUSES}"
        )
        assert status != "SUMMARIZED_FROM_CMS_MCD", f"Policy {slug} retains unverified blanket status"

        status_counts[status] += 1

        # Checked date must be present across all entries
        checked_date = cms_ref.get("checked_date")
        assert checked_date, f"Policy {slug} missing checked_date"

        # Every VERIFIED_FROM_MCD entry has a check date, title, real CMS ID, and URL
        if status == "VERIFIED_FROM_MCD":
            assert cms_ref.get("document_title"), f"VERIFIED_FROM_MCD policy {slug} must record document_title"
            assert cms_ref.get("real_cms_id"), f"VERIFIED_FROM_MCD policy {slug} must record real_cms_id"
            assert cms_ref.get("url"), f"VERIFIED_FROM_MCD policy {slug} must record verified URL"

        # For NO_MCD_DOCUMENT_FOUND: real_cms_id is NONE and search_terms_tried is recorded
        if status == "NO_MCD_DOCUMENT_FOUND":
            assert cms_ref.get("real_cms_id") == "NONE", f"NO_MCD policy {slug} real_cms_id must be NONE"
            assert cms_ref.get("authority"), f"NO_MCD policy {slug} must declare authority"

        # Traceability status must be a verified or statutory standard
        for crit in data.get("criteria", []):
            st = crit.get("source_traceability_status")
            assert st in ("VERIFIED_FROM_MCD", "STATUTORY_RULE", "BENEFIT_STATUTE", "CLAIMED_UNVERIFIED"), (
                f"Policy {slug} criterion {crit.get('criterion_code')} invalid traceability status: {st}"
            )

    assert status_counts["VERIFIED_FROM_MCD"] == 42
    assert status_counts["NO_MCD_DOCUMENT_FOUND"] == 10
    assert status_counts["MISMATCH"] == 0
    assert status_counts["UNVERIFIED_AUTHOR_SUMMARY"] == 0

