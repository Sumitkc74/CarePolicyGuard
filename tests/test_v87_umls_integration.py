"""
Test Suite for Prompt v87: UMLS / UTS REST API Integration.

Validates that:
(i)   Same CUI confirms equivalence via verify_equivalence (EQUIVALENCE_CONFIRMED_VIA_UMLS).
(ii)  Different CUIs reject equivalence and fall back to NO_CONCEPT_MAP_ENTRY.
(iii) UMLS 'not found' falls back gracefully to NO_CONCEPT_MAP_ENTRY without errors.
(iv)  Missing UMLS_API_KEY fails closed (reports unavailable, falls back cleanly).
(v)   Strict egress boundary is enforced: only individual medical terms are sent,
      never clinical notes, note sentences, or narratives.
(vi)  The 12 committed concepts in the global ConceptMap are strictly unchanged.
(vii) The judge still rejects advocacy spans in gold-DENIED cases (no false approvals).
(viii) The pre-judge UMLS path resolves equivalence without an LLM call when CUIs match.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from app.core.concept_map import ConceptMap, get_concept_map
from app.core.llm_judge import ClinicalEquivalenceJudge, EquivalenceVerdict
from app.services.umls_client import UMLS_PINNED_VERSION, UMLSClient


def test_v87_same_cui_confirms_equivalence_in_verify_equivalence():
    """
    Condition (i): When two terms resolve to the identical CUI in UMLS,
    verify_equivalence confirms equivalence via the UMLS path.
    """
    mock_responses = {
        "chronic kidney disease": {"result": {"results": [{"ui": "C0000001", "name": "Chronic Kidney Disease"}]}},
        "chronic renal failure": {"result": {"results": [{"ui": "C0000001", "name": "Chronic Renal Failure"}]}},
    }

    def fake_get(url: str, params: dict[str, str]):
        term = params.get("string", "")
        if term in mock_responses:
            return httpx.Response(200, json=mock_responses[term], request=httpx.Request("GET", url))
        return httpx.Response(404, json={"error": "Not found"}, request=httpx.Request("GET", url))

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False
    mock_client.get.side_effect = fake_get

    umls = UMLSClient(
        api_key="mock-test-key",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
        http_client=mock_client,
    )

    cmap = ConceptMap()
    with patch("app.services.umls_client.get_umls_client", return_value=umls):
        is_equiv, reason = cmap.verify_equivalence(
            criterion_term="chronic kidney disease",
            proposed_term="chronic renal failure",
        )
        assert is_equiv is True
        assert "EQUIVALENCE_CONFIRMED_VIA_UMLS" in reason
        assert "C0000001" in reason


def test_v87_different_cui_rejects_equivalence():
    """
    Condition (ii): When two terms resolve to different CUIs,
    verify_equivalence rejects equivalence and returns NO_CONCEPT_MAP_ENTRY.
    """
    mock_responses = {
        "lung cancer": {"result": {"results": [{"ui": "C0000002", "name": "Lung Malignancy"}]}},
        "breast cancer": {"result": {"results": [{"ui": "C0000003", "name": "Breast Neoplasm"}]}},
    }

    def fake_get(url: str, params: dict[str, str]):
        term = params.get("string", "")
        if term in mock_responses:
            return httpx.Response(200, json=mock_responses[term], request=httpx.Request("GET", url))
        return httpx.Response(404, json={"error": "Not found"}, request=httpx.Request("GET", url))

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False
    mock_client.get.side_effect = fake_get

    umls = UMLSClient(
        api_key="mock-test-key",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
        http_client=mock_client,
    )

    cmap = ConceptMap()
    with patch("app.services.umls_client.get_umls_client", return_value=umls):
        is_equiv, reason = cmap.verify_equivalence(
            criterion_term="lung cancer",
            proposed_term="breast cancer",
        )
        assert is_equiv is False
        assert "NO_CONCEPT_MAP_ENTRY" in reason


def test_v87_umls_not_found_falls_back():
    """
    Condition (iii): When a term has no entry in UMLS (404),
    verify_equivalence falls through to NO_CONCEPT_MAP_ENTRY without raising errors.
    """
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False
    mock_client.get.return_value = httpx.Response(
        404,
        json={"error": "Term not indexed"},
        request=httpx.Request("GET", "https://uts-ws.nlm.nih.gov/rest/search/2024AB"),
    )

    umls = UMLSClient(
        api_key="mock-test-key",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
        http_client=mock_client,
    )

    cmap = ConceptMap()
    with patch("app.services.umls_client.get_umls_client", return_value=umls):
        is_equiv, reason = cmap.verify_equivalence(
            criterion_term="completely unindexed novel biomarker 999",
            proposed_term="unknown clinical phrase 888",
        )
        assert is_equiv is False
        assert "NO_CONCEPT_MAP_ENTRY" in reason


def test_v87_missing_key_fails_closed():
    """
    Condition (iv): With no UMLS_API_KEY configured, the client reports
    is_configured=False, every lookup returns None, and equivalence fails closed.
    """
    umls = UMLSClient(
        api_key="",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
    )
    assert umls.is_configured is False
    assert umls.get_cui("prostate cancer") is None

    is_equiv, cui = umls.are_equivalent("prostate cancer", "prostate adenocarcinoma")
    assert is_equiv is False
    assert cui is None

    cmap = ConceptMap()
    with patch("app.services.umls_client.get_umls_client", return_value=umls):
        # When unmapped in committed concept map and UMLS is unconfigured, defers cleanly
        is_eq, reason = cmap.verify_equivalence(
            criterion_term="unindexed criterion term",
            proposed_term="unindexed proposed term",
        )
        assert is_eq is False
        assert "NO_CONCEPT_MAP_ENTRY" in reason


def test_v87_no_note_egress_strictly_enforced():
    """
    Condition (v): Egress boundary strictly enforces that only individual medical
    terms can be sent to UTS. Notes, sentences, or multi-clause narratives are rejected.
    """
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False

    umls = UMLSClient(
        api_key="mock-test-key",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
        http_client=mock_client,
    )

    # Valid clinical terms
    assert umls.validate_term_egress_boundary("prostate adenocarcinoma") is True
    assert umls.validate_term_egress_boundary("type 2 diabetes mellitus") is True
    assert umls.validate_term_egress_boundary("visual acuity 20/50") is True

    # Invalid: multi-sentence notes, paragraphs, line breaks, or text > 100 chars
    sentence_input = "Patient has a history of severe back pain. The examination confirms tenderness."
    assert umls.validate_term_egress_boundary(sentence_input) is False

    multiline_input = "ASSESSMENT & PLAN:\nPatient underwent lumbar decompressive laminectomy."
    assert umls.validate_term_egress_boundary(multiline_input) is False

    long_input = "a" * 105
    assert umls.validate_term_egress_boundary(long_input) is False

    # Assert get_cui rejects sentence input and DOES NOT call the API
    res = umls.get_cui(sentence_input)
    assert res is None
    assert mock_client.get.call_count == 0


def test_v87_committed_map_strictly_unchanged():
    """
    Condition (vi): The 12 committed concepts in the global ConceptMap are exactly
    as at the baseline head, with zero auto-approved draft entries.
    """
    cmap = get_concept_map()
    expected_cids = {
        "CONCEPT-PROSTATE-CANCER",
        "CONCEPT-LUNG-CANCER",
        "CONCEPT-DOSE-SENSITIVE-STRUCTURES",
        "CONCEPT-CATARACT-LENS-OPACITY",
        "CONCEPT-VISUAL-IMPAIRMENT",
        "CONCEPT-CONSERVATIVE-CARE-FAILURE",
        "CONCEPT-RADICULOPATHY",
        "CONCEPT-KNEE-INSTABILITY",
        "CONCEPT-KNEE-DEFORMITY",
        "CONCEPT-LVEF-HEART-FAILURE",
        "CONCEPT-SLEEP-APNEA",
        "CONCEPT-DIABETIC-ULCER",
    }
    actual_cids = set(cmap._concepts.keys())
    assert actual_cids == expected_cids, (
        f"Committed concept set must strictly match baseline 12 concepts. Diff: {actual_cids ^ expected_cids}"
    )
    assert len(cmap._concepts) == 12

    # Assert draft entries from draft JSON are NOT in the active map
    draft_file = Path("app/data/concept_map/draft_attested_concept_entries.json")
    if draft_file.exists():
        with open(draft_file, "r", encoding="utf-8") as f:
            draft_data = json.load(f)
        for entry in draft_data.get("draft_entries", []):
            cid = entry.get("concept_id")
            assert cid not in cmap._concepts, (
                f"Draft entry {cid} must NOT be auto-approved into committed concept map."
            )


def test_v87_judge_still_rejects_advocacy_in_gold_denied_case():
    """
    Condition (vii): The judge still rejects advocacy spans that fail the criterion
    in gold-DENIED cases, ensuring the UMLS integration does NOT cause false approvals.
    """
    judge = ClinicalEquivalenceJudge(endpoint_url="http://localhost:11434/v1/chat/completions")

    # Mock an LLM response where the judge evaluates an insufficient candidate span as NOT_EQUIVALENT
    criterion = {
        "criterion_code": "CRIT-LUMB-01",
        "name": "Failure of Conservative Therapy",
        "description": "Documented completion of at least 6 weeks of structured physical therapy",
        "keywords": ["physical therapy", "conservative therapy"],
    }
    # Insufficient span: only 1 week of therapy documented
    span_text = "Patient attended physical therapy for 1 week and discontinued due to schedule conflicts."

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "verdict": "NOT_EQUIVALENT",
                    "rationale": "Only 1 week of physical therapy is documented, failing the mandatory 6-week duration."
                })
            }
        }]
    }

    with patch("httpx.Client.post", return_value=fake_resp):
        eval_res = judge.judge_equivalence_sync(criterion=criterion, candidate_span_text=span_text)
        assert eval_res.verdict == EquivalenceVerdict.NOT_EQUIVALENT
        assert "failing the mandatory 6-week duration" in eval_res.rationale


def test_v87_pre_judge_umls_resolves_equivalence_without_llm_call():
    """
    Condition (viii): When UMLS confirms same CUI for criterion and candidate span
    in an unambiguous context, judge_equivalence_sync returns EQUIVALENT without calling LLM.
    """
    judge = ClinicalEquivalenceJudge(endpoint_url="http://localhost:11434/v1/chat/completions")

    criterion = {
        "criterion_code": "CRIT-ONC-01",
        "name": "prostate cancer",
        "description": "Biopsy-proven prostate cancer",
        "keywords": ["prostate cancer"],
    }
    candidate_span = "prostate adenocarcinoma"

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False
    mock_client.get.return_value = httpx.Response(
        200,
        json={"result": {"results": [{"ui": "C0000001", "name": "Prostate Malignancy"}]}},
        request=httpx.Request("GET", "https://uts-ws.nlm.nih.gov/rest/search/2024AB"),
    )

    umls = UMLSClient(
        api_key="mock-test-key",
        version=UMLS_PINNED_VERSION,
        cache_path=None,
        http_client=mock_client,
    )

    with patch("app.services.umls_client.get_umls_client", return_value=umls), \
         patch("httpx.Client.post") as mock_llm_post:
        eval_res = judge.judge_equivalence_sync(criterion=criterion, candidate_span_text=candidate_span)
        assert eval_res.verdict == EquivalenceVerdict.EQUIVALENT
        assert eval_res.status_code == "EQUIVALENCE_CONFIRMED_VIA_UMLS"
        assert "C0000001" in eval_res.rationale
        # Crucial efficiency invariant: NO LLM POST was performed!
        assert mock_llm_post.call_count == 0
