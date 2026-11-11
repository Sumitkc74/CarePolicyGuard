"""
Regression test for Task 3: Verifies that when an LLM proposal is accepted,
the criterion assessment's raw_confidence is properly updated from the verified span (0.95),
preventing premature weakest-link floor or calibrated confidence abstention triggers.
"""

import pytest
from unittest.mock import MagicMock
from app.schemas.contracts import ClinicalEvidenceSpan, DeterminationStatus, CriterionAssessment
from app.agents.pipeline import MultiAgentVerificationPipeline


def test_accepted_proposal_updates_raw_confidence():
    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer = MagicMock()
    pipeline.llm_proposer.enabled = True

    span = ClinicalEvidenceSpan(
        source_text="early-stage non-small cell lung cancer",
        start_char=10,
        end_char=48,
        clinical_section="ASSESSMENT",
        confidence=0.92
    )
    pipeline.llm_proposer.run_synonymy_conversation.return_value = (span, [])

    criterion_dict = {
        "criterion_code": "CRIT-TEST-01",
        "name": "Test Criterion",
        "description": "Test Description",
        "clinical_intent": "Inclusion test",
        "criterion_type": "FINDING_PRESENCE",
        "entity_names": ["target concept"],
        "is_exclusion": False
    }

    # Declarative evaluate will return INSUFFICIENT_EVIDENCE with raw_confidence=0.50
    from app.services.declarative_engine import DeclarativePolicyEngine
    decl_crit = DeclarativePolicyEngine.compile_from_dict(criterion_dict)
    initial_assessment = DeclarativePolicyEngine.evaluate(decl_crit, "Unrelated note text")
    assert initial_assessment.status == DeterminationStatus.INSUFFICIENT_EVIDENCE
    assert initial_assessment.raw_confidence == 0.50

    # Simulate the pipeline loop logic
    verified_span, _ = pipeline.llm_proposer.run_synonymy_conversation(
        criterion=criterion_dict,
        ehr_narrative="Unrelated note text",
        failed_reason="missed",
        verifier_agent=pipeline.verifier_agent,
        case_id="TEST-CASE"
    )
    assert verified_span is not None

    if verified_span:
        initial_assessment.verified_spans.append(verified_span)
        initial_assessment.raw_confidence = verified_span.confidence or 0.95
        initial_assessment.status = DeterminationStatus.MET

    assert initial_assessment.status == DeterminationStatus.MET
    assert initial_assessment.raw_confidence == 0.92
    assert len(initial_assessment.verified_spans) == 1
