import json
import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, ClinicalEvidenceSpan
from app.services.semantic_verifier import SemanticSupportChecker


def test_mechanically_valid_span_fails_if_semantically_unsupported():
    """
    Task 3: Proves that a span matching character-for-character (mechanically grounded)
    does NOT count as evidence if it fails semantic support (e.g. wrong subject/family history).
    """
    note = "FAMILY HISTORY: Father had severe heart failure and documented LVEF 22%."
    start = note.find("LVEF 22%")
    end = start + len("LVEF 22%")

    span = ClinicalEvidenceSpan(
        source_text="LVEF 22%",
        start_char=start,
        end_char=end,
        clinical_section="Family History",
        confidence=0.98
    )

    # Verify character-slice identity
    assert note[start:end] == span.source_text

    # Run semantic support audit
    SemanticSupportChecker.verify_span_semantics(span, note)

    # Must fail semantic support because experiencer is the father, not the patient
    assert span.subject_valid is False
    assert span.semantic_support_passed is False
    assert len(span.semantic_invalidation_reasons) > 0


def test_semantic_dimensions_isolation():
    """
    Task 3: Tests each semantic dimension individually:
    1. Subject (Family History)
    2. Timing (Future planned)
    3. Modality (Hypothetical / conditional)
    4. Negation (Negated finding)
    5. Value out of range
    """
    # 1. Family History
    s1_text = "Family history notable for ischemic cardiomyopathy."
    span1 = ClinicalEvidenceSpan(source_text="ischemic cardiomyopathy", start_char=27, end_char=50, clinical_section="FHx")
    SemanticSupportChecker.verify_span_semantics(span1, s1_text)
    assert span1.subject_valid is False
    assert span1.semantic_support_passed is False

    # 2. Timing (Future planned)
    s2_text = "Patient is scheduled for elective CRT-D implantation."
    span2 = ClinicalEvidenceSpan(source_text="CRT-D implantation", start_char=34, end_char=52, clinical_section="Plan")
    SemanticSupportChecker.verify_span_semantics(span2, s2_text)
    assert span2.timing_valid is False
    assert span2.semantic_support_passed is False

    # 3. Modality (Hypothetical)
    s3_text = "Consider implantable cardioverter defibrillator if ventricular tachycardia recurs."
    span3 = ClinicalEvidenceSpan(source_text="defibrillator", start_char=33, end_char=46, clinical_section="Assessment")
    SemanticSupportChecker.verify_span_semantics(span3, s3_text)
    assert span3.modality_valid is False
    assert span3.semantic_support_passed is False

    # 4. Negation
    s4_text = "Patient denies any excessive daytime sleepiness."
    span4 = ClinicalEvidenceSpan(source_text="excessive daytime sleepiness", start_char=19, end_char=47, clinical_section="ROS")
    SemanticSupportChecker.verify_span_semantics(span4, s4_text)
    assert span4.negation_valid is False
    assert span4.semantic_support_passed is False

    # 5. Value out of range
    s5_text = "Transthoracic echocardiogram reveals resting LVEF 48%."
    span5 = ClinicalEvidenceSpan(source_text="LVEF 48%", start_char=45, end_char=53, clinical_section="Echocardiogram")
    crit_def = {"operator": "<=", "threshold": 35.0, "target_unit": "%"}
    SemanticSupportChecker.verify_span_semantics(span5, s5_text, criterion_def=crit_def)
    assert span5.value_in_range is False
    assert span5.semantic_support_passed is False


def test_contradiction_detection_surfaces_conflicts_as_deferral():
    """
    Task 3: Proves that conflicting diagnostic measurements across sections
    (e.g., LVEF 22% in HPI vs LVEF 56% in Echo) surface as a deferral rather than silent pick.
    """
    pipeline = MultiAgentVerificationPipeline()
    contradictory_ehr = (
        "CARDIOLOGY PROGRESS NOTE\n"
        "HPI: Patient seen for heart failure. Previous outside echo on 10/01 reported LVEF 22%.\n"
        "DIAGNOSTICS: Repeat comprehensive inpatient echocardiogram on 10/15 reveals LVEF 56% with normal systolic function.\n"
        "PLAN: NYHA Class II. On GDMT."
    )
    res = pipeline.adjudicate_sync("PT-TEST-CONTRA", "NCD-20.4", contradictory_ehr, save_record=False)

    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status is True
    assert "contradiction" in res.abstention_reason.lower() or "discordance" in res.abstention_reason.lower()


def test_adversarial_dev_set_all_rejected_or_deferred():
    """
    Task 3: Executes the complete adversarial development set extension (8 cases)
    and asserts 100% safety (zero false approvals).
    """
    pipeline = MultiAgentVerificationPipeline()
    with open("app/data/benchmarks/adversarial_dev_cases.json", "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) == 8

    results = []
    for case in cases:
        res = pipeline.adjudicate_sync(
            patient_id=case["case_id"],
            policy_id=case["policy_id"],
            ehr_narrative=case["narrative"],
            save_record=False
        )
        # CRITICAL SAFETY INVARIANT: None of the adversarial cases may be APPROVED!
        assert res.adjudication_decision != AdjudicationDecision.APPROVED, (
            f"Adversarial safety failure on case {case['case_id']} ({case['name']}): "
            f"Falsely approved with confidence {res.calibrated_aggregate_confidence}!"
        )
        results.append({
            "case_id": case["case_id"],
            "name": case["name"],
            "decision": res.adjudication_decision.value,
            "passed": True
        })

    # Assert 100% adversarial pass rate (8/8)
    assert all(r["passed"] for r in results)

