import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus
from app.services.declarative_engine import DeclarativePolicyEngine

def test_terminal_illness_exclusion_detected():
    """
    Regression Test (Bug a):
    Verifies that a patient with metastatic cancer and life expectancy < 1 year
    is autonomously denied under NCD-20.4, even if 'No cardiogenic shock' is explicitly noted.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    CARDIOLOGY CONSULT NOTE
    Patient with ischemic cardiomyopathy, myocardial infarction 6 months ago.
    Echocardiogram: LVEF 29%.
    Symptoms: NYHA Class II heart failure.
    Medications: Guideline-directed medical therapy for 120 days.
    Oncology: Metastatic pancreatic cancer with life expectancy less than 1 year, currently receiving hospice-directed care planning.
    Exclusions: No cardiogenic shock at present.
    Plan: ICD referral requested.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-REG-A",
        policy_id="NCD-20.4",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.DENIED
    excl_crit = next((c for c in res.criterion_assessments if c.is_exclusion), None)
    assert excl_crit is not None
    assert excl_crit.status == DeterminationStatus.MET

def test_qualitative_severe_aortic_stenosis_defers_without_quantification():
    """
    Regression Test (Bug b):
    Verifies that a clinical note asserting 'severe aortic stenosis' qualitatively
    without quantified AVA, mean gradient, or peak velocity defers to human review
    (DEFERRED_TO_HUMAN), never approving on keyword alone.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    STRUCTURAL HEART NOTE
    Evaluation: 76-year-old male with exertional dyspnea. Echocardiogram report describes
    severe aortic stenosis in qualitative terms only; no aortic valve area, no mean gradient,
    and no peak velocity are recorded in this note.
    Heart Team: Formal multidisciplinary Heart Team consultation completed with cardiac surgery
    and interventional cardiology.
    Plan: TAVR referral under NCD 20.33 pending quantified imaging.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-REG-B",
        policy_id="NCD-20.33",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    tavr_crit = next((c for c in res.criterion_assessments if "tavr-01" in c.criterion_code.lower()), None)
    assert tavr_crit is not None
    assert tavr_crit.status == DeterminationStatus.INSUFFICIENT_EVIDENCE

def test_carotid_high_surgical_risk_hostile_neck_or_radiation():
    """
    Regression Test (Bug c):
    Verifies that Carotid Artery Stenting (NCD 20.7) approves when high surgical risk
    features (hostile neck anatomy, prior radiation) and an EPD are documented,
    without demanding surgeon-plus-cardiologist consensus.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    VASCULAR SURGERY NOTE
    Evaluation: 73-year-old male with recent transient ischemic attack and left carotid artery
    stenosis of 85% on carotid duplex ultrasound.
    Surgical risk: High risk for open carotid endarterectomy due to hostile neck anatomy and prior neck radiation.
    Procedure plan: Carotid artery stenting with deployment of an FDA-approved distal embolic protection device (filter system).
    Plan: Carotid stenting referral under NCD 20.7.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-REG-C",
        policy_id="NCD-20.7",
        ehr_narrative=ehr_text,
        execution_mode="deterministic",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    risk_crit = next((c for c in res.criterion_assessments if "cas-02" in c.criterion_code.lower()), None)
    assert risk_crit is not None
    assert risk_crit.status == DeterminationStatus.MET

def test_cha2ds2_score_token_not_parsed_as_internal_digit():
    """
    Regression Test (Bug d):
    Verifies that declarative numeric extraction parses 'CHA2DS2-VASc score is 4' as 4.0,
    rather than extracting the internal acronym digit '2' from CHA2 or DS2.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    ELECTROPHYSIOLOGY NOTE
    74-year-old female with persistent non-valvular atrial fibrillation. CHA2DS2-VASc score is 4.
    Anticoagulation history: Recurrent major gastrointestinal hemorrhage on apixaban;
    treating team documents contraindication to long-term oral anticoagulation. HAS-BLED score is 4.
    Imaging: CTA within 48 hours confirms absence of left atrial thrombus and suitable appendage anatomy.
    Plan: Percutaneous left atrial appendage closure (Watchman) under NCD 220.13.
    """
    res = pipeline.adjudicate_sync(
        patient_id="PT-TEST-REG-D",
        policy_id="NCD-220.13",
        ehr_narrative=ehr_text,
        execution_mode="declarative",
        save_record=False
    )
    assert res.adjudication_decision == AdjudicationDecision.APPROVED
    laac_crit = next((c for c in res.criterion_assessments if "laac-01" in c.criterion_code.lower()), None)
    assert laac_crit is not None
    assert laac_crit.status == DeterminationStatus.MET
    assert "4.0" in laac_crit.clinical_rationale or "4" in laac_crit.clinical_rationale

def test_state_machine_mode_safety_gate_blocks_false_approvals():
    """
    Regression Test (State Machine Mode Safety):
    Verifies that State Machine mode CANNOT falsely approve unverified, unquantified,
    or contraindicated presentations.
    """
    pipeline = MultiAgentVerificationPipeline()
    
    # 1. Active septic arthritis must DENY, not approve
    septic_ehr = """
    ORTHOPEDIC NOTE
    Severe right knee osteoarthritis with flexion 75 degrees.
    Conservative management for 210 days failed.
    Active septic arthritis of the right knee confirmed on joint aspiration with positive culture.
    Plan: Total knee arthroplasty requested.
    """
    res_septic = pipeline.adjudicate_sync(
        patient_id="PT-SM-SAFE-1",
        policy_id="LCD-TOTAL-KNEE-01",
        ehr_narrative=septic_ehr,
        execution_mode="state_machine",
        save_record=False
    )
    assert res_septic.adjudication_decision == AdjudicationDecision.DENIED

    # 2. Left atrial thrombus present on TEE must DENY or DEFER, never APPROVE
    thrombus_ehr = """
    ELECTROPHYSIOLOGY NOTE
    Persistent non-valvular atrial fibrillation. CHA2DS2-VASc score is 5.
    HAS-BLED score is 3 with prior intracranial hemorrhage.
    Imaging: Transesophageal echocardiogram (TEE) demonstrates a left atrial thrombus measuring 12 mm.
    Plan: LAAC requested.
    """
    res_thrombus = pipeline.adjudicate_sync(
        patient_id="PT-SM-SAFE-2",
        policy_id="NCD-220.13",
        ehr_narrative=thrombus_ehr,
        execution_mode="state_machine",
        save_record=False
    )
    assert res_thrombus.adjudication_decision != AdjudicationDecision.APPROVED

def test_cpap_5_to_14_band_negated_comorbidities_denies_across_all_modes():
    """
    Regression Test (HOLD-05):
    Verifies that an AHI in the 5-14 band (8.2 events/hr) with explicitly negated
    comorbidities (denies daytime sleepiness, no hypertension, no history of stroke)
    evaluates to an autonomous DENIAL (not a deferral) across deterministic,
    state_machine, and declarative modes, with zero false approvals.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    SLEEP MEDICINE NOTE
    Pre-Test Evaluation: Face-to-face clinical evaluation completed on 01/12/2026.
    Review: Patient denies excessive daytime sleepiness. No hypertension, no history of stroke, no insomnia documented.
    Polysomnography: Diagnostic overnight sleep study completed on 02/01/2026.
    Apnea-Hypopnea Index (AHI): 8.2 events/hr.
    Plan: CPAP therapy requested under LCD L33829.
    """
    for mode in ["deterministic", "state_machine", "declarative"]:
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-HOLD-05",
            policy_id="LCD-L33829",
            ehr_narrative=ehr_text,
            execution_mode=mode,
            save_record=False
        )
        assert res.adjudication_decision == AdjudicationDecision.DENIED, f"Mode {mode} failed to deny HOLD-05"
        assert res.abstention_status is False, f"Mode {mode} deferred instead of denying"

def test_laac_thrombus_on_imaging_denies_across_all_modes():
    """
    Regression Test (HOLD-10):
    Verifies that a patient with AF and high stroke risk who demonstrates a left atrial
    thrombus on pre-procedural imaging is autonomously DENIED across deterministic,
    state_machine, and declarative modes.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    ELECTROPHYSIOLOGY NOTE
    71-year-old male with persistent non-valvular atrial fibrillation. CHA2DS2-VASc score is 5.
    Anticoagulation history: Prior intracranial hemorrhage; contraindication to long-term oral anticoagulation documented. HAS-BLED score is 3.
    Imaging: Transesophageal echocardiogram (TEE) demonstrates a left atrial thrombus measuring 12 mm in the appendage.
    Plan: LAAC referral held pending thrombus resolution.
    """
    for mode in ["deterministic", "state_machine", "declarative"]:
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-HOLD-10",
            policy_id="NCD-220.13",
            ehr_narrative=ehr_text,
            execution_mode=mode,
            save_record=False
        )
        assert res.adjudication_decision == AdjudicationDecision.DENIED, f"Mode {mode} failed to deny HOLD-10"
        assert res.abstention_status is False, f"Mode {mode} deferred instead of denying"

def test_hold_08_tavr_qualitative_omission_defers_across_all_modes():
    """
    Regression Test (HOLD-08):
    Verifies that TAVR referral with qualitative stenosis and missing AVA/gradient/velocity
    defers to human review (DEFERRED_TO_HUMAN) across deterministic, state_machine, and
    declarative modes, and that the sentence-initial 'no aortic valve area...' does NOT
    erroneously negate subsequent 'Heart Team' documentation.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    STRUCTURAL HEART NOTE
    PATIENT: [REDACTED] | MRN: [REDACTED]

    EVALUATION:
    76-year-old male with exertional dyspnea. Echocardiogram report describes severe aortic stenosis in qualitative terms only; no aortic valve area, no mean gradient, and no peak velocity are recorded in this note.
    Heart Team: Formal multidisciplinary Heart Team consultation completed with cardiac surgery and interventional cardiology.

    PLAN:
    TAVR referral under NCD 20.33 pending quantified imaging.

    ATTENDING PHYSICIAN:
    Dr. Laura Bennett, MD
    Electronically signed on 02/17/2026.
    """
    for mode in ["deterministic", "state_machine", "declarative"]:
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-HOLD-08",
            policy_id="NCD-20.33",
            ehr_narrative=ehr_text,
            execution_mode=mode,
            save_record=False
        )
        assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN, f"Mode {mode} returned {res.adjudication_decision} instead of DEFERRED_TO_HUMAN"
        assert res.abstention_status is True, f"Mode {mode} did not trigger abstention"

def test_hold_12_hbot_duration_omission_defers_across_all_modes():
    """
    Regression Test (HOLD-12):
    Verifies that HBOT referral with Wagner Grade 3 ulcer but unrecorded treatment duration
    defers to human review (DEFERRED_TO_HUMAN) across deterministic, state_machine, and
    declarative modes, and that preceding 'no day count' does NOT falsely negate distal perfusion.
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    WOUND CARE CONSULTATION
    PATIENT: [REDACTED] | MRN: [REDACTED]

    WOUND ASSESSMENT:
    61-year-old female with Type 2 diabetes and a deep right foot ulcer, Wagner Grade 3 with tendon involvement.
    STANDARD TREATMENT COURSE:
    Patient has received standard wound care for several weeks, including debridement and offloading; no day count is recorded in this note.
    PERFUSION ASSESSMENT:
    Adequate distal perfusion documented on arterial duplex.

    PLAN:
    Hyperbaric oxygen therapy requested under NCD 20.29 pending treatment-duration records.

    ATTENDING PHYSICIAN:
    Dr. Rachel Adams, MD
    Electronically signed on 02/11/2026.
    """
    for mode in ["deterministic", "state_machine", "declarative"]:
        res = pipeline.adjudicate_sync(
            patient_id="PT-TEST-HOLD-12",
            policy_id="NCD-20.29",
            ehr_narrative=ehr_text,
            execution_mode=mode,
            save_record=False
        )
        assert res.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN, f"Mode {mode} returned {res.adjudication_decision} instead of DEFERRED_TO_HUMAN"
        assert res.abstention_status is True, f"Mode {mode} did not trigger abstention"


