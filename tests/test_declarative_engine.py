import pytest
from app.services.declarative_engine import DeclarativePolicyEngine
from app.schemas.declarative_policy import DeclarativePolicy, DeclarativeCriterion, CriterionType
from app.schemas.contracts import DeterminationStatus
from app.agents.policy_retriever import PolicyRetrievalAgent

def test_declarative_policy_engine_loads_all_cms_policies():
    """Verifies that all 5 CMS policies load directly from structured declarative JSON files."""
    policies = DeclarativePolicyEngine.get_all_policies()
    assert len(policies) >= 5
    policy_ids = {p.policy_id for p in policies}
    assert "NCD-20.4" in policy_ids
    assert "LCD-L33829" in policy_ids
    assert "NCD-20.33" in policy_ids
    assert "NCD-220.13" in policy_ids
    assert "NCD-20.29" in policy_ids

def test_declarative_policy_engine_evaluates_ncd_20_4():
    """Evaluates NCD-20.4 declarative criteria against clinical documentation."""
    policy = DeclarativePolicyEngine.load_policy("NCD-20.4")
    assert policy is not None
    assert len(policy.criteria) == 5

    ehr_text = """
    CARDIOLOGY PROGRESS NOTE
    Patient with non-ischemic cardiomyopathy.
    Echocardiogram demonstrates LVEF 26%.
    NYHA Class II functional symptoms.
    GDMT ongoing with Carvedilol and Lisinopril for > 120 days.
    No cardiogenic shock.
    """
    
    assessments = DeclarativePolicyEngine.evaluate_policy(policy, ehr_text)
    assert len(assessments) == 5
    
    # Check LVEF assessment
    lvef_a = next(a for a in assessments if a.criterion_code == "CRIT-ICD-01")
    assert lvef_a.status == DeterminationStatus.MET
    assert len(lvef_a.verified_spans) == 1
    assert "LVEF 26%" in lvef_a.verified_spans[0].source_text

    # Check GDMT duration assessment
    gdmt_a = next(a for a in assessments if a.criterion_code == "CRIT-ICD-03")
    assert gdmt_a.status == DeterminationStatus.MET

    # Check exclusion assessment
    shock_a = next(a for a in assessments if a.criterion_code == "CRIT-ICD-EXCL-01")
    assert shock_a.status == DeterminationStatus.NOT_MET  # Exclusion NOT met means clean

def test_declarative_policy_engine_zero_code_custom_policy():
    """
    Proves scalability: Defines a brand new policy entirely in data/JSON schema,
    evaluating it deterministically with ZERO python code changes.
    """
    custom_policy_data = {
        "policy_id": "LCD-TOTAL-KNEE-01",
        "title": "Total Knee Arthroplasty (TKA)",
        "jurisdiction": "Local Coverage Determination",
        "effective_date": "2026-01-01",
        "category": "Orthopedics",
        "description": "Coverage for primary total knee arthroplasty in severe osteoarthritis.",
        "criteria": [
            {
                "criterion_code": "CRIT-TKA-01",
                "name": "Knee Range of Motion / Flexion Contracture",
                "description": "Documented knee flexion contracture or motion <= 90 degrees.",
                "clinical_intent": "Mandatory structural mobility deficit",
                "criterion_type": "NUMERIC_THRESHOLD",
                "entity_names": ["flexion", "range of motion", "ROM"],
                "operator": "<=",
                "threshold": 90.0,
                "target_unit": "degrees",
                "is_exclusion": False,
                "negation_sensitive": True,
                "required_temporal_window": "Within past 3 months"
            },
            {
                "criterion_code": "CRIT-TKA-02",
                "name": "Failure of Conservative Therapy Duration",
                "description": "Failure of non-surgical conservative therapy (physical therapy, NSAIDs, injections) for >= 180 days.",
                "clinical_intent": "Conservative management prerequisite",
                "criterion_type": "TEMPORAL_DURATION",
                "entity_names": ["conservative therapy", "physical therapy", "PT", "injections"],
                "operator": ">=",
                "min_duration_days": 180,
                "is_exclusion": False,
                "negation_sensitive": True,
                "required_temporal_window": ">= 180 days"
            },
            {
                "criterion_code": "CRIT-TKA-EXCL-01",
                "name": "Active Joint Infection Exclusion",
                "description": "Patient must not have active septic arthritis or active systemic infection.",
                "clinical_intent": "Surgical infection risk exclusion",
                "criterion_type": "EXCLUSION_SYMPTOM",
                "entity_names": ["septic arthritis", "active infection", "joint sepsis"],
                "is_exclusion": True,
                "negation_sensitive": True,
                "required_temporal_window": "Current presentation"
            }
        ]
    }
    
    policy = DeclarativePolicy(**custom_policy_data)
    
    # Test qualifying case
    qualifying_note = """
    ORTHOPEDIC SURGERY CLINIC
    Patient with severe tricompartmental knee osteoarthritis.
    Physical Exam: Right knee range of motion limited to flexion 80 degrees.
    Conservative management: Failed physical therapy and joint injections for 7 months (210 days).
    Labs/Infection: No active infection, no septic arthritis.
    Plan: Proceed with Right Total Knee Arthroplasty.
    """
    
    results = DeclarativePolicyEngine.evaluate_policy(policy, qualifying_note)
    assert len(results) == 3
    assert results[0].status == DeterminationStatus.MET
    assert results[1].status == DeterminationStatus.MET
    assert results[2].status == DeterminationStatus.NOT_MET  # Exclusion not met -> Passed
    
    # Test non-qualifying case (flexion 110 degrees > 90)
    non_qualifying_note = """
    ORTHOPEDIC NOTE
    Patient with mild right knee pain.
    Physical Exam: Right knee flexion 110 degrees.
    Conservative management for 30 days.
    """
    results_fail = DeclarativePolicyEngine.evaluate_policy(policy, non_qualifying_note)
    assert results_fail[0].status == DeterminationStatus.NOT_MET
    assert results_fail[1].status == DeterminationStatus.NOT_MET

def test_policy_retriever_without_db_loads_declarative_criteria():
    """Verifies PolicyRetrievalAgent loads criteria from DeclarativePolicyEngine when DB is None."""
    retriever = PolicyRetrievalAgent(db=None)
    crits = retriever.get_structured_criteria("NCD-20.4")
    assert len(crits) == 5
    codes = [c["criterion_code"] for c in crits]
    assert "CRIT-ICD-01" in codes
    assert "CRIT-ICD-02" in codes
    assert "CRIT-ICD-03" in codes

