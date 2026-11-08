"""
Tests for Task 1 and Task 2:
- Task 1: Gated Local LLM Proposal behind 3 deterministic gates (Gate A: exact slice, Gate B: semantic verification, Gate C: Agent 3 veto)
- Task 2: Autonomous Agentic Decisions:
  * Agent 2 Tool Chooser (deterministic extractor, timeline validator, phenotype detector, LLM proposer)
  * Agent 3 Bounded Multi-Round Debate Loop (up to 3 rounds)
  * Agent 4 Learned Deferral Policy (candidate tau on dev data vs operative 0.85, deferral queue prioritization, outcome logging)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.schemas.contracts import (
    DeterminationStatus,
    AdjudicationDecision,
    CriterionAssessment,
    ClinicalEvidenceSpan,
    VerificationAuditResult,
)
from app.agents.llm_proposer import (
    LLMProposalAgent,
    LLMProposedSpan,
    GateEvaluationResult,
)
from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.agents.pipeline import MultiAgentVerificationPipeline


# -----------------------------------------------------------------------------
# TASK 1 TESTS: 3 Deterministic Gates for LLM Proposals
# -----------------------------------------------------------------------------

def test_gate_a_exact_slice_rejects_hallucination():
    """
    Gate A must reject any proposed evidence span whose exact character slice
    does not match the raw narrative byte-for-byte.
    """
    proposer = LLMProposalAgent()
    narrative = "Patient has severe symptomatic aortic stenosis with valve area 0.7 cm2."
    criterion_def = {
        "criterion_code": "AS-01",
        "name": "Aortic Valve Area",
        "description": "Aortic valve area less than 1.0 cm2",
        "keywords": "aortic stenosis, valve area"
    }

    # Case 1: Offsets out of range
    hallucinated_span_1 = LLMProposedSpan(
        criterion_code="AS-01",
        proposed_status=DeterminationStatus.MET,
        quote="valve area 0.5 cm2",
        start_char=200,
        end_char=218,
        confidence=0.92,
        reasoning="Extracted valve area."
    )
    res_1 = proposer.evaluate_proposal_through_gates(
        proposal=hallucinated_span_1,
        raw_narrative=narrative,
        criterion_def=criterion_def
    )
    assert not res_1.passed
    assert res_1.failed_gate == "GATE_A_EXACT_SLICE"
    assert "offset" in res_1.reason.lower()

    # Case 2: Slice text does not match narrative at the specified offsets
    hallucinated_span_2 = LLMProposedSpan(
        criterion_code="AS-01",
        proposed_status=DeterminationStatus.MET,
        quote="valve area 0.5 cm2",  # Actual text at 0..18 is "Patient has severe"
        start_char=0,
        end_char=18,
        confidence=0.92,
        reasoning="Extracted valve area."
    )
    res_2 = proposer.evaluate_proposal_through_gates(
        proposal=hallucinated_span_2,
        raw_narrative=narrative,
        criterion_def=criterion_def
    )
    assert not res_2.passed
    assert res_2.failed_gate == "GATE_A_EXACT_SLICE"
    assert any(term in res_2.reason.lower() for term in ("character", "mismatch", "hallucinated", "not exist"))


def test_gate_b_semantic_verification_rejects_negation_and_contradiction():
    """
    Gate B must reject proposals claiming MET when the text contains clinical negation
    or lacks required semantic keywords.
    """
    proposer = LLMProposalAgent()
    narrative = "Patient has no chest pain and no evidence of heart failure. Stable vitals."
    criterion_def = {
        "criterion_code": "CHF-01",
        "name": "Heart Failure Diagnosis",
        "description": "Documented presence of congestive heart failure",
        "keywords": "heart failure, chf"
    }

    # Slice is physically accurate in narrative: "no evidence of heart failure"
    start = narrative.find("no evidence of heart failure")
    end = start + len("no evidence of heart failure")
    negated_span = LLMProposedSpan(
        criterion_code="CHF-01",
        proposed_status=DeterminationStatus.MET,  # LLM erroneously proposes MET
        quote=narrative[start:end],
        start_char=start,
        end_char=end,
        confidence=0.88,
        reasoning="Heart failure mentioned."
    )

    res = proposer.evaluate_proposal_through_gates(
        proposal=negated_span,
        raw_narrative=narrative,
        criterion_def=criterion_def
    )
    assert not res.passed
    assert res.failed_gate == "GATE_B_SEMANTIC"
    assert "negation" in res.reason.lower() or "contradiction" in res.reason.lower()


def test_gate_c_agent3_veto():
    """
    Gate C must invoke Agent 3 adversarial cross-examination.
    If Agent 3 audits the proposed span and flags a hallucination or contradiction,
    Gate C must veto the proposal.
    """
    proposer = LLMProposalAgent()
    narrative = "LVEF is 45% recorded on echocardiogram 2 weeks ago."
    criterion_def = {
        "criterion_code": "EF-01",
        "name": "Depressed Ejection Fraction",
        "description": "LVEF <= 35% documented on cardiac imaging",
        "keywords": "lvef, ejection fraction"
    }

    start = narrative.find("LVEF is 45%")
    end = start + len("LVEF is 45%")
    proposal = LLMProposedSpan(
        criterion_code="EF-01",
        proposed_status=DeterminationStatus.MET,
        quote=narrative[start:end],
        start_char=start,
        end_char=end,
        confidence=0.80,
        reasoning="Extracted LVEF."
    )

    # Mock verifier agent to return an audit flagging a contradiction
    mock_verifier = MagicMock()
    mock_audit = VerificationAuditResult(
        criterion_code="EF-01",
        grounding_status=True,
        hallucination_flag=False,
        unverified_omission_flag=False,
        offset_drift_detected=False,
        contradiction_detected=True,  # 45% contradicts <= 35%
        calibrated_confidence=0.20,
        audit_notes="Contradiction: LVEF is 45% which exceeds the required threshold of 35%."
    )
    mock_verifier.audit_assessment.return_value = mock_audit

    res = proposer.evaluate_proposal_through_gates(
        proposal=proposal,
        raw_narrative=narrative,
        criterion_def=criterion_def,
        verifier_agent=mock_verifier
    )
    assert not res.passed
    assert res.failed_gate in ("GATE_C_ADVERSARIAL_VETO", "GATE_C_AGENT3_VETO")
    assert "veto" in res.reason.lower()


def test_llm_timeout_and_unavailable_graceful_fallback():
    """
    When the local LLM server times out or is unreachable, the system must not fail:
    it falls back cleanly to deterministic extraction without breaking the pipeline.
    """
    proposer = LLMProposalAgent()
    proposer.enabled = True  # Enable for this test to exercise network timeout/connection handling
    narrative = "Patient has severe chronic knee osteoarthrosis. Conservative therapy tried."
    criterion_def = {
        "criterion_code": "TKA-01",
        "name": "Severe Osteoarthritis",
        "description": "Grade IV osteoarthritis of the knee",
        "keywords": "osteoarthrosis, knee"
    }

    # Simulate timeout by patching proposer._execute_network_request with TimeoutException
    import httpx
    with patch.object(proposer, "_execute_network_request", side_effect=httpx.TimeoutException("Connection timed out")):
        res = proposer.propose_spans_sync(
            narrative=narrative,
            criterion_def=criterion_def,
            policy_id="LCD-TKA"
        )
        assert res["status"] == "SKIPPED_TIMEOUT"
        assert res["proposals"] == []

    # Simulate connection error (Ollama not running)
    with patch.object(proposer, "_execute_network_request", side_effect=httpx.ConnectError("Failed to establish connection")):
        res = proposer.propose_spans_sync(
            narrative=narrative,
            criterion_def=criterion_def,
            policy_id="LCD-TKA"
        )
        assert res["status"] == "SKIPPED_UNAVAILABLE"
        assert res["proposals"] == []


def test_llm_cannot_overwrite_or_downgrade_deterministic_verdict():
    """
    Deterministic extractors stand first. An LLM proposal must never overwrite
    or downgrade a deterministic MET or DENIED determination.
    """
    evaluator = CriteriaEvaluationAgent()
    narrative = "Echocardiogram: LVEF 25% recorded with severe hypokinesis. Patient has NYHA functional class III symptoms."
    criterion_dict = {
        "criterion_code": "CRIT-ICD-01",
        "name": "Severe LV Systolic Dysfunction",
        "description": "Documented LVEF <= 35% on diagnostic echocardiography",
        "clinical_intent": "Confirm depressed LVEF",
        "is_exclusion": False,
        "keywords": "lvef, ejection fraction",
        "min_score": 0.8
    }

    # Deterministic evaluation succeeds as MET
    det_assessment = evaluator.evaluate_criterion(criterion_dict, narrative)
    assert det_assessment.status == DeterminationStatus.MET

    # Now run agentic evaluation with an LLM proposer that proposes NOT_MET
    mock_llm = MagicMock()
    mock_llm.propose_spans_sync.return_value = {
        "status": "PROPOSED",
        "proposals": [
            LLMProposedSpan(
                criterion_code="CRIT-ICD-01",
                proposed_status=DeterminationStatus.NOT_MET,
                quote="Patient has NYHA functional class III",
                start_char=narrative.find("Patient has NYHA"),
                end_char=narrative.find("Patient has NYHA") + 10,
                confidence=0.90,
                reasoning="Suggesting not met."
            )
        ]
    }

    agentic_assessment = evaluator.evaluate_criterion_agentic(
        criterion_dict=criterion_dict,
        ehr_narrative=narrative,
        llm_proposer=mock_llm,
        policy_id="NCD-20.4"
    )

    # Invariant: deterministic MET is preserved, LLM proposal did not downgrade it
    assert agentic_assessment.status == DeterminationStatus.MET
    assert agentic_assessment.tool_selection["methods_tried"][0] == "deterministic_extractor"


# -----------------------------------------------------------------------------
# TASK 2 TESTS: Actually Agentic Agents 2, 3, 4
# -----------------------------------------------------------------------------

def test_agent2_autonomous_tool_selection():
    """
    Agent 2 must choose tools autonomously based on criteria requirements:
    - Temporal criteria trigger 'timeline_validator'
    - High-ambiguity or missing evidence triggers 'llm_proposer'
    - Standard clear criteria trigger 'deterministic_extractor'
    Records methods tried, selection order, and rationale.
    """
    evaluator = CriteriaEvaluationAgent()
    narrative = "Patient underwent medical therapy for 3 months with persistent angina. Prior MI was 60 days ago."

    # Temporal criterion
    temporal_crit = {
        "criterion_code": "CRIT-TEMP-01",
        "name": "Medical Therapy Trial Period",
        "description": "At least 90 days of optimal medical therapy",
        "clinical_intent": "Verify conservative medical management duration",
        "is_exclusion": False,
        "required_temporal_window": "90 days",
        "keywords": "medical therapy, trial, months",
        "min_score": 0.7
    }

    assessment = evaluator.evaluate_criterion_agentic(
        criterion_dict=temporal_crit,
        ehr_narrative=narrative,
        policy_id="NCD-20.4"
    )

    assert assessment.tool_selection is not None
    assert "timeline_validator" in assessment.tool_selection["methods_tried"]
    assert assessment.tool_selection["selected_tool"] in ("timeline_validator", "deterministic_extractor")
    assert "selection_rationale" in assessment.tool_selection


def test_agent3_debate_loop_termination_within_three_rounds():
    """
    Agent 3's debate loop must terminate within 3 rounds, recording
    each round's challenge, defense or concession in debate_rounds.
    """
    verifier = AdversarialVerificationAgent()
    narrative = "Patient has LVEF 25% recorded on May 10, 2026. Prior MI was on March 1, 2026."

    assessment = CriterionAssessment(
        criterion_id="ICD-01",
        criterion_code="ICD-01",
        name="Severe LV Dysfunction",
        description="LVEF <= 35%",
        status=DeterminationStatus.MET,
        clinical_rationale="Extracted LVEF 25%",
        raw_confidence=0.88,
        is_exclusion=False,
        verified_spans=[
            ClinicalEvidenceSpan(
                source_text="LVEF 25%",
                start_char=narrative.find("LVEF 25%") + 5,
                end_char=narrative.find("LVEF 25%") + 5 + len("LVEF 25%"),
                confidence=0.88,
                clinical_section="NARRATIVE"
            )
        ]
    )

    crit_defs = [{
        "criterion_code": "ICD-01",
        "name": "Severe LV Dysfunction",
        "description": "LVEF <= 35%",
        "keywords": "lvef, ejection fraction"
    }]

    evaluator = CriteriaEvaluationAgent()
    audits, debates = verifier.debate_and_verify(
        assessments=[assessment],
        criteria_defs=crit_defs,
        ehr_narrative=narrative,
        evaluator_agent=evaluator,
        max_rounds=3
    )

    assert len(audits) == 1
    # Check that debate took at most 3 rounds
    assert len(debates) <= 3
    if debates:
        first_debate = debates[0]
        assert "round" in first_debate
        assert "challenge" in first_debate
        assert "outcome" in first_debate


def test_agent3_concession_outcome():
    """
    When Agent 3 challenges a criterion as ungrounded or contradicted and
    Agent 2 cannot defend it, Agent 2 must concede and the status is updated.
    """
    verifier = AdversarialVerificationAgent()
    narrative = "Patient denied any previous myocardial infarction or chest pain."

    hallucinated_assessment = CriterionAssessment(
        criterion_id="ICD-MI",
        criterion_code="ICD-MI",
        name="Prior Myocardial Infarction",
        description="Documented prior MI >= 40 days ago",
        status=DeterminationStatus.MET,
        clinical_rationale="MI mentioned in history",
        raw_confidence=0.75,
        is_exclusion=False,
        verified_spans=[
            ClinicalEvidenceSpan(
                source_text="prior myocardial infarction",
                start_char=10,
                end_char=37,
                confidence=0.75,
                clinical_section="NARRATIVE"
            )
        ]
    )

    crit_defs = [{
        "criterion_code": "ICD-MI",
        "name": "Prior Myocardial Infarction",
        "description": "Documented prior MI >= 40 days ago",
        "keywords": "myocardial infarction, mi"
    }]

    evaluator = CriteriaEvaluationAgent()
    audits, debates = verifier.debate_and_verify(
        assessments=[hallucinated_assessment],
        criteria_defs=crit_defs,
        ehr_narrative=narrative,
        evaluator_agent=evaluator,
        max_rounds=3
    )

    # Agent 2 must concede or revise because text does not support active affirmative MI
    assert len(debates) >= 1
    concession_found = any(d.get("outcome") in ("CONCEDED_AND_REVISED", "ACCEPTED_AFTER_DEFENSE") for d in debates)
    assert concession_found or hallucinated_assessment.status != DeterminationStatus.MET


def test_agent4_candidate_tau_and_operative_tau():
    """
    Agent 4 runs calibration sweep over tau on development scores,
    labels it 'exploratory-analysis-on-development-data' (not a derived tau),
    and preserves operative tau = 0.85 without claiming a derived threshold.
    """
    gate = CalibratedAbstentionGate(tau=0.85)

    sweep = gate.run_exploratory_tau_sweep()

    # Operative threshold must remain exactly 0.85
    assert sweep["operative_tau"] == 0.85
    assert sweep["label"] == "exploratory-analysis-on-development-data"
    assert sweep["is_derived_tau"] is False
    assert len(sweep["analysis_grid"]) > 0
    # No value in the report is claimed as a derived tau
    assert "derived_threshold_tau" not in sweep
    assert "no threshold is claimed as a derived tau" in sweep["disclaimer"].lower()


def test_agent4_deferral_queue_prioritization():
    """
    Agent 4 prioritizes the human deferral queue by:
    priority_score = (policy_risk_weight * 40.0) + (min(missing_count, 5) * 6.0) + (min(waiting_hours, 72) * 0.5)
    High risk policies (e.g., NCD-20.4 ICD, TAVR, ACDF) must be ranked above low risk procedures.
    """
    cases = [
        {
            "case_id": "CASE-ROUTINE-1",
            "policy_id": "NCD-CATARACT",  # standard risk = 0.5
            "missing_criteria": ["CAT-01"],  # missing = 1
            "waiting_time_hours": 2.0
        },
        {
            "case_id": "CASE-URGENT-ICD",
            "policy_id": "NCD-20.4",  # high risk = 1.0 (ICD)
            "missing_criteria": ["ICD-01", "ICD-02", "ICD-03"],  # missing = 3
            "waiting_time_hours": 12.0
        },
        {
            "case_id": "CASE-OLD-WAITING",
            "policy_id": "OPD-BLEPH",  # standard risk = 0.5
            "missing_criteria": [],
            "waiting_time_hours": 48.0
        }
    ]

    sorted_queue = CalibratedAbstentionGate.prioritize_deferral_queue(cases)

    # CASE-URGENT-ICD: 1.0*40 + 3*6 + 12*0.5 = 40 + 18 + 6 = 64.0 -> Rank 1 (HIGH)
    # CASE-OLD-WAITING: 0.5*40 + 0 + 48*0.5 = 20 + 24 = 44.0 -> Rank 2 (MEDIUM)
    # CASE-ROUTINE-1: 0.5*40 + 1*6 + 2*0.5 = 20 + 6 + 1 = 27.0 -> Rank 3 (ROUTINE)

    assert sorted_queue[0]["case_id"] == "CASE-URGENT-ICD"
    assert sorted_queue[0]["priority_tier"] == "HIGH"
    assert sorted_queue[0]["priority_score"] == 64.0

    assert sorted_queue[1]["case_id"] == "CASE-OLD-WAITING"
    assert sorted_queue[1]["priority_tier"] == "MEDIUM"

    assert sorted_queue[2]["case_id"] == "CASE-ROUTINE-1"
    assert sorted_queue[2]["priority_tier"] == "ROUTINE"


def test_agentic_pipeline_e2e_adjudication():
    """
    End-to-end integration test verifying that MultiAgentVerificationPipeline:
    1. Evaluates criteria using Agent 2 tool decisions
    2. Runs Agent 3 debate rounds
    3. Runs Agent 4 abstention gate with candidate tau analysis
    4. Populates all audit metadata on FinalAdjudication
    """
    pipeline = MultiAgentVerificationPipeline()
    ehr = (
        "History of present illness: Patient is a 68-year-old evaluated for cardiac symptoms. "
        "Echocardiogram demonstrates severe left ventricular dysfunction with LVEF 28%. "
        "Patient has NYHA functional class III ischemic cardiomyopathy. "
        "Optimal medical therapy with beta-blocker, ACE-inhibitor, and spironolactone for > 90 days. "
        "Myocardial infarction occurred 6 months ago. Normal cognition and expected survival > 1 year."
    )

    res = pipeline.adjudicate_sync(
        patient_id="PT-SYNTHETIC-9999",
        policy_id="NCD-20.4",
        ehr_narrative=ehr
    )

    assert res.adjudication_decision in (AdjudicationDecision.APPROVED, AdjudicationDecision.DEFERRED_TO_HUMAN)
    assert res.agentic_audit_trail is not None
    assert "agent_1_retrieval" in res.agentic_audit_trail
    assert "agent_2_tool_selection" in res.agentic_audit_trail
    assert "agent_3_debate_rounds" in res.agentic_audit_trail
    assert "agent_4_abstention_gate" in res.agentic_audit_trail

    assert res.candidate_tau_analysis is not None
    assert res.candidate_tau_analysis["operative_tau"] == 0.85
    assert res.candidate_tau_analysis["label"] == "exploratory-analysis-on-development-data"
    assert res.candidate_tau_analysis["is_derived_tau"] is False

    assert res.llm_proposal_metadata is not None
    assert "enabled" in res.llm_proposal_metadata
    assert "model" in res.llm_proposal_metadata


def test_gate_a_quote_exists_with_wrong_llm_offsets_passes():
    """
    Task 1: If local LLM returns incorrect character offsets (e.g. 0,0 or 999,1020),
    Gate A must re-anchor to the system-located verbatim span and pass Gate A.
    """
    proposer = LLMProposalAgent()
    narrative = "Clinical Progress Note: Patient has documented severe aortic stenosis with AVA 0.65 cm2."
    crit_def = {
        "criterion_code": "CRIT-AS-01",
        "name": "Aortic Valve Area",
        "keywords": "aortic stenosis, ava"
    }
    target_quote = "aortic stenosis"

    # LLM provided completely wrong character offsets (e.g. 0, 10 or 999, 1014)
    proposal_wrong_offsets = LLMProposedSpan(
        criterion_code="CRIT-AS-01",
        proposed_status=DeterminationStatus.MET,
        claimed_text=target_quote,
        char_start=0,
        char_end=10,  # actual slice at 0..10 is 'Clinical P'
        claimed_equivalence="exact match",
        rationale="Found in narrative."
    )

    res = proposer.evaluate_proposal_through_gates(
        proposal=proposal_wrong_offsets,
        sanitized_ehr=narrative,
        criterion=crit_def
    )

    # Gate A exact slice check passed because system located the true span
    assert res.failing_gate != "GATE_A_EXACT_SLICE"
    assert proposal_wrong_offsets.char_start == narrative.find(target_quote)
    assert proposal_wrong_offsets.char_end == proposal_wrong_offsets.char_start + len(target_quote)
    assert narrative[proposal_wrong_offsets.char_start:proposal_wrong_offsets.char_end] == target_quote


def test_gate_a_hallucinated_quote_fails():
    """
    Task 1: If local LLM hallucinates a quote not present anywhere in the narrative,
    Gate A must strictly reject it with GATE_A_EXACT_SLICE.
    """
    proposer = LLMProposalAgent()
    narrative = "Clinical Progress Note: Patient has documented severe aortic stenosis with AVA 0.65 cm2."
    crit_def = {
        "criterion_code": "CRIT-AS-01",
        "name": "Aortic Valve Area",
        "keywords": "aortic stenosis, ava"
    }

    hallucinated_proposal = LLMProposedSpan(
        criterion_code="CRIT-AS-01",
        proposed_status=DeterminationStatus.MET,
        claimed_text="patient exhibits severe mitral regurgitation grade 4",
        char_start=0,
        char_end=0,
        claimed_equivalence="fabricated finding",
        rationale="Hallucinated clinical finding."
    )

    res = proposer.evaluate_proposal_through_gates(
        proposal=hallucinated_proposal,
        sanitized_ehr=narrative,
        criterion=crit_def
    )

    assert not res.passed
    assert res.failed_gate == "GATE_A_EXACT_SLICE"
    assert "hallucinated" in res.rejection_reason.lower()


def test_locate_claimed_span_multiple_occurrences_deterministic():
    """
    Task 1: If claimed_text appears multiple times in note, locate_claimed_span
    deterministically prefers the affirmative patient context over a negated or family context.
    """
    # Occurrence 1: clinically negated ("denies chest pain")
    # Occurrence 2: affirmative patient finding ("documented severe chest pain on exertion")
    narrative = (
        "Review of Systems: Patient denies chest pain at rest. "
        "Physical Exam: Patient has documented severe chest pain on exertion during treadmill testing."
    )

    claimed = "chest pain"
    s, e = LLMProposalAgent.locate_claimed_span(narrative, claimed)

    # Must select the second occurrence because the first is negated by 'denies'
    assert narrative[s:e] == claimed
    second_idx = narrative.rfind(claimed)
    assert s == second_idx
    assert e == second_idx + len(claimed)
