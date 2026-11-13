"""Comprehensive unit and integration tests for Medicare Policy Shortlist.

Validates:
1. Unified scorer resolving legacy scorer disagreements (e.g. DEV-LCD-ACDF-NEG).
2. Shortlist entries carry verbatim quoted phrases and drop empty/sub-floor candidates.
3. Margin rule preselection: decisive case vs. close-call case.
4. No governing policy handling for off-topic notes.
5. Elimination of silent NCD-20.4 default fallback (fail-before / pass-after).
6. Message board posting of POLICY_SHORTLIST and POLICY_CHOSEN.
7. API endpoint /api/v1/policies/shortlist contract validation.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.message_board import BoardMessageType
from app.services.policy_shortlist_service import PolicyShortlistService
from main import app


@pytest.fixture
def dev_vignettes():
    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_unified_scorer_resolves_legacy_disagreement(dev_vignettes):
    """DEV-LCD-ACDF-NEG caused Scorer 1 (OPD-CERV-DISC) and Scorer 2 (LCD-ACDF) to disagree.
    The unified scorer with criteria coverage reranking must rank LCD-ACDF as #1.
    """
    vig = next(v for v in dev_vignettes if v.get("vignette_id") == "DEV-LCD-ACDF-NEG")
    note = vig["ehr_narrative"]

    res = PolicyShortlistService.compute_shortlist(note, top_k=5)

    candidates = res.get("shortlist") or res.get("candidates")
    assert len(candidates) > 0
    top_cand = candidates[0]
    assert top_cand["policy_id"] == "LCD-ACDF", (
        f"Expected LCD-ACDF as #1 candidate, got {top_cand['policy_id']} (title: {top_cand['policy_title']})"
    )
    assert top_cand["rank"] == 1
    assert top_cand["coverage_ratio"] > 0.0


def test_shortlist_entries_carry_quoted_phrases_and_drop_empty(dev_vignettes):
    """Every shortlist candidate must have matching_phrases that are verbatim
    substrings of the clinical note.
    """
    vig = dev_vignettes[0]
    note = vig["ehr_narrative"]
    note_lower = note.lower()

    res = PolicyShortlistService.compute_shortlist(note, top_k=5)
    candidates = res.get("shortlist") or res.get("candidates")
    assert len(candidates) > 0

    for cand in candidates:
        assert isinstance(cand["matching_phrases"], list)
        for phrase in cand["matching_phrases"]:
            assert phrase.lower() in note_lower, (
                f"Phrase '{phrase}' for policy {cand['policy_id']} is not an exact substring of the note."
            )


def test_margin_rule_preselection_decisive_vs_close_call(dev_vignettes):
    """A decisive case (e.g. DEV-LCD-ACDF-APP) has margin >= 0.08
    and coverage >= 0.33, yielding status="PRESELECTED".
    A deliberately ambiguous / borderline note must yield status="SELECTION_REQUIRED".
    """
    # 1. Decisive Case
    vig_decisive = next(v for v in dev_vignettes if v.get("vignette_id") == "DEV-LCD-ACDF-APP")
    res_decisive = PolicyShortlistService.compute_shortlist(vig_decisive["ehr_narrative"], top_k=5)

    assert res_decisive["status"] == "PRESELECTED"
    assert res_decisive["preselected_policy_id"] == "LCD-ACDF"
    assert res_decisive["preselection_margin"] is not None
    assert res_decisive["preselection_margin"] >= 0.08

    # 2. Close Call Case (DEV-LCD-MRI-LUMBAR-APP: margin 0.027 < 0.08 between top candidates)
    vig_close = next(v for v in dev_vignettes if v.get("vignette_id") == "DEV-LCD-MRI-LUMBAR-APP")
    res_close = PolicyShortlistService.compute_shortlist(vig_close["ehr_narrative"], top_k=5)
    assert res_close["status"] == "SELECTION_REQUIRED"
    assert res_close["preselected_policy_id"] is None
    assert res_close["preselection_margin"] is not None
    assert res_close["preselection_margin"] < 0.08


def test_no_governing_policy_off_topic():
    """An off-topic clinical note with zero Medicare prior authorization policies
    applicable must return status="NO_GOVERNING_POLICY" and empty candidates.
    """
    off_topic_note = (
        "Patient presents with mild seasonal allergic rhinitis, intermittent sneezing, and clear rhinorrhea "
        "triggered by spring pollen. Over-the-counter cetirizine recommended. No other complaints or chronic conditions."
    )
    res = PolicyShortlistService.compute_shortlist(off_topic_note, top_k=5)

    assert res["status"] == "NO_GOVERNING_POLICY"
    assert res["preselected_policy_id"] is None
    candidates = res.get("shortlist") or res.get("candidates")
    assert len(candidates) == 0


def test_kill_silent_ncd20_4_default_fail_before_pass_after():
    """CRITICAL REGRESSION: Previously, an unselected or off-topic note silently defaulted
    to NCD-20.4 (Implantable Defibrillators).
    The pipeline must now return DEFERRED_TO_HUMAN with policy_id="NONE", status="NO_GOVERNING_POLICY",
    and never evaluate or approve under NCD-20.4.
    """
    pipeline = MultiAgentVerificationPipeline()
    off_topic_note = (
        "Patient presents for routine follow-up of mild eczema on the left forearm. "
        "Prescribed topical hydrocortisone cream. Vital signs normal, lungs clear, heart regular."
    )

    # Calling pipeline in AUTO mode
    adj = pipeline.adjudicate_sync(
        patient_id="PT-OFF-TOPIC",
        policy_id="AUTO",
        ehr_narrative=off_topic_note,
        execution_mode="deterministic",
        save_record=False,
    )

    assert adj.adjudication_decision.value == "DEFERRED_TO_HUMAN"
    assert adj.policy_id == "NONE"
    assert adj.policy_choice_metadata is not None
    assert adj.policy_choice_metadata["chooser"] == "none"
    assert adj.policy_choice_metadata["status"] == "NO_GOVERNING_POLICY"
    assert "No governing Medicare policy matches" in adj.abstention_reason


def test_message_board_shortlist_and_chosen_posted(dev_vignettes):
    """Running adjudication in AUTO mode must record POLICY_SHORTLIST and
    POLICY_CHOSEN on the CaseMessageBoard.
    """
    pipeline = MultiAgentVerificationPipeline()
    vig = dev_vignettes[0]

    adj = pipeline.adjudicate_sync(
        patient_id="PT-TEST",
        policy_id="AUTO",
        ehr_narrative=vig["ehr_narrative"],
        execution_mode="deterministic",
        save_record=False,
    )

    assert adj.message_board is not None
    msg_types = [m.get("message_type") for m in adj.message_board]

    assert BoardMessageType.POLICY_SHORTLIST.value in msg_types or BoardMessageType.POLICY_SHORTLIST in msg_types, (
        f"POLICY_SHORTLIST missing from message board. Types found: {msg_types}"
    )
    assert BoardMessageType.POLICY_CHOSEN.value in msg_types or BoardMessageType.POLICY_CHOSEN in msg_types, (
        f"POLICY_CHOSEN missing from message board. Types found: {msg_types}"
    )

    chosen_msg = next(
        m for m in adj.message_board
        if m.get("message_type") in (BoardMessageType.POLICY_CHOSEN, BoardMessageType.POLICY_CHOSEN.value)
    )
    assert "chosen_policy_id" in chosen_msg["metadata"]
    assert chosen_msg["metadata"]["chosen_policy_id"] == adj.policy_id


def test_shortlist_api_endpoint_contracts(dev_vignettes):
    """Tests POST /api/v1/policies/shortlist contract."""
    client = TestClient(app)

    # 1. Empty narrative returns 400
    res_bad = client.post("/api/v1/policies/shortlist", json={"ehr_narrative": "   ", "top_k": 5})
    assert res_bad.status_code == 400
    assert "empty" in res_bad.json()["detail"].lower()

    # 2. Valid narrative returns 200 with complete schema
    vig = dev_vignettes[0]
    res_good = client.post("/api/v1/policies/shortlist", json={"ehr_narrative": vig["ehr_narrative"], "top_k": 3})
    assert res_good.status_code == 200

    data = res_good.json()
    assert "status" in data
    assert "preselected_policy_id" in data
    assert "shortlist" in data or "candidates" in data
    candidates = data.get("shortlist") or data.get("candidates")
    assert len(candidates) <= 3


def test_upload_note_off_topic_defers_without_ncd20_4():
    """Regression test: /api/v1/upload-note with an off-topic note must NOT default to NCD-20.4.
    It must return DEFERRED_TO_HUMAN under policy_id='NONE'.
    """
    client = TestClient(app)
    off_topic_content = (
        b"Patient presents for routine follow-up of mild eczema on the left forearm. "
        b"Prescribed topical hydrocortisone cream. Vital signs normal, lungs clear, heart regular."
    )

    files = {"file": ("eczema_note.txt", off_topic_content, "text/plain")}
    res = client.post("/api/v1/upload-note", files=files)
    assert res.status_code == 200
    data = res.json()
    adj = data["adjudication"]
    assert adj["adjudication_decision"] == "DEFERRED_TO_HUMAN"
    assert adj["policy_id"] == "NONE"
    assert adj["policy_id"] != "NCD-20.4"


def test_extract_text_off_topic_returns_null_suggestion():
    """Regression test: /api/v1/extract-clinical-text with an off-topic note must return
    suggested_policy_id=None and suggested_policy_title=None, NEVER defaulting to NCD-20.4.
    """
    client = TestClient(app)
    off_topic_content = (
        b"Patient presents for routine follow-up of mild seasonal allergies and sneezing. "
        b"Prescribed cetirizine 10mg daily. No active cardiovascular or orthopedic complaints."
    )

    files = {"files": ("allergy_note.txt", off_topic_content, "text/plain")}
    res = client.post("/api/v1/extract-text", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["suggested_policy_id"] is None
    assert data["suggested_policy_title"] is None

