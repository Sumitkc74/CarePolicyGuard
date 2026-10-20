import pytest
from app.schemas.contracts import (
    DeterminationStatus,
    AdjudicationDecision,
    ClinicalEvidenceSpan,
    CriterionAssessment
)
from app.agents.policy_retriever import PolicyRetrievalAgent
from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.agents.packet_generator import CoveragePacketGenerator
from app.agents.pipeline import MultiAgentVerificationPipeline

@pytest.fixture
def sample_ehr():
    return """
    CARDIOLOGY CLINIC NOTE
    PATIENT: [REDACTED]
    
    HISTORY OF PRESENT ILLNESS:
    Patient is a 65-year-old male with ischemic cardiomyopathy.
    Myocardial infarction occurred 18 months ago.
    Symptoms: NYHA Class II heart failure.
    
    DIAGNOSTICS:
    Echocardiogram confirms severe systolic dysfunction with LVEF 28%.
    
    MEDICATIONS:
    Patient compliant with carvedilol 25mg BID and lisinopril 20mg for 6 months.
    
    PLAN:
    Referral for primary prevention ICD under CMS NCD 20.4.
    """

def test_criteria_evaluator_lvef(sample_ehr):
    evaluator = CriteriaEvaluationAgent()
    crit_lvef = {
        "criterion_code": "CRIT-ICD-01",
        "name": "Severe LV Systolic Dysfunction",
        "description": "LVEF <= 35% on echocardiography",
        "is_exclusion": False,
        "keywords": ["lvef", "ejection fraction"]
    }
    assessment = evaluator.evaluate_criterion(crit_lvef, sample_ehr)
    assert assessment.status == DeterminationStatus.MET
    assert len(assessment.verified_spans) > 0
    span = assessment.verified_spans[0]
    # Check exact slice match
    assert sample_ehr[span.start_char:span.end_char] == span.source_text
    assert "28%" in span.source_text

def test_adversarial_verifier_character_grounding(sample_ehr):
    verifier = AdversarialVerificationAgent()
    
    # 1. Valid grounded span
    grounded_span = ClinicalEvidenceSpan(
        source_text="LVEF 28%",
        start_char=sample_ehr.find("LVEF 28%"),
        end_char=sample_ehr.find("LVEF 28%") + len("LVEF 28%"),
        clinical_section="Diagnostics",
        confidence=0.98
    )
    all_grounded, hallucination, drift, notes = verifier.verify_spans_programmatic([grounded_span], sample_ehr)
    assert all_grounded is True
    assert hallucination is False
    assert drift is False

    # 2. Fabricated / Hallucinated span
    hallucinated_span = ClinicalEvidenceSpan(
        source_text="LVEF 12% with severe pulmonary edema",
        start_char=10,
        end_char=45,
        clinical_section="Diagnostics",
        confidence=0.95
    )
    all_grounded, hallucination, drift, notes = verifier.verify_spans_programmatic([hallucinated_span], sample_ehr)
    assert all_grounded is False
    assert hallucination is True

    # 3. Offset Drift span
    actual_pos = sample_ehr.find("NYHA Class II")
    drifted_span = ClinicalEvidenceSpan(
        source_text="NYHA Class II",
        start_char=actual_pos + 50,  # shifted!
        end_char=actual_pos + 50 + len("NYHA Class II"),
        clinical_section="HPI",
        confidence=0.90
    )
    all_grounded, hallucination, drift, notes = verifier.verify_spans_programmatic([drifted_span], sample_ehr)
    assert all_grounded is False
    assert drift is True

def test_adversarial_verifier_negative_omission_audit():
    verifier = AdversarialVerificationAgent()
    ehr_with_lvef = "Cardiology evaluation reveals patient has severe ischemic disease with LVEF 25%."
    
    # Model incorrectly marked NOT_MET for LVEF
    bogus_assessment = CriterionAssessment(
        criterion_id="CRIT-ICD-01",
        criterion_code="CRIT-ICD-01",
        name="LVEF <= 35%",
        description="LVEF <= 35%",
        is_exclusion=False,
        status=DeterminationStatus.NOT_MET,
        verified_spans=[],
        clinical_rationale="No qualifying data found.",
        raw_confidence=0.85
    )
    crit_def = {"criterion_code": "CRIT-ICD-01", "keywords": ["lvef"]}
    omission_flag, note = verifier.audit_negative_omissions(bogus_assessment, crit_def, ehr_with_lvef)
    assert omission_flag is True
    assert "UNVERIFIED OMISSION" in note

def test_calibrated_abstention_gate_deferral():
    gate = CalibratedAbstentionGate(tau=0.85)

    # Low calibrated confidence case -> must abstain
    low_conf_audit = [
        CriterionAssessment(
            criterion_id="1", criterion_code="CRIT-1", name="Test", description="Test",
            is_exclusion=False, status=DeterminationStatus.MET, verified_spans=[],
            clinical_rationale="Borderline", raw_confidence=0.60
        )
    ]
    audit_results = [
        type("AuditObj", (), {
            "criterion_code": "CRIT-1", "grounding_status": True,
            "hallucination_flag": False, "offset_drift_detected": False,
            "unverified_omission_flag": False, "calibrated_confidence": 0.60,
            "audit_notes": "Clean"
        })()
    ]

    decision, abstained, raw_c, cal_c, reason, action_notes = gate.evaluate(low_conf_audit, audit_results)
    assert decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert abstained is True
    assert "falls below safety threshold tau" in reason

@pytest.mark.asyncio
async def test_end_to_end_pipeline_approval(sample_ehr):
    pipeline = MultiAgentVerificationPipeline(db=None)
    result = await pipeline.adjudicate(
        patient_id="PT-TEST-001",
        policy_id="NCD-20.4",
        ehr_narrative=sample_ehr
    )
    assert result.adjudication_decision == AdjudicationDecision.APPROVED
    assert result.abstention_status is False
    assert result.calibrated_aggregate_confidence >= 0.85
    assert len(result.audit_hash) == 64

def test_criteria_evaluator_lvef_hfpef_distinction():
    evaluator = CriteriaEvaluationAgent()
    crit_lvef = {
        "criterion_code": "CRIT-ICD-01",
        "name": "Severe LV Systolic Dysfunction",
        "description": "LVEF <= 35% on echocardiography",
        "is_exclusion": False,
        "keywords": ["lvef", "ejection fraction"]
    }
    
    # Preserved EF (HFpEF)
    hfpef_note = "Transthoracic echocardiogram (TTE) demonstrates preserved ejection fraction with LVEF 55%."
    assessment_hfpef = evaluator.evaluate_criterion(crit_lvef, hfpef_note)
    assert assessment_hfpef.status == DeterminationStatus.NOT_MET
    assert "HFpEF" in assessment_hfpef.clinical_rationale or "Preserved" in assessment_hfpef.clinical_rationale
    assert "Transthoracic Echocardiogram" in assessment_hfpef.clinical_rationale

    # Reduced EF (HFrEF)
    hfref_note = "Diagnostic TTE reveals severely depressed systolic function with LVEF 25%."
    assessment_hfref = evaluator.evaluate_criterion(crit_lvef, hfref_note)
    assert assessment_hfref.status == DeterminationStatus.MET
    assert "HFrEF" in assessment_hfref.clinical_rationale or "systolic" in assessment_hfref.clinical_rationale.lower()
    assert "Transthoracic Echocardiogram" in assessment_hfref.clinical_rationale

def test_criteria_evaluator_gdmt_contraindication_exception():
    evaluator = CriteriaEvaluationAgent()
    crit_gdmt = {
        "criterion_code": "CRIT-ICD-02",
        "name": "Optimal Medical Therapy (GDMT)",
        "description": "Patient on GDMT for at least 90 days or documented intolerance",
        "is_exclusion": False,
        "keywords": ["gdmt", "medical therapy", "carvedilol"]
    }
    
    # Patient with documented contraindication/intolerance (e.g. angioedema to ACEi)
    ehr_contraindication = (
        "Patient has been stable on carvedilol 25mg BID for 6 months (>90 days). "
        "ACE inhibitor and ARNI are strictly contraindicated due to history of severe life-threatening angioedema. "
        "MRA withheld due to recurrent severe hyperkalemia."
    )
    assessment = evaluator.evaluate_criterion(crit_gdmt, ehr_contraindication)
    assert assessment.status == DeterminationStatus.MET
    assert "contraindication" in assessment.clinical_rationale.lower() or "exception" in assessment.clinical_rationale.lower()
    assert len(assessment.verified_spans) > 0

@pytest.mark.asyncio
async def test_coverage_packet_sdm_and_validity_period(sample_ehr):
    pipeline = MultiAgentVerificationPipeline(db=None)
    result = await pipeline.adjudicate(
        patient_id="PT-TEST-002",
        policy_id="NCD-20.4",
        ehr_narrative=sample_ehr
    )
    packet = CoveragePacketGenerator.generate_packet(result, physician_name="Dr. Jane Cardiologist, MD")
    assert packet.authorization_validity_period is not None
    assert "180 Calendar Days" in packet.authorization_validity_period
    assert packet.shared_decision_making_attestation is not None
    assert "Section B.3" in packet.shared_decision_making_attestation


