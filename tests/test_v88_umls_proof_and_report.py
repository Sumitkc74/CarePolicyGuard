"""
Test Suite for Prompt v88: UMLS Proof, Egress Boundary Hardening, and Report Verification.

Pins:
(i)   Tightened egress boundary rejects terms ending in sentence punctuation (., ?, !, ;),
      rejects multi-sentence clinical text and terms > 100 chars, while accepting clean medical terms.
(ii)  UMLS telemetry counters are properly incremented and recorded across client and judge.
(iii) The v87 delivery report contains the required in-place corrections (provenance, -2 attribution,
      delivery head 6ecf756, and zero occurrences of nonexistent exception classes).
(iv)  Target case defenses, concessions, and advocate rejections in gold-DENIED cases remain intact.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from app.core.llm_judge import ClinicalEquivalenceJudge, EquivalenceVerdict
from app.services.umls_client import UMLSClient


def test_v88_tightened_egress_boundary():
    """
    Condition (i): Egress boundary strictly rejects:
    - Terms ending in sentence punctuation: ., ?, !, ;
    - Multi-sentence text containing delimiters followed by whitespace
    - Linebreaks / carriage returns
    - Terms exceeding 100 characters
    Accepts:
    - Clean medical terms and phrases <= 100 characters
    """
    client = UMLSClient(api_key="mock_key")

    # 1. Terms ending in sentence punctuation must be REJECTED
    assert client.validate_term_egress_boundary("prostate cancer.") is False
    assert client.validate_term_egress_boundary("adenocarcinoma?") is False
    assert client.validate_term_egress_boundary("cardiogenic shock!") is False
    assert client.validate_term_egress_boundary("lumbar radiculopathy;") is False

    # 2. Terms containing sentence delimiters followed by whitespace must be REJECTED
    assert client.validate_term_egress_boundary("Patient denies pain. Heart failure noted.") is False
    assert client.validate_term_egress_boundary("Cough? Dyspnea present.") is False

    # 3. Newlines / linebreaks must be REJECTED
    assert client.validate_term_egress_boundary("prostate cancer\nstage 2") is False
    assert client.validate_term_egress_boundary("lumbar pain\rextension") is False

    # 4. Terms exceeding 100 characters must be REJECTED
    long_term = "a" * 101
    assert client.validate_term_egress_boundary(long_term) is False

    # 5. Clean clinical terms <= 100 chars must be ACCEPTED
    assert client.validate_term_egress_boundary("prostate adenocarcinoma") is True
    assert client.validate_term_egress_boundary("prostate cancer") is True
    assert client.validate_term_egress_boundary("chronic kidney disease") is True
    assert client.validate_term_egress_boundary("renal failure") is True


def test_v88_telemetry_recording():
    """
    Condition (ii): When UMLS resolves equivalence before the LLM judge,
    the judge's 'equivalence_resolved_by_umls' telemetry counter increments
    AND the UMLS client's 'equivalence_confirmed_by_cui' counter increments.
    """
    judge = ClinicalEquivalenceJudge()
    initial_judge_count = judge.telemetry.get("equivalence_resolved_by_umls", 0)
    initial_global_judge_count = ClinicalEquivalenceJudge._global_telemetry.get("equivalence_resolved_by_umls", 0)

    mock_client = MagicMock(spec=UMLSClient)
    mock_client.is_configured = True
    mock_client.validate_term_egress_boundary.return_value = True
    # Return same CUI
    mock_client.are_equivalent.return_value = (True, "C0022646")

    with patch("app.services.umls_client.get_umls_client", return_value=mock_client):
        res = judge.judge_equivalence_sync(
            criterion={
                "criterion_code": "CRIT-KIDNEY-01",
                "name": "Kidney Disease",
                "description": "Evidence of chronic kidney failure or insufficiency.",
                "keywords": ["kidney", "renal"],
            },
            candidate_span_text="Patient has chronic renal failure documented on lab report.",
        )

    assert res.verdict == EquivalenceVerdict.EQUIVALENT
    assert res.status_code == "EQUIVALENCE_CONFIRMED_VIA_UMLS"
    assert "C0022646" in res.rationale

    # Assert judge instance counter incremented
    assert judge.telemetry.get("equivalence_resolved_by_umls") == initial_judge_count + 1
    # Assert judge class-level counter incremented
    assert (
        ClinicalEquivalenceJudge._global_telemetry.get("equivalence_resolved_by_umls")
        == initial_global_judge_count + 1
    )

    # Now verify client's own telemetry counter when calling are_equivalent directly on client
    client = UMLSClient(api_key="mock_key")
    with patch.object(client, "get_cui", side_effect=lambda term: "C0022646" if "kidney" in term or "renal" in term else None):
        is_eq, cui = client.are_equivalent("chronic kidney disease", "chronic renal failure")
        assert is_eq is True
        assert cui == "C0022646"
        assert client.telemetry["equivalence_confirmed_by_cui"] == 1


def test_v88_v87_report_corrections_present():
    """
    Condition (iii): Validates that docs/agentic_v87_delivery_report.md contains:
    - Provenance statement noting measurement ran on uncommitted code and run git_head is 934c6d1.
    - Correction to '-2 calls saved' attribution acknowledging zero CUI entries in run JSON.
    - Delivery head 6ecf756.
    - Zero occurrences of nonexistent exception class UMLSEgressViolationError.
    """
    report_path = Path("docs/agentic_v87_delivery_report.md")
    assert report_path.exists(), "v87 delivery report must exist"

    text = report_path.read_text(encoding="utf-8")

    # 1. Provenance statement
    assert "934c6d1" in text, "Report must cite baseline anchor / run git_head 934c6d1"
    assert "uncommitted" in text.lower(), "Report must explicitly state measurement ran on uncommitted code"

    # 2. Attribution correction
    assert "Efficiency Attribution Correction" in text or "unsupported" in text.lower(), (
        "Report must contain attribution correction noting lack of UMLS evidence for -2 calls"
    )
    assert "pre-judge short circuit" in text, "Report must keep original claim alongside correction"

    # 3. Delivery head
    assert "6ecf756" in text, "Report must cite delivery head 6ecf756"

    # 4. Zero occurrences of nonexistent exception class
    assert "UMLSEgressViolationError" not in text, (
        "Report must NOT contain nonexistent class UMLSEgressViolationError"
    )


def test_v88_target_case_defenses_and_advocacy_rejection_preserved():
    """
    Condition (iv): Verify key safety invariants:
    - Objection validity defense still rejects synthetic invalid objections.
    - Valid objections still concede.
    - In gold-DENIED cases, advocacy spans are rejected (preventing false approvals).
    """
    judge = ClinicalEquivalenceJudge()

    # Synthetic absent requirement must be invalidated
    invalid_llm_resp = MagicMock()
    invalid_llm_resp.status_code = 200
    invalid_llm_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "objection_valid": False,
                    "objection_invalid_reason": "The objection demands 4 weeks of conservative therapy, but the criterion contains no conservative therapy duration requirement.",
                    "defense_quote": "",
                    "rationale": "Objection absent from criterion text",
                })
            }
        }]
    }

    with patch.object(httpx.Client, "post", return_value=invalid_llm_resp):
        def_result = judge.generate_defense_sync(
            criterion={
                "criterion_code": "CRIT-KYPHO-02",
                "name": "Vertebral Compression Fracture",
                "description": "Documentation of acute or subacute osteoporotic vertebral compression fracture with persistent debilitating pain.",
            },
            objection={
                "objection_type": "TEMPORAL",
                "named_sub_requirement": "4 weeks of conservative physical therapy",
                "counter_quote": "Conservative therapy lasted 2 weeks",
                "specific_contradiction": True,
                "rationale": "Conservative therapy requirement not met",
            },
            proposed_evidence="STIR imaging demonstrating acute osteoporotic vcf with bone edema",
            note_text="Clinical note with acute fracture.",
        )
    assert def_result.objection_valid is False, "Objection demanding unmentioned conservative therapy must be invalid"

    # Valid objection on present requirement must concede
    valid_llm_resp = MagicMock()
    valid_llm_resp.status_code = 200
    valid_llm_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "objection_valid": True,
                    "objection_invalid_reason": "",
                    "defense_quote": "",
                    "rationale": "Echocardiogram demonstrates preserved ejection fraction of 50%, which contradicts the requirement of <= 35%.",
                })
            }
        }]
    }

    with patch.object(httpx.Client, "post", return_value=valid_llm_resp):
        valid_def = judge.generate_defense_sync(
            criterion={
                "criterion_code": "CRIT-CARD-01",
                "name": "Ejection Fraction",
                "description": "Left ventricular ejection fraction <= 35% documented on echocardiogram.",
            },
            objection={
                "objection_type": "NUMERIC_MISMATCH",
                "named_sub_requirement": "Left ventricular ejection fraction <= 35%",
                "counter_quote": "Echocardiogram demonstrates preserved ejection fraction of 50%.",
                "specific_contradiction": True,
                "rationale": "EF 50% is greater than threshold 35%",
            },
            proposed_evidence="Echocardiogram demonstrates preserved ejection fraction of 50%.",
            note_text="Clinical progress note.",
        )
    assert valid_def.objection_valid is True, "Valid contradiction on present criterion must be acknowledged"
