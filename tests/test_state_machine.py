import pytest
from app.services.hybrid_retriever import BM25Retriever, DenseSemanticRetriever, HybridPolicyRetriever
from app.agents.llm_extractor import StructuredExtractorAgent, ExtractorTools, CandidateExtraction
from app.agents.state_machine import ClinicalAdjudicationStateMachine, PipelineStage

def test_bm25_retriever():
    docs = [
        {"policy_id": "P1", "content": "Implantable cardioverter defibrillator for heart failure LVEF 30%"},
        {"policy_id": "P2", "content": "Continuous positive airway pressure for obstructive sleep apnea AHI 25"},
        {"policy_id": "P3", "content": "Hyperbaric oxygen therapy for diabetic wound ulcer"}
    ]
    bm25 = BM25Retriever()
    bm25.index_documents(docs)
    
    results = bm25.search("heart failure defibrillator LVEF", top_k=1)
    assert len(results) == 1
    assert results[0][0]["policy_id"] == "P1"
    assert results[0][1] > 0

def test_dense_semantic_retriever():
    docs = [
        {"policy_id": "P1", "content": "implantable cardioverter defibrillator systolic heart failure LVEF"},
        {"policy_id": "P2", "content": "cpap polysomnography obstructive sleep apnea"}
    ]
    dense = DenseSemanticRetriever()
    results = dense.search("defibrillator cardiomyopathy", docs, top_k=1)
    assert len(results) == 1
    assert results[0][0]["policy_id"] == "P1"

def test_extractor_tools_exact_slice():
    raw_text = "Patient diagnosed with ischemic cardiomyopathy. Echocardiogram shows LVEF 28%."
    quote = "LVEF 28%"
    start = raw_text.find(quote)
    end = start + len(quote)
    
    assert ExtractorTools.verify_exact_character_slice(raw_text, quote, start, end) is True
    assert ExtractorTools.verify_exact_character_slice(raw_text, quote, start + 1, end) is False

def test_extractor_tools_temporal_delta():
    days = ExtractorTools.calculate_temporal_delta("2026-01-01", "2026-04-01")
    assert days == 90

def test_extractor_tools_numeric_cutoff():
    assert ExtractorTools.evaluate_numeric_cutoff(28.0, "<=", 35.0) is True
    assert ExtractorTools.evaluate_numeric_cutoff(42.0, "<=", 35.0) is False

def test_structured_extractor_propose():
    extractor = StructuredExtractorAgent(sample_passes=3)
    raw_ehr = "Assessment: Severe systolic heart failure with LVEF 30% and NYHA Class II symptoms."
    crit = {
        "criterion_code": "CRIT-ICD-01",
        "description": "Severe left ventricular systolic dysfunction with LVEF <= 35%",
        "keywords": ["lvef", "ejection fraction"],
        "is_exclusion": False
    }
    candidate = extractor.propose_candidates(raw_ehr, crit)
    assert isinstance(candidate, CandidateExtraction)
    assert candidate.criterion_code == "CRIT-ICD-01"
    assert candidate.status_proposed == "MET"
    assert candidate.numeric_value == 30.0
    assert candidate.sampling_agreement_rate > 0.0

def test_clinical_adjudication_state_machine():
    sm = ClinicalAdjudicationStateMachine(tau=0.85)
    raw_ehr = """
    PROGRESS NOTE
    Patient with non-ischemic cardiomyopathy.
    Echocardiogram: LVEF 28%.
    Current functional status: NYHA Class II.
    GDMT ongoing for 6 months.
    No cardiogenic shock.
    """
    criteria = [
        {"criterion_code": "CRIT-ICD-01", "description": "LVEF <= 35%", "keywords": ["lvef"], "is_exclusion": False},
        {"criterion_code": "CRIT-ICD-02", "description": "NYHA Class II or III", "keywords": ["nyha"], "is_exclusion": False},
        {"criterion_code": "CRIT-ICD-EXCL-01", "description": "Cardiogenic shock exclusion", "keywords": ["shock"], "is_exclusion": True}
    ]
    
    result = sm.execute_state_machine(
        patient_id="PT-9999",
        policy_id="NCD-20.4",
        policy_title="Implantable Automatic Defibrillators",
        criteria_list=criteria,
        raw_ehr_text=raw_ehr
    )
    
    assert result["final_decision"] == "APPROVED"
    assert result["abstention_status"] is False
    assert len(result["transitions_log"]) >= 6
    assert result["state_audit_hash"] is not None
    assert len(result["state_audit_hash"]) == 64  # SHA-256

