import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.schemas.contracts import AdjudicationDecision, FinalAdjudication
from app.agents.benchmark_engine import BENCHMARK_VIGNETTES
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_pipeline_policy_auto_discovery_sleep_apnea():
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    CLINICAL PROGRESS NOTE
    Patient: John Doe, 54yo male
    Chief Complaint: Excessive daytime sleepiness, witnessed apneas by spouse, loud snoring.
    Polysomnography (PSG) completed:
    Apnea-Hypopnea Index (AHI): 28.4 events per hour (Severe OSA).
    Epworth Sleepiness Scale: 16/24.
    Prescription: Continuous positive airway pressure (CPAP) device with heated humidifier.
    Face-to-face clinical evaluation completed prior to PSG.
    """
    
    # Adjudicate with policy_id="AUTO"
    result = pipeline.adjudicate_sync(
        patient_id="PT-AUTO-01",
        policy_id="AUTO",
        ehr_narrative=ehr_text,
        save_record=False
    )
    
    assert isinstance(result, FinalAdjudication)
    assert result.policy_id == "LCD-L33829"
    assert result.retrieval_insights is not None
    assert result.retrieval_insights["auto_discovered"] is True
    assert result.retrieval_insights["selected_policy_id"] == "LCD-L33829"
    assert len(result.retrieval_insights["candidates"]) > 0

def test_pipeline_policy_auto_discovery_heart_failure():
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    CARDIOLOGY CONSULTATION NOTE
    Patient with ischemic cardiomyopathy, prior myocardial infarction 18 months ago.
    Echocardiogram: Left ventricular ejection fraction (LVEF) 26%.
    NYHA functional classification: Class III dyspnea on minimal exertion.
    Guideline-directed medical therapy (GDMT): Carvedilol 25mg BID, Entresto 49/51mg BID, Spironolactone 25mg daily for 8 months.
    Recommendation: Single-chamber implantable cardioverter defibrillator (ICD) for primary prevention.
    """
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-AUTO-02",
        policy_id=None,  # None defaults to auto-discovery
        ehr_narrative=ehr_text,
        save_record=False
    )
    
    assert isinstance(result, FinalAdjudication)
    assert result.policy_id == "NCD-20.4"
    assert result.retrieval_insights is not None
    assert result.retrieval_insights["auto_discovered"] is True

def test_pipeline_state_machine_execution_mode():
    pipeline = MultiAgentVerificationPipeline()
    ehr_text = """
    CARDIOLOGY NOTE
    History: Non-ischemic dilated cardiomyopathy diagnosed 2024.
    Diagnostic testing: Transthoracic echocardiogram demonstrates LVEF 28%.
    Clinical status: NYHA Class II symptoms with mild fatigue during uphill walking.
    Medical therapy: Optimal GDMT with Metoprolol succinate 100mg and Lisinopril 20mg for > 120 days.
    No cardiogenic shock, no active cardiac ischemia, no non-cardiac disease limiting life expectancy to < 1 year.
    Plan: Implantable cardioverter defibrillator (ICD) implantation.
    """
    
    result = pipeline.adjudicate_sync(
        patient_id="PT-SM-01",
        policy_id="NCD-20.4",
        ehr_narrative=ehr_text,
        execution_mode="state_machine",
        save_record=False
    )
    
    assert isinstance(result, FinalAdjudication)
    assert result.execution_mode == "state_machine"
    assert result.adjudication_decision == AdjudicationDecision.APPROVED
    assert result.abstention_status is False
    assert result.state_transitions is not None
    assert len(result.state_transitions) >= 6
    
    # Check that transition steps include all essential stages
    stages = [t["stage"] for t in result.state_transitions]
    assert "STAGE_0_INITIALIZATION" in stages
    assert "STAGE_1_HYBRID_POLICY_RETRIEVAL" in stages
    assert "STAGE_2_STRUCTURED_EXTRACTOR_PROPOSAL" in stages
    assert "STAGE_3_CRITIC_ADVERSARIAL_CROSS_EXAM" in stages
    assert "STAGE_4_DETERMINISTIC_SLICE_VERIFICATION" in stages
    assert "STAGE_5_CALIBRATED_ABSTENTION_GATE" in stages
    assert "STAGE_6_ADJUDICATION_FINALIZED" in stages

    assert len(result.audit_hash) == 64
    assert len(result.criterion_assessments) > 0
    assert len(result.verification_audits) > 0

def test_state_machine_mode_concordance_on_all_vignettes():
    """
    Verifies that state-machine mode achieves 10/10 concordance with gold CMS labels
    and matches deterministic mode decisions across all 10 benchmark vignettes.
    """
    pipeline = MultiAgentVerificationPipeline()
    for v in BENCHMARK_VIGNETTES:
        gold = v["gold_decision"]
        res_det = pipeline.adjudicate_sync(
            patient_id=f"PT-EVAL-{v['id']}",
            policy_id=v["policy_id"],
            ehr_narrative=v["ehr"],
            execution_mode="deterministic",
            save_record=False
        )
        res_sm = pipeline.adjudicate_sync(
            patient_id=f"PT-EVAL-{v['id']}",
            policy_id=v["policy_id"],
            ehr_narrative=v["ehr"],
            execution_mode="state_machine",
            save_record=False
        )
        # Both modes must match the gold CMS statutory determination
        assert res_det.adjudication_decision.value == gold, f"Deterministic failed on {v['id']}"
        assert res_sm.adjudication_decision.value == gold, f"State machine failed on {v['id']}"
        # Both modes must yield the exact same decision
        assert res_sm.adjudication_decision == res_det.adjudication_decision

def test_api_adjudicate_endpoint_with_auto_and_state_machine():
    payload = {
        "patient_id": "PT-API-TEST",
        "policy_id": "AUTO",
        "execution_mode": "state_machine",
        "ehr_narrative": """
        CARDIOLOGY PROGRESS NOTE
        Patient with non-ischemic cardiomyopathy diagnosed in 2024.
        Echocardiogram: LVEF 28%.
        NYHA Functional Class: Class II.
        GDMT: Metoprolol succinate and Lisinopril for 6 months.
        No cardiogenic shock.
        Plan: Implantable Cardioverter Defibrillator (ICD).
        """,
        "options": {"save_record": False}
    }
    
    response = client.post("/api/v1/adjudicate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["policy_id"] == "NCD-20.4"
    assert data["execution_mode"] == "state_machine"
    assert data["adjudication_decision"] == "APPROVED"
    assert data["state_transitions"] is not None
    assert len(data["state_transitions"]) >= 6
    assert data["retrieval_insights"]["auto_discovered"] is True
