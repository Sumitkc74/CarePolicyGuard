"""
Policy Traceability and Completeness Verification Tests (Task 2).

Proves:
1. Every policy file carries a valid schema version and a non-empty change log.
2. Every criterion in every policy file carries all mandatory traceability fields:
   - cms_document
   - source_section
   - source_paragraph
   - source_traceability_status
   - source_text_excerpt
3. Traceability status is either VERIFIED_SOURCE or UNVERIFIED (never absent or fabricated).
4. Unverified criteria are explicitly marked with explanatory notes.
5. PolicyRetrievalAgent.pull_statutory_policy_text returns verified statutory source for every policy.
"""

import json
from pathlib import Path
import pytest
from app.agents.policy_retriever import PolicyRetrievalAgent


POLICIES_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "policies"
ALL_POLICY_FILES = list(POLICIES_DIR.glob("*.json"))


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
    Verifies that every criterion in every policy carries:
    - cms_document (non-empty string)
    - source_section (non-empty string)
    - source_paragraph (non-empty string)
    - source_traceability_status ('VERIFIED_SOURCE' or 'UNVERIFIED')
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
        assert crit["source_traceability_status"] in ("VERIFIED_SOURCE", "UNVERIFIED"), (
            f"{policy_file.name} [{code}] invalid status: {crit['source_traceability_status']}"
        )
        assert "source_text_excerpt" in crit and crit["source_text_excerpt"], f"{policy_file.name} [{code}] missing source_text_excerpt"

        # If unverified, it must carry an explicit note
        if crit["source_traceability_status"] == "UNVERIFIED":
            assert "UNVERIFIED" in crit["source_paragraph"]
            assert "UNVERIFIED" in crit["source_text_excerpt"]


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

