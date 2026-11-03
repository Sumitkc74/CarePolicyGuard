import pytest
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.critic_agent import CriticAgent
from app.agents.missing_evidence_agent import MissingEvidenceAgent
from app.schemas.contracts import AdjudicationDecision, DeterminationStatus, CriterionAssessment


def test_critic_agent_catches_adversarial_approval_and_records_disagreement():
    """
    Task 4: Proves that the Critic Agent actively falsifies provisional approvals
    when counter-evidence (e.g. unaddressed cardiogenic shock or hidden negation) is present,
    and records an explicit agent disagreement.
    """
    critic = CriticAgent()

    # Create mock criteria assessments that are provisionally MET
    assessments = [
        CriterionAssessment(
            criterion_id=1,
            criterion_code="CRIT-ICD-01",
            name="Severe LVEF",
            description="LVEF <= 35%",
            status=DeterminationStatus.MET,
            clinical_rationale="LVEF 25% verified",
            raw_confidence=0.95
        )
    ]

    # Note contains unaddressed cardiogenic shock counter-evidence
    adversarial_ehr = (
        "Patient has LVEF 25% and NYHA Class II heart failure. "
        "However, patient developed acute cardiogenic shock requiring norepinephrine pressor support."
    )

    critic_res = critic.critique_approval(
        provisional_decision=AdjudicationDecision.APPROVED,
        criteria_assessments=assessments,
        ehr_text=adversarial_ehr,
        policy_id="NCD-20.4"
    )

    assert critic_res["falsification_detected"] is True
    assert critic_res["critic_action"] in ("VETO_TO_DENIED", "VETO_TO_DEFERRED")
    assert critic_res["disagreement_recorded"] is True
    assert len(critic_res["objections"]) > 0


def test_no_agent_path_can_bypass_deterministic_veto():
    """
    Task 4: Proves the fundamental architectural invariant:
    'Agents propose; the deterministic engine disposes, and no agent may approve on its own.'
    Even if an agent proposes APPROVED, if any mandatory criterion is unmet,
    the deterministic engine vetoes the proposal to DENIED or DEFERRED.
    """
    pipeline = MultiAgentVerificationPipeline()

    # Note where GDMT and NYHA are completely absent
    incomplete_ehr = (
        "Patient evaluated. Echocardiogram confirms LVEF 25%. Remote MI 2 years ago."
    )
    res = pipeline.adjudicate_sync("PT-TEST-VETO", "NCD-20.4", incomplete_ehr, save_record=False)

    # Invariant: Must NEVER be approved autonomously
    assert res.adjudication_decision != AdjudicationDecision.APPROVED
    assert res.adjudication_decision in (AdjudicationDecision.DENIED, AdjudicationDecision.DEFERRED_TO_HUMAN)


def test_missing_evidence_agent_formulates_targeted_questions():
    """
    Task 4: Proves the MissingEvidenceAgent formulates exact, tailored clinical
    questions for a human reviewer on deferred cases.
    """
    agent = MissingEvidenceAgent()
    criteria = [
        CriterionAssessment(
            criterion_id=1,
            criterion_code="CRIT-ICD-01",
            name="LVEF <= 35%",
            description="Left Ventricular Ejection Fraction <= 35%",
            status=DeterminationStatus.INSUFFICIENT_EVIDENCE,
            clinical_rationale="No LVEF test found in chart",
            raw_confidence=0.5
        ),
        CriterionAssessment(
            criterion_id=2,
            criterion_code="CRIT-ICD-03",
            name="GDMT >= 90 Days",
            description="Guideline-directed medical therapy for >= 90 days",
            status=DeterminationStatus.NOT_MET,
            clinical_rationale="GDMT only 10 days",
            raw_confidence=0.4
        )
    ]
    questions = agent.formulate_questions(criteria, "Implantable Automatic Defibrillators")

    assert len(questions) == 2
    assert any("LVEF" in q for q in questions)
    assert any("GDMT" in q for q in questions)

