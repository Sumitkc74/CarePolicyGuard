import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus, CriterionAssessment, ClinicalEvidenceSpan

def test_red_team_contradictory_lvef_measurements_defers():
    """
    Red-Team Shape 1: Contradictory Notes.
    An earlier echocardiogram progress note documents 'LVEF 28%', while a subsequent
    note in the same chart documents 'LVEF 45% post-revascularization'.
    The adversarial verifier must detect the discordance and the calibrated gate must defer.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    CARDIOLOGY PROGRESS NOTE - 01/10/2026
    Patient evaluated for ischemic cardiomyopathy.
    Echocardiogram: LVEF is 28% with severe apical akinesis. NYHA Class III symptoms.
    Plan: Continue GDMT, re-evaluate after interval medical optimization.

    CARDIOLOGY ADDENDUM - 02/15/2026
    Follow-up assessment post-coronary revascularization.
    Repeat bedside ultrasound: LVEF is 45% with marked functional recovery.
    Plan: Referral for ICD implantation submitted under NCD 20.4.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-RED-LVEF-DISC",
        policy_id="NCD-20.4",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status is True
    assert "discordance" in (res.abstention_reason or "").lower() or "conflict" in (res.abstention_reason or "").lower()

def test_red_team_conflicting_surgical_risk_documentation_defers():
    """
    Red-Team Shape 2: Conflicting Documentation.
    Vascular surgeon documents 'high surgical risk for open CEA due to hostile neck',
    but the anesthesiologist consultation note documents 'low surgical risk / standard risk'.
    System must detect the conflicting risk assessments and defer rather than autonomously approving.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    VASCULAR SURGERY CONSULT:
    73-year-old male with 85% carotid stenosis.
    Surgical evaluation: Patient is at high surgical risk for open carotid endarterectomy
    due to hostile neck anatomy and severe cervical arthritis. Embolic protection device planned.

    ANESTHESIOLOGY PRE-OPERATIVE NOTE:
    Airway exam normal, Mallampati II.
    Cardiopulmonary clearance: Patient evaluated as low surgical risk for general anesthesia and standard risk for CEA.
    Plan: Proceed with CAS under NCD 20.7.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-RED-CAS-CONFLICT",
        policy_id="NCD-20.7",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert res.abstention_status is True
    assert "discordance" in (res.abstention_reason or "").lower() or "conflict" in (res.abstention_reason or "").lower()

def test_red_team_missing_data_vs_negative_finding_distinction():
    """
    Red-Team Shape 3: Missing Data vs Explicit Negative Finding.
    Verifies the critical clinical and legal distinction:
    - Case A: A note with 'no mention of tobacco use / smoking history' when checking
      a smoking requirement yields INSUFFICIENT_EVIDENCE (missing data).
    - Case B: A note explicitly stating 'patient denies tobacco use, lifetime non-smoker'
      yields NOT_MET with a grounded negation trigger.
    """
    from app.services.declarative_engine import DeclarativePolicyEngine
    from app.schemas.declarative_policy import DeclarativeCriterion, CriterionType

    tobacco_criterion = DeclarativeCriterion(
        criterion_code="CRIT-TOB-01",
        name="Tobacco Smoking History",
        description="Documented history of cigarette tobacco use >= 20 pack-years",
        clinical_intent="Identify qualified smoking history",
        criterion_type=CriterionType.FINDING_PRESENCE,
        entity_names=["tobacco use", "smoking history", "cigarette smoker", "tobacco"],
        is_exclusion=False,
        negation_sensitive=True,
        required_temporal_window="Lifetime",
        min_score=0.85
    )

    # Case A: Missing data (no mention)
    note_missing = "55-year-old male presenting for annual checkup. Blood pressure 120/80. Normal exam."
    assessment_missing = DeclarativePolicyEngine.evaluate(tobacco_criterion, note_missing)
    assert assessment_missing.status == DeterminationStatus.INSUFFICIENT_EVIDENCE
    assert len(assessment_missing.verified_spans) == 0

    # Case B: Explicit negative finding (denies tobacco use)
    note_negative = "55-year-old male presenting for annual checkup. Social History: Patient denies tobacco use and never smoked."
    assessment_negative = DeclarativePolicyEngine.evaluate(tobacco_criterion, note_negative)
    assert assessment_negative.status == DeterminationStatus.NOT_MET
    assert len(assessment_negative.verified_spans) > 0
    assert "negated" in assessment_negative.clinical_rationale.lower()

def test_red_team_copy_pasted_outdated_temporal_finding():
    """
    Red-Team Shape 4: Copy-Pasted Interval History with Outdated Temporal Validity.
    Verifies that when a policy requires evidence within a specific temporal window
    (e.g. within 30 days or >= 90 days), a carried-forward note indicating an outdated
    or non-qualifying timeframe defers or denies appropriately.
    """
    pipeline = MultiAgentVerificationPipeline()
    # LCD-TOTAL-KNEE-01 requires conservative therapy failure for >= 90 days (3 months).
    # Here, the patient has only received 14 days of physical therapy carried over from an old note.
    ehr_text = """
    ORTHOPEDIC INTERVAL PROGRESS NOTE
    71-year-old female with bilateral knee osteoarthritis.
    Range of motion: Right knee flexion 80 degrees.
    Treatment History (Carried forward from 2 weeks ago):
    Started physical therapy 14 days ago. Has not tried NSAIDs or injections yet.
    Active infection: None.
    Plan: Request total knee arthroplasty under LCD-TOTAL-KNEE-01.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-RED-OUTDATED-TEMP",
        policy_id="LCD-TOTAL-KNEE-01",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    # 14 days < 90 days minimum conservative therapy duration -> NOT_MET -> DENIED
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    dur_crit = next((c for c in res.criterion_assessments if "tka-02" in c.criterion_code.lower()), None)
    assert dur_crit is not None
    assert dur_crit.status == DeterminationStatus.NOT_MET

