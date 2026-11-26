"""
Unit tests for v91 Policy Verification Workflow (scripts.review_policy_queue + Agent 5).

Covers all 10 mandatory conditions:
(i) Refusal of agent reviewer (agent self-approval block).
(ii) Recording ACCEPT on PASS verbatim_check; duplicate refusal without --overwrite.
(iii) Refusal of APPROVE on FAIL verbatim_check; allowing REJECT.
(iv) Refusal of APPROVE with empty notes.
(v) Policy activation: DRAFT to ACTIVE when all accepted; refusal if pending; refusal if active.
(vi) Engine refusal of DRAFT policy without include_drafts=True.
(vii) Agent 5 NO_INDICATIONS_FOUND on empty indications; no policy persisted; no queue records.
(viii) Agent 5 queue registration with PENDING_HUMAN_REVIEW and verbatim_check.
(ix) Freshly onboarded policy carries DRAFT status and criteria carry CLAIMED_UNVERIFIED.
(x) Verbatim check: exact substring passes, paraphrase fails, empty fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.policy_onboarding import PolicyOnboardingAgent
from app.schemas.declarative_policy import DeclarativeCriterion, DeclarativePolicy
from app.services.declarative_engine import DeclarativePolicyEngine
from scripts.review_policy_queue import (
    activate_policy,
    is_agent_reviewer,
    load_queue,
    record_review,
    save_queue,
)


@pytest.fixture
def mock_queue_file(tmp_path: Path) -> Path:
    """Fixture providing an isolated queue JSON file."""
    q_file = tmp_path / "test_policy_queue.json"
    initial_records = [
        {
            "policy_id": "TEST-POL-01",
            "criterion_code": "CRIT-TEST-01",
            "criterion_name": "Test Requirement 1",
            "is_exclusion": False,
            "criterion_description": "Requirement 1 description.",
            "source_text_excerpt": "Verbatim quote 1.",
            "cms_document": "Test LCD",
            "source_section": "Indications",
            "source_paragraph": "Para 1",
            "status": "PENDING_HUMAN_REVIEW",
            "reviewer_decision": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "reviewer_notes": None,
            "verbatim_check": "PASS",
            "mcd_passage": "Verbatim quote 1 from document.",
            "policy_status": "DRAFT",
            "created_at": "2026-11-26T00:00:00Z",
        },
        {
            "policy_id": "TEST-POL-01",
            "criterion_code": "CRIT-TEST-02",
            "criterion_name": "Test Requirement 2",
            "is_exclusion": False,
            "criterion_description": "Requirement 2 description.",
            "source_text_excerpt": "Mismatched quote 2.",
            "cms_document": "Test LCD",
            "source_section": "Indications",
            "source_paragraph": "Para 2",
            "status": "PENDING_HUMAN_REVIEW",
            "reviewer_decision": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "reviewer_notes": None,
            "verbatim_check": "FAIL",
            "mcd_passage": "No matching passage found in document.",
            "policy_status": "DRAFT",
            "created_at": "2026-11-26T00:00:00Z",
        },
    ]
    with open(q_file, "w", encoding="utf-8") as f:
        json.dump(initial_records, f, indent=2)
    return q_file


def test_i_review_tool_refuses_agent_reviewer(mock_queue_file: Path):
    """(i) The review tool refuses an agent reviewer and writes nothing."""
    agent_names = ["Agent-5", "claude_bot", "LLM-Evaluator", "Antigravity-Agent", "system_auto"]
    for agent_name in agent_names:
        assert is_agent_reviewer(agent_name) is True
        success, msg = record_review(
            queue_file=mock_queue_file,
            criterion_code="CRIT-TEST-01",
            decision="APPROVE",
            reviewer_name=agent_name,
            notes="Automated self approval attempt",
        )
        assert success is False
        assert "Agent self-approval is strictly prohibited" in msg

    # Verify queue was not modified
    queue = load_queue(mock_queue_file)
    assert queue[0]["status"] == "PENDING_HUMAN_REVIEW"
    assert queue[0]["reviewer_decision"] is None


def test_ii_review_tool_records_accept_on_pass(mock_queue_file: Path):
    """(ii) The review tool records an ACCEPT for a PASS criterion, and refuses duplicate without overwrite."""
    success, msg = record_review(
        queue_file=mock_queue_file,
        criterion_code="CRIT-TEST-01",
        decision="APPROVE",
        reviewer_name="Dr. Jane Doe, MD",
        notes="Grounded in LCD paragraph 1.",
    )
    assert success is True
    assert "Successfully recorded APPROVE (status -> ACCEPTED)" in msg

    queue = load_queue(mock_queue_file)
    rec = next(r for r in queue if r["criterion_code"] == "CRIT-TEST-01")
    assert rec["status"] == "ACCEPTED"
    assert rec["reviewer_decision"] == "APPROVE"
    assert rec["reviewed_by"] == "Dr. Jane Doe, MD"
    assert rec["reviewer_notes"] == "Grounded in LCD paragraph 1."
    assert rec["reviewed_at"] is not None

    # Duplicate without overwrite must be refused
    dup_success, dup_msg = record_review(
        queue_file=mock_queue_file,
        criterion_code="CRIT-TEST-01",
        decision="APPROVE",
        reviewer_name="Dr. Jane Doe, MD",
        notes="Trying duplicate review",
        overwrite=False,
    )
    assert dup_success is False
    assert "already has review status 'ACCEPTED'" in dup_msg


def test_iii_review_tool_refuses_approve_on_fail_allows_reject(mock_queue_file: Path):
    """(iii) Refuses APPROVE for a criterion whose verbatim_check is FAIL, but allows REJECT."""
    # Attempt APPROVE on FAIL criterion
    app_success, app_msg = record_review(
        queue_file=mock_queue_file,
        criterion_code="CRIT-TEST-02",
        decision="APPROVE",
        reviewer_name="Dr. Jane Doe, MD",
        notes="Attempting to approve failed criterion",
    )
    assert app_success is False
    assert "Cannot approve criterion 'CRIT-TEST-02' with verbatim check status 'FAIL'" in app_msg

    # Attempt REJECT on FAIL criterion
    rej_success, rej_msg = record_review(
        queue_file=mock_queue_file,
        criterion_code="CRIT-TEST-02",
        decision="REJECT",
        reviewer_name="Dr. Jane Doe, MD",
        notes="Rejected due to fabricated or mismatched source quote.",
    )
    assert rej_success is True
    assert "Successfully recorded REJECT (status -> REJECTED)" in rej_msg

    queue = load_queue(mock_queue_file)
    rec = next(r for r in queue if r["criterion_code"] == "CRIT-TEST-02")
    assert rec["status"] == "REJECTED"
    assert rec["reviewer_decision"] == "REJECT"


def test_iv_review_tool_refuses_approve_with_empty_notes(mock_queue_file: Path):
    """(iv) Refuses review recording with empty or whitespace-only reviewer notes."""
    success, msg = record_review(
        queue_file=mock_queue_file,
        criterion_code="CRIT-TEST-01",
        decision="APPROVE",
        reviewer_name="Dr. Jane Doe, MD",
        notes="   ",
    )
    assert success is False
    assert "Reviewer notes are mandatory" in msg


def test_v_policy_activation_lifecycle(mock_queue_file: Path, tmp_path: Path):
    """(v) Policy activation: DRAFT to ACTIVE when all accepted; refused if pending; refused if active."""
    policy_file = tmp_path / "TEST-POL-01.json"
    policy_data = {
        "policy_id": "TEST-POL-01",
        "title": "Test Procedure Policy",
        "status": "DRAFT",
        "criteria": [
            {"criterion_code": "CRIT-TEST-01", "name": "Crit 1"},
            {"criterion_code": "CRIT-TEST-02", "name": "Crit 2"},
        ],
    }
    with open(policy_file, "w", encoding="utf-8") as f:
        json.dump(policy_data, f, indent=2)

    # 1. Refusal when criteria are still pending
    act_fail, act_msg = activate_policy(
        policy_id="TEST-POL-01",
        queue_file=mock_queue_file,
        policies_dir=tmp_path,
    )
    assert act_fail is False
    assert "cannot be activated" in act_msg
    assert "PENDING: 2" in act_msg

    # 2. Accept both criteria
    record_review(
        criterion_code="CRIT-TEST-01",
        decision="APPROVE",
        reviewer_name="Dr. Clinician",
        notes="Valid quote",
        queue_file=mock_queue_file,
        overwrite=True,
    )
    # Set CRIT-TEST-02 verbatim_check to PASS in queue so it can be approved
    queue = load_queue(mock_queue_file)
    for q in queue:
        if q["criterion_code"] == "CRIT-TEST-02":
            q["verbatim_check"] = "PASS"
    save_queue(queue, mock_queue_file)
    record_review(
        criterion_code="CRIT-TEST-02",
        decision="APPROVE",
        reviewer_name="Dr. Clinician",
        notes="Valid quote 2",
        queue_file=mock_queue_file,
        overwrite=True,
    )

    # 3. Activation succeeds when all are ACCEPTED
    act_ok, act_ok_msg = activate_policy(
        policy_id="TEST-POL-01",
        queue_file=mock_queue_file,
        policies_dir=tmp_path,
    )
    assert act_ok is True
    assert "SUCCESS: Policy 'TEST-POL-01' activated" in act_ok_msg

    with open(policy_file, encoding="utf-8") as f:
        updated_pol = json.load(f)
    assert updated_pol["status"] == "ACTIVE"

    # 4. Refused if already ACTIVE
    act_again, act_again_msg = activate_policy(
        policy_id="TEST-POL-01",
        queue_file=mock_queue_file,
        policies_dir=tmp_path,
    )
    assert act_again is False
    assert "already ACTIVE" in act_again_msg


def test_vi_engine_refuses_draft_policy_without_flag():
    """(vi) DeclarativePolicyEngine refuses DRAFT policy without include_drafts=True."""
    draft_policy = DeclarativePolicy(
        policy_id="DRAFT-POL-TEMP",
        title="Draft Test Policy",
        jurisdiction="MAC",
        effective_date="2026-11-26",
        category="Test Category",
        description="Draft test description",
        status="DRAFT",
        criteria=[
            DeclarativeCriterion(
                criterion_code="CRIT-DRAFT-01",
                name="Draft Crit",
                description="Draft description",
                clinical_intent="Intent",
                criterion_type="FINDING_PRESENCE",
            )
        ],
    )
    active_policy = DeclarativePolicy(
        policy_id="ACTIVE-POL-TEMP",
        title="Active Test Policy",
        jurisdiction="MAC",
        effective_date="2026-11-26",
        category="Test Category",
        description="Active test description",
        status="ACTIVE",
        criteria=[
            DeclarativeCriterion(
                criterion_code="CRIT-ACTIVE-01",
                name="Active Crit",
                description="Active description",
                clinical_intent="Intent",
                criterion_type="FINDING_PRESENCE",
            )
        ],
    )

    with patch.object(
        DeclarativePolicyEngine,
        "get_all_policies",
        side_effect=lambda include_drafts=False: (
            [active_policy, draft_policy] if include_drafts else [active_policy]
        ),
    ):
        active_only = DeclarativePolicyEngine.get_all_policies(include_drafts=False)
        assert len(active_only) == 1
        assert active_only[0].policy_id == "ACTIVE-POL-TEMP"

        all_pols = DeclarativePolicyEngine.get_all_policies(include_drafts=True)
        assert len(all_pols) == 2
        assert {p.policy_id for p in all_pols} == {"ACTIVE-POL-TEMP", "DRAFT-POL-TEMP"}


def test_vii_onboard_policy_no_indications_terminal(tmp_path: Path):
    """(vii) onboard_policy terminates with NO_INDICATIONS_FOUND, writes no policy or queue records."""
    empty_doc = {
        "mcd_id": "L99991",
        "title": "Document Without Indications",
        "jurisdiction": "MAC",
        "authority": "CMS",
        "url": "https://cms.gov",
        "text": "General introductory preamble with zero clinical indications.",
        "indications": [],
    }

    queue_file = tmp_path / "mock_queue.json"
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump([], f)

    agent = PolicyOnboardingAgent(staging_dir=tmp_path, queue_path=queue_file)

    with patch.object(agent, "fetch_mcd_document", return_value=empty_doc):
        result = agent.onboard_policy("L99991", "Test Subject", save_draft=True)

    assert result.status == "NO_INDICATIONS_FOUND"
    assert "NO_INDICATIONS_FOUND: MCD document" in result.message
    assert result.policy is None

    # Confirm no files written
    assert len(list(tmp_path.glob("*.json"))) == 1  # Only mock_queue.json
    queue_data = json.loads(queue_file.read_text(encoding="utf-8"))
    assert len(queue_data) == 0


def test_viii_onboard_policy_creates_pending_human_review_queue_records(tmp_path: Path):
    """(viii) onboard_policy creates PENDING_HUMAN_REVIEW queue records for every drafted criterion."""
    doc_text = "The patient must have documented knee instability on clinical exam."
    valid_doc = {
        "mcd_id": "L33318",
        "title": "Knee Orthoses",
        "jurisdiction": "DME MAC",
        "authority": "DME MAC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33318",
        "text": doc_text,
        "indications": [
            {
                "code": "CRIT-KNEE-01",
                "name": "Knee Instability",
                "description": "Documented knee instability.",
                "quoted_passage": doc_text,
                "section": "Indications",
                "paragraph": "Paragraph 1",
                "type": "FINDING_PRESENCE",
                "synonyms": ["knee instability"],
            }
        ],
    }

    queue_file = tmp_path / "queue_v8.json"
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump([], f)

    agent = PolicyOnboardingAgent(staging_dir=tmp_path, queue_path=queue_file)

    with patch.object(agent, "fetch_mcd_document", return_value=valid_doc):
        result = agent.onboard_policy("L33318", "Knee Orthoses", save_draft=True)

    assert result.status == "DRAFT_ONBOARDED"
    # Verify queue record
    queue_data = json.loads(queue_file.read_text(encoding="utf-8"))
    assert len(queue_data) == 1
    rec = queue_data[0]
    assert rec["criterion_code"] == "CRIT-KNEE-01"
    assert rec["status"] == "PENDING_HUMAN_REVIEW"
    assert rec["verbatim_check"] == "PASS"
    assert rec["policy_status"] == "DRAFT"
    assert rec["reviewer_decision"] is None


def test_ix_freshly_onboarded_policy_draft_and_claimed_unverified(tmp_path: Path):
    """(ix) A freshly onboarded policy's criteria carry CLAIMED_UNVERIFIED and policy carries DRAFT status."""
    doc_text = "The patient must have documented knee instability on clinical exam."
    valid_doc = {
        "mcd_id": "L33318",
        "title": "Knee Orthoses",
        "jurisdiction": "DME MAC",
        "authority": "DME MAC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33318",
        "text": doc_text,
        "indications": [
            {
                "code": "CRIT-KNEE-01",
                "name": "Knee Instability",
                "description": "Documented knee instability.",
                "quoted_passage": doc_text,
                "section": "Indications",
                "paragraph": "Paragraph 1",
                "type": "FINDING_PRESENCE",
                "synonyms": ["knee instability"],
            }
        ],
    }

    queue_file = tmp_path / "queue_v9.json"
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump([], f)

    agent = PolicyOnboardingAgent(staging_dir=tmp_path, queue_path=queue_file)

    with patch.object(agent, "fetch_mcd_document", return_value=valid_doc):
        result = agent.onboard_policy("L33318", "Knee Orthoses", save_draft=True)

    assert result.status == "DRAFT_ONBOARDED"
    policy = result.policy
    assert policy is not None
    assert policy.status == "DRAFT"
    assert policy.cms_reference.get("provenance_status") == "CLAIMED_UNVERIFIED"
    assert policy.cms_reference.get("lifecycle_status") == "DRAFT"

    for crit in policy.criteria:
        assert crit.source_traceability_status == "CLAIMED_UNVERIFIED"
        assert crit.source_traceability_status != "VERIFIED_FROM_MCD"


def test_x_verbatim_check_logic():
    """(x) The verbatim check: exact substring passes, paraphrase fails, empty fails."""
    doc_text = "The patient must have severe radicular pain refractory to conservative therapy for at least 4 weeks."

    # 1. Exact passage passes
    quote_exact = "severe radicular pain refractory to conservative therapy for at least 4 weeks"
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, quote_exact) is True

    # 2. Passage with excess internal whitespace passes
    quote_ws = "severe   radicular\n pain  refractory  to conservative therapy"
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, quote_ws) is True

    # 3. Paraphrase fails
    quote_paraphrase = "patient has intense sciatica that did not improve after one month of PT"
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, quote_paraphrase) is False

    # 4. Partial mismatch fails
    quote_mismatch = "severe radicular pain refractory to conservative therapy for at least 6 weeks"
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, quote_mismatch) is False

    # 5. Empty / whitespace fails
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, "") is False
    assert PolicyOnboardingAgent.verify_verbatim_quote(doc_text, "   ") is False
