import pytest
from fastapi.testclient import TestClient

from main import app
from app.db.session import SessionLocal
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.policy_retriever import PolicyRetrievalAgent
from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.schemas.contracts import (
    DeterminationStatus,
    AdjudicationDecision,
    ClinicalEvidenceSpan,
    CriterionAssessment
)

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_negex_negation_scope_detection():
    """
    Verifies that clinical negation ('denies', 'no history of') prevents false-positive
    approvals and marks mandatory criteria as NOT_MET.
    """
    evaluator = CriteriaEvaluationAgent()
    negated_note = (
        "Patient is a 65-year-old male presenting for routine checkup. "
        "Patient explicitly denies dyspnea on exertion. "
        "No history of ischemic cardiomyopathy or heart failure. "
        "Physical exam is unremarkable."
    )

    criterion = {
        "criterion_code": "CRIT-HF",
        "name": "Heart Failure Diagnosis",
        "description": "Documented heart failure symptoms or ischemic cardiomyopathy",
        "is_exclusion": False,
        "keywords": ["heart failure", "cardiomyopathy"]
    }

    assessment = evaluator.evaluate_criterion(criterion, negated_note)
    assert assessment.status == DeterminationStatus.NOT_MET
    assert "explicitly negated" in assessment.clinical_rationale.lower()


def test_family_history_scope_detection():
    """
    Verifies that symptoms or conditions belonging to family members (e.g. 'father')
    are not falsely attributed to the patient.
    """
    evaluator = CriteriaEvaluationAgent()
    family_note = (
        "Patient is a 55-year-old female for evaluation. "
        "Family history is significant: Father had severe ischemic cardiomyopathy and sudden cardiac death. "
        "Patient herself has normal LV function and no cardiac symptoms."
    )

    criterion = {
        "criterion_code": "CRIT-ICM",
        "name": "Ischemic Cardiomyopathy",
        "description": "Patient has documented ischemic cardiomyopathy",
        "is_exclusion": False,
        "keywords": ["ischemic cardiomyopathy"]
    }

    assessment = evaluator.evaluate_criterion(criterion, family_note)
    assert assessment.status == DeterminationStatus.INSUFFICIENT_EVIDENCE
    assert "family" in assessment.clinical_rationale.lower()


def test_multi_span_clinical_discordance_detection():
    """
    Verifies that conflicting measurements in the chart (e.g., LVEF 24% vs LVEF 55%)
    trigger adversarial discordance flags and force human auditor review.
    """
    verifier = AdversarialVerificationAgent()
    conflicting_note = (
        "Initial TTE on 01/10/2026: Severe LV systolic dysfunction with LVEF 24%. "
        "Repeat TTE on 02/15/2026: Recovered cardiac function with LVEF 55%."
    )

    assessment = CriterionAssessment(
        criterion_id="CRIT-1",
        criterion_code="CRIT-1",
        name="LVEF Threshold",
        description="LVEF <= 35%",
        is_exclusion=False,
        status=DeterminationStatus.MET,
        verified_spans=[
            ClinicalEvidenceSpan(
                source_text="LVEF 24%",
                start_char=52,
                end_char=60,
                clinical_section="Diagnostic Studies",
                confidence=0.95
            )
        ],
        clinical_rationale="LVEF 24% documented on initial echo.",
        raw_confidence=0.95
    )

    is_discordant, disc_note = verifier.audit_discordance(assessment, conflicting_note)
    assert is_discordant is True
    assert "discordance" in disc_note.lower()
    assert "24% vs 55%" in disc_note

    # Gate must abstain on discordance
    audit = verifier.audit_assessment(assessment, {"criterion_code": "CRIT-1"}, conflicting_note)
    assert audit.discordance_flag is True

    gate = CalibratedAbstentionGate(tau=0.85)
    decision, abstention_status, _, _, reason, _ = gate.evaluate([assessment], [audit])
    assert decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert abstention_status is True
    assert "discordance" in reason.lower()


def test_autonomous_offset_drift_healing_loop(db):
    """
    Verifies that the multi-agent pipeline autonomously detects and heals
    character offset drifts in evidence spans without requiring human deferral.
    """
    pipeline = MultiAgentVerificationPipeline(db=db)
    raw_text = "Progress Note Header.\nPatient with ischemic cardiomyopathy, documented LVEF 28% on echo. NYHA Class III."

    span_text = "LVEF 28%"
    # Intentionally corrupt the start and end offsets to trigger offset drift
    corrupted_span = ClinicalEvidenceSpan(
        source_text=span_text,
        start_char=10,  # Corrupted start (true start is ~67)
        end_char=18,
        clinical_section="Diagnostic Studies",
        confidence=0.90
    )

    # Verifier detects the drift
    all_grounded, hallucination, offset_drift, _ = pipeline.verifier_agent.verify_spans_programmatic(
        [corrupted_span],
        raw_text
    )
    assert offset_drift is True
    assert not all_grounded

    # Self-healing loop heals the offsets
    healed = pipeline.verifier_agent.heal_offset_drift(corrupted_span, raw_text)
    assert healed is True
    assert raw_text[corrupted_span.start_char:corrupted_span.end_char] == span_text

    # Re-verify healed span
    all_grounded_after, _, offset_drift_after, _ = pipeline.verifier_agent.verify_spans_programmatic(
        [corrupted_span],
        raw_text
    )
    assert all_grounded_after is True
    assert offset_drift_after is False


def test_weakest_link_safety_floor():
    """
    Verifies that if any mandatory inclusion criterion falls below the critical floor (tau_floor=0.65),
    the gate abstains even if the arithmetic mean confidence is high.
    """
    gate = CalibratedAbstentionGate(tau=0.80, tau_floor=0.65)

    crit1 = CriterionAssessment(
        criterion_id="CRIT-AGE",
        criterion_code="CRIT-AGE",
        name="Patient Age",
        description="Age >= 18",
        is_exclusion=False,
        status=DeterminationStatus.MET,
        verified_spans=[],
        clinical_rationale="Age 65 verified.",
        raw_confidence=0.99
    )
    crit2 = CriterionAssessment(
        criterion_id="CRIT-LVEF",
        criterion_code="CRIT-LVEF",
        name="LVEF <= 35%",
        description="Mandatory diagnostic ejection fraction",
        is_exclusion=False,
        status=DeterminationStatus.MET,
        verified_spans=[],
        clinical_rationale="Borderline mention.",
        raw_confidence=0.55  # Below tau_floor
    )

    audit1 = type("MockAudit", (), {"calibrated_confidence": 0.99, "hallucination_flag": False, "offset_drift_detected": False, "unverified_omission_flag": False, "discordance_flag": False, "criterion_code": "CRIT-AGE"})()
    audit2 = type("MockAudit", (), {"calibrated_confidence": 0.55, "hallucination_flag": False, "offset_drift_detected": False, "unverified_omission_flag": False, "discordance_flag": False, "criterion_code": "CRIT-LVEF"})()

    decision, abstained, raw_conf, cal_conf, reason, _ = gate.evaluate([crit1, crit2], [audit1, audit2])
    assert decision == AdjudicationDecision.DEFERRED_TO_HUMAN
    assert abstained is True
    assert "Weakest-link safety floor breached" in reason


def test_clinical_taxonomy_acronym_cross_referencing(db):
    """
    Verifies that colloquial procedure names (e.g. MitraClip, TEER) correctly boost
    relevance for NCD 20.33 via clinical taxonomy cross-referencing.
    """
    retriever = PolicyRetrievalAgent(db=db)
    clinical_note = "Patient referred for urgent MitraClip procedure to address symptomatic severe mitral regurgitation."

    matches = retriever.search_policies_by_narrative(clinical_note)
    assert len(matches) > 0
    top_policy = matches[0]
    assert top_policy["policy_id"] == "NCD-20.33"
    assert "mitraclip" in top_policy["matched_terms"]

