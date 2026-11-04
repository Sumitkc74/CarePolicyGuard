"""
Policy Traceability and Independent Regulatory Audit Package Tests (Task 4).

Proves:
1. Every policy file carries a valid schema version and a non-empty change log.
2. Every criterion in every policy file carries all mandatory traceability fields:
   - cms_document
   - source_section
   - source_paragraph
   - source_traceability_status
   - source_text_excerpt
3. Traceability status is honestly marked as 'CLAIMED_UNVERIFIED' or 'UNVERIFIED'.
4. No policy or criterion carries a verified status without an independent audit record.
5. The independent audit package covers all 8 policies and all criteria.
6. PolicyRetrievalAgent.pull_statutory_policy_text returns statutory citations for every policy.
"""

import json
from pathlib import Path
import pytest
from app.agents.policy_retriever import PolicyRetrievalAgent


POLICIES_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "policies"
ALL_POLICY_FILES = list(POLICIES_DIR.glob("*.json"))
AUDIT_DIR = Path(__file__).resolve().parent.parent / "carepolicyguard-audit"


def test_all_eight_policies_present():
    """Verifies that all 8 expected policy files exist in app/data/policies."""
    expected_ids = {
        "NCD-20.4", "LCD-L33829", "LCD-TOTAL-KNEE-01", "NCD-20.29",
        "NCD-20.33", "NCD-20.7", "NCD-220.13", "NCD-240.2"
    }
    actual_ids = {f.stem for f in ALL_POLICY_FILES}
    assert expected_ids == actual_ids, f"Expected {expected_ids}, found {actual_ids}"


@pytest.mark.parametrize("policy_file", ALL_POLICY_FILES, ids=lambda f: f.name)
def test_policy_carries_version_and_changelog(policy_file):
    """Verifies that every policy file carries a version and a non-empty change log."""
    data = json.loads(policy_file.read_text(encoding="utf-8"))

    assert "policy_version" in data, f"{policy_file.name} missing 'policy_version'"
    assert data["policy_version"], f"{policy_file.name} has empty 'policy_version'"

    assert "change_log" in data, f"{policy_file.name} missing 'change_log'"
    assert isinstance(data["change_log"], list), f"{policy_file.name} change_log must be a list"
    assert len(data["change_log"]) >= 1, f"{policy_file.name} change_log must not be empty"

    entry = data["change_log"][0]
    assert "version" in entry and "date" in entry and "summary" in entry


@pytest.mark.parametrize("policy_file", ALL_POLICY_FILES, ids=lambda f: f.name)
def test_all_criteria_carry_complete_traceability_fields(policy_file):
    """
    Task 4 Honest Traceability:
    Verifies that every criterion in every policy carries:
    - cms_document (non-empty string)
    - source_section (non-empty string)
    - source_paragraph (non-empty string)
    - source_traceability_status ('CLAIMED_UNVERIFIED' or 'UNVERIFIED')
    - source_text_excerpt (non-empty string)
    """
    data = json.loads(policy_file.read_text(encoding="utf-8"))
    criteria = data.get("criteria", [])
    assert len(criteria) > 0, f"{policy_file.name} has no criteria"

    for crit in criteria:
        code = crit.get("criterion_code", "UNKNOWN")
        assert "cms_document" in crit and crit["cms_document"], f"{policy_file.name} [{code}] missing cms_document"
        assert "source_section" in crit and crit["source_section"], f"{policy_file.name} [{code}] missing source_section"
        assert "source_paragraph" in crit and crit["source_paragraph"], f"{policy_file.name} [{code}] missing source_paragraph"
        assert "source_traceability_status" in crit, f"{policy_file.name} [{code}] missing source_traceability_status"
        assert crit["source_traceability_status"] in ("CLAIMED_UNVERIFIED", "UNVERIFIED"), (
            f"{policy_file.name} [{code}] must be CLAIMED_UNVERIFIED or UNVERIFIED, got {crit['source_traceability_status']}"
        )
        assert "source_text_excerpt" in crit and crit["source_text_excerpt"], f"{policy_file.name} [{code}] missing source_text_excerpt"

        # If archetype unverified, it must carry an explicit note
        if crit["source_traceability_status"] == "UNVERIFIED":
            assert "UNVERIFIED" in crit["source_paragraph"]
            assert "UNVERIFIED" in crit["source_text_excerpt"]


def test_no_policy_carries_verified_status_without_audit_record():
    """
    Task 4: Asserts that ZERO criteria across all 8 policies carry self-certified
    'VERIFIED_SOURCE' or 'VERIFIED' status without an independent external audit record.
    """
    verified_found = []
    for p_file in ALL_POLICY_FILES:
        data = json.loads(p_file.read_text(encoding="utf-8"))
        for crit in data.get("criteria", []):
            st = crit.get("source_traceability_status", "")
            if "VERIFIED_SOURCE" in st or st == "VERIFIED":
                verified_found.append(f"{p_file.name}:{crit.get('criterion_code')}")

    assert len(verified_found) == 0, (
        f"Found self-certified verified criteria without audit record: {verified_found}"
    )


def test_audit_package_covers_all_eight_policies():
    """
    Task 4: Asserts that the independent audit package (carepolicyguard-audit/)
    covers all 8 policies with complete checklists, manifest, and instructions.
    """
    assert AUDIT_DIR.exists(), "carepolicyguard-audit directory must exist"

    readme_path = AUDIT_DIR / "README.md"
    assert readme_path.exists(), "carepolicyguard-audit/README.md missing"
    readme_text = readme_path.read_text(encoding="utf-8")
    assert "PENDING INDEPENDENT REVIEW" in readme_text
    assert "must NOT have seen system execution logs" in readme_text

    checklist_path = AUDIT_DIR / "CRITERIA_CHECKLIST_ALL_POLICIES.md"
    assert checklist_path.exists(), "carepolicyguard-audit/CRITERIA_CHECKLIST_ALL_POLICIES.md missing"
    checklist_text = checklist_path.read_text(encoding="utf-8")

    template_path = AUDIT_DIR / "AUDIT_COVERAGE_TEMPLATE.md"
    assert template_path.exists(), "carepolicyguard-audit/AUDIT_COVERAGE_TEMPLATE.md missing"

    manifest_path = AUDIT_DIR / "audit_manifest.json"
    assert manifest_path.exists(), "carepolicyguard-audit/audit_manifest.json missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["policies_count"] == 8
    assert manifest["total_criteria_count"] == 26
    assert manifest["audit_status"] == "AUDIT_PENDING_INDEPENDENT_REVIEW"
    assert manifest["independent_reviewer_certified"] is False

    manifest_policy_ids = {p["policy_id"] for p in manifest["policies"]}
    expected_ids = {
        "NCD-20.4", "LCD-L33829", "LCD-TOTAL-KNEE-01", "NCD-20.29",
        "NCD-20.33", "NCD-20.7", "NCD-220.13", "NCD-240.2"
    }
    assert manifest_policy_ids == expected_ids

    for pol_id in expected_ids:
        assert pol_id in checklist_text, f"{pol_id} missing from checklist markdown"


def test_policy_retriever_returns_traced_source_for_all_policies():
    """
    Verifies that PolicyRetrievalAgent.pull_statutory_policy_text returns
    authoritative citations for every policy without falling back to 'Unregistered Policy'.
    """
    retriever = PolicyRetrievalAgent()
    expected_ids = [
        "NCD-20.4", "LCD-L33829", "LCD-TOTAL-KNEE-01", "NCD-20.29",
        "NCD-20.33", "NCD-20.7", "NCD-220.13", "NCD-240.2"
    ]

    for pol_id in expected_ids:
        stat_info = retriever.pull_statutory_policy_text(pol_id)
        assert stat_info["policy_id"] == pol_id
        assert stat_info["source"] != "Unregistered Policy", f"{pol_id} returned as Unregistered Policy"
        assert len(stat_info["cms_manual"]) > 0
        assert len(stat_info["chapter_section"]) > 0
        assert len(stat_info["statutory_text_excerpt"]) > 0
