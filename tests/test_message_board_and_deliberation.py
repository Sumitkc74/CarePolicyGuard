"""
Tests for CaseMessageBoard, CandidateSpanExtractor, and Deliberation Protocol.
Verifies Task 1 (message board audit trail) and Task 2 (autonomous multi-agent deliberation).
"""

from app.core.candidate_span_extractor import CandidateSpanExtractor
from app.core.concept_map import ConceptDefinition, ConceptMap
from app.schemas.message_board import BoardMessageType, CaseMessageBoard


def test_case_message_board_lifecycle() -> None:
    board = CaseMessageBoard(case_id="TEST-CASE-001")
    assert board.total_messages == 0

    m1 = board.post(
        agent="Agent 1 (Policy Selector)",
        message_type=BoardMessageType.POLICY_SELECTED,
        content="Matched policy POL-TEST with confidence 0.96.",
        metadata={"margin_to_runner_up": 0.22},
    )
    assert m1.sequence_number == 1
    assert m1.agent == "Agent 1 (Policy Selector)"
    assert m1.message_type == BoardMessageType.POLICY_SELECTED

    m2 = board.post(
        agent="Agent 2 (Clinical Extractor)",
        message_type=BoardMessageType.ASSESSMENT_PROPOSED,
        criterion_code="CRIT-01",
        evidence={"source_text": "patient has prostate adenocarcinoma", "start_char": 0, "end_char": 34},
        content="Proposing MET for CRIT-01 based on biopsy note.",
    )
    assert m2.sequence_number == 2
    assert m2.criterion_code == "CRIT-01"

    m3 = board.post(
        agent="Agent 3 (Adversarial Verifier)",
        message_type=BoardMessageType.CHALLENGE,
        criterion_code="CRIT-01",
        content="Challenge: Verifying if biopsy is primary or metastatic.",
    )
    assert m3.sequence_number == 3

    m4 = board.post(
        agent="Agent 2 (Clinical Extractor)",
        message_type=BoardMessageType.DEFENSE,
        criterion_code="CRIT-01",
        content="Defense: Primary prostate adenocarcinoma Gleason 3+4=7 confirmed.",
    )
    assert m4.sequence_number == 4

    m5 = board.post(
        agent="Agent 4 (Adjudicator)",
        message_type=BoardMessageType.DECISION,
        content="Adjudication complete: APPROVED.",
    )
    assert m5.sequence_number == 5
    assert board.total_messages == 5

    transcript = board.render_transcript()
    assert "POLICY_SELECTED" in transcript
    assert "ASSESSMENT_PROPOSED" in transcript
    assert "CHALLENGE" in transcript
    assert "DEFENSE" in transcript
    assert "DECISION" in transcript

    records = board.to_records()
    assert len(records) == 5
    assert records[0]["sequence_number"] == 1
    assert records[4]["message_type"] == "DECISION"


def test_candidate_span_extractor_exact_slices() -> None:
    ehr_text = (
        "HISTORY OF PRESENT ILLNESS:\n"
        "67-year-old male presents with localized prostate adenocarcinoma.\n"
        "PSA is 7.2 ng/mL. Biopsy Gleason score 4+3=7. 3D conformal radiation therapy was planned.\n"
        "However, 3D-CRT plan exceeds rectal wall tolerance constraints.\n"
    )

    criterion = {
        "criterion_code": "CRIT-IMRT-02",
        "name": "3D-CRT tolerance exceeded",
        "description": "3D conformal radiation plan exceeds normal tissue tolerance limits.",
        "keywords": ["tolerance", "rectal wall tolerance", "exceeds"],
    }

    cmap = ConceptMap()
    cmap.register_concept(
        ConceptDefinition(
            concept_id="CONCEPT-IMRT-TOLERANCE",
            canonical_name="3D-CRT tolerance exceeded",
            domain="radiation_oncology",
            accepted_terms=["3d-crt plan exceeds rectal wall tolerance", "tolerance constraints exceeded"],
            source_reason="Radiation tolerance limits",
        )
    )

    candidates = CandidateSpanExtractor.extract_candidates(
        ehr_narrative=ehr_text,
        criterion=criterion,
        concept_map=cmap,
        max_candidates=3,
    )

    assert len(candidates) > 0
    top = candidates[0]
    # Check that slice exactly matches the source narrative
    assert ehr_text[top.start_char : top.end_char] == top.source_text
    assert "tolerance" in top.source_text.lower()


def test_candidate_span_extractor_empty_on_unrelated_text() -> None:
    ehr_text = "Patient underwent routine cataract extraction with phacoemulsification."
    criterion = {
        "criterion_code": "CRIT-CARDIO",
        "name": "Ejection Fraction < 35%",
        "description": "Left ventricular ejection fraction documented below 35 percent.",
        "keywords": ["ejection fraction", "lvef", "ventricular"],
    }

    candidates = CandidateSpanExtractor.extract_candidates(
        ehr_narrative=ehr_text,
        criterion=criterion,
    )
    # Zero overlap with cardiac criterion
    assert len(candidates) == 0
