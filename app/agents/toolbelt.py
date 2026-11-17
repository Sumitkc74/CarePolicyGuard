"""
CarePolicyGuard Agent Toolbelt and Instrumentation (Task 1 & Task 7).

Wraps core adjudication tools with typed inputs, typed outputs, structured failure handling,
and auditable execution logging:
1. deterministic_check: DeclarativePolicyEngine.evaluate
2. concept_map_lookup: get_concept_map() with 35 committed (deciding) and 119 draft (advisory) concepts
3. retrieve_policies: PolicyShortlistService unified scorer + coverage reranking
4. judge_criterion: ClinicalEquivalenceJudge.judge_criterion_sync (gated by Gates A/B/C)
5. challenge_judgment: ClinicalEquivalenceJudge.generate_adversarial_counter_reading_sync
6. advocate_for: ClinicalEquivalenceJudge.generate_advocacy_sync
7. search_spans: CandidateSpanExtractor + judge_equivalence_sync (capped at 1 per criterion)
8. defer: Agent 4 calibrated deferral action for genuine clinical ambiguity
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.concept_map import ConceptMap, get_concept_map
from app.schemas.contracts import (
    ClinicalEvidenceSpan,
    CriterionAssessment,
    DeterminationStatus,
)

logger = logging.getLogger(__name__)


class ToolExecutionRecord(BaseModel):
    """Auditable log of a single agent tool execution (Task 7)."""
    agent: str = Field(..., description="Agent that initiated the tool call")
    tool: str = Field(..., description="Name of the tool invoked")
    criterion_code: str | None = Field(default=None, description="Criterion code if tool operated on a criterion")
    clinical_rationale: str = Field(..., description="Clinical justification for invoking this tool")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Structured tool inputs")
    result: dict[str, Any] = Field(default_factory=dict, description="Structured tool outputs")
    what_changed: str = Field(..., description="Change in agent internal state or adjudication outcome")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float = Field(default=0.0, description="Tool execution wall-clock time in milliseconds")


class MindChangeRecord(BaseModel):
    """Recorded agent position shift / concession during two-sided debate (Task 3)."""
    agent: str = Field(..., description="Agent that changed its position")
    criterion: str = Field(..., description="Policy criterion code")
    from_status: str = Field(..., description="Previous determination status")
    to_status: str = Field(..., description="Updated determination status")
    reason: str = Field(..., description="Clinical or evidentiary reason for concession/change")
    evidence_span: str | None = Field(default=None, description="Direct quote from narrative involved in change")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AgentToolbelt:
    """
    Centralized Agent Toolbelt wrapping all clinical verification tools.
    Provides uniform execution logging, latency instrumentation, and per-criterion attribution.
    """

    def __init__(self, db: Any | None = None, concept_map: ConceptMap | None = None):
        self.db = db
        self.concept_map = concept_map or get_concept_map()
        self.execution_logs: list[ToolExecutionRecord] = []
        self.tool_attribution: dict[str, str] = {}
        self.judge_routing: dict[str, str] = {}
        self.mind_changes: list[MindChangeRecord] = []

    def _log_execution(
        self,
        agent: str,
        tool: str,
        criterion_code: str | None,
        clinical_rationale: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
        what_changed: str,
        duration_ms: float,
    ) -> ToolExecutionRecord:
        record = ToolExecutionRecord(
            agent=agent,
            tool=tool,
            criterion_code=criterion_code,
            clinical_rationale=clinical_rationale,
            inputs=inputs,
            result=result,
            what_changed=what_changed,
            duration_ms=round(duration_ms, 2),
        )
        self.execution_logs.append(record)
        return record

    def record_mind_change(
        self,
        agent: str,
        criterion: str,
        from_status: str,
        to_status: str,
        reason: str,
        evidence_span: str | None = None,
    ) -> MindChangeRecord:
        """Records a concession or status change during two-sided debate (Task 3)."""
        change = MindChangeRecord(
            agent=agent,
            criterion=criterion,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            evidence_span=evidence_span,
        )
        self.mind_changes.append(change)
        return change

    # -------------------------------------------------------------------------
    # Tool 1: deterministic_check
    # -------------------------------------------------------------------------
    def deterministic_check(
        self,
        agent: str,
        criterion: dict[str, Any] | Any,
        note: str,
        policy: Any | None = None,
        rationale: str = "Evaluate criterion against note using deterministic regex and negation patterns",
    ) -> CriterionAssessment:
        """
        Tool 1: Evaluates a policy criterion deterministically via DeclarativePolicyEngine.
        """
        t0 = time.perf_counter()
        from app.services.declarative_engine import DeclarativePolicyEngine

        ccode = getattr(criterion, "criterion_code", None) or criterion.get("criterion_code", "UNKNOWN")
        decl_crit = DeclarativePolicyEngine.compile_from_dict(criterion) if isinstance(criterion, dict) else criterion
        assessment = DeclarativePolicyEngine.evaluate(decl_crit, note)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        what_changed = f"Preliminary assessment: {assessment.status.value} (conf={assessment.raw_confidence:.2f})"
        if assessment.status in (DeterminationStatus.MET, DeterminationStatus.NOT_MET):
            self.tool_attribution[ccode] = "deterministic_check"

        self._log_execution(
            agent=agent,
            tool="deterministic_check",
            criterion_code=ccode,
            clinical_rationale=rationale,
            inputs={"criterion_code": ccode, "is_exclusion": getattr(decl_crit, "is_exclusion", False)},
            result={
                "status": assessment.status.value,
                "raw_confidence": assessment.raw_confidence,
                "verified_spans_count": len(assessment.verified_spans),
                "clinical_rationale": assessment.clinical_rationale,
            },
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return assessment

    # -------------------------------------------------------------------------
    # Tool 2: concept_map_lookup
    # -------------------------------------------------------------------------
    def concept_map_lookup(
        self,
        agent: str,
        term: str,
        criterion_term: str | None = None,
        rationale: str = "Lookup term in concept map and check equivalence against governing criterion",
    ) -> dict[str, Any]:
        """
        Tool 2: Queries ConceptMap.
        Committed concepts (35 mappings) are deciding;
        Draft concepts (119 mappings) are advisory only.
        """
        t0 = time.perf_counter()
        cdef = self.concept_map.lookup_concept(term)
        is_deciding = False
        status = "UNMAPPED"
        concept_id = None
        canonical_name = None

        if cdef:
            concept_id = cdef.concept_id
            canonical_name = cdef.canonical_name
            # Check if source is human accepted or committed
            if "draft" in cdef.source_reason.lower() or "unified draft" in cdef.source_reason.lower():
                is_deciding = False
                status = "ADVISORY_DRAFT"
            else:
                is_deciding = True
                status = "DECIDING_COMMITTED"

        equivalence_confirmed = False
        equiv_reason = "No criterion term provided"
        if criterion_term:
            is_eq, eq_r = self.concept_map.verify_equivalence(criterion_term, term)
            equivalence_confirmed = is_eq
            equiv_reason = eq_r

        duration_ms = (time.perf_counter() - t0) * 1000.0
        result = {
            "term": term,
            "concept_id": concept_id,
            "canonical_name": canonical_name,
            "is_deciding": is_deciding,
            "status": status,
            "equivalence_confirmed": equivalence_confirmed,
            "equivalence_reason": equiv_reason,
        }
        what_changed = f"Concept lookup '{term}': {status} (deciding={is_deciding}, equiv={equivalence_confirmed})"

        self._log_execution(
            agent=agent,
            tool="concept_map_lookup",
            criterion_code=None,
            clinical_rationale=rationale,
            inputs={"term": term, "criterion_term": criterion_term},
            result=result,
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return result

    # -------------------------------------------------------------------------
    # Tool 3: retrieve_policies
    # -------------------------------------------------------------------------
    def retrieve_policies(
        self,
        agent: str,
        narrative: str,
        top_k: int = 5,
        rationale: str = "Retrieve and rank governing Medicare policies via unified hybrid scorer",
    ) -> dict[str, Any]:
        """
        Tool 3: Runs unified candidate scoring, criteria-coverage reranking, and margin evaluation.
        """
        t0 = time.perf_counter()
        from app.services.policy_shortlist_service import PolicyShortlistService

        res = PolicyShortlistService.compute_shortlist(narrative, db=self.db, top_k=top_k)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        shortlist = res.get("shortlist", [])
        top_pid = res.get("preselected_policy_id") or (shortlist[0]["policy_id"] if shortlist else None)
        margin = res.get("score_margin")
        status = res.get("status")

        what_changed = f"Policy retrieval: status={status}, top_policy={top_pid}, margin={margin}"

        self._log_execution(
            agent=agent,
            tool="retrieve_policies",
            criterion_code=None,
            clinical_rationale=rationale,
            inputs={"top_k": top_k, "narrative_len": len(narrative)},
            result={
                "status": status,
                "preselected_policy_id": top_pid,
                "score_margin": margin,
                "candidates_count": len(shortlist),
                "margin_threshold": res.get("margin_threshold"),
            },
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return res

    # -------------------------------------------------------------------------
    # Tool 4: judge_criterion
    # -------------------------------------------------------------------------
    def judge_criterion(
        self,
        agent: str,
        criterion: dict[str, Any],
        note: str,
        judge: Any,
        concept_map: ConceptMap | None = None,
        rationale: str = "Query local LLM judge for clinical equivalence on ambiguous criterion",
    ) -> dict[str, Any]:
        """
        Tool 4: Invokes ClinicalEquivalenceJudge.judge_criterion_sync.
        Validates quotes through Gate A (exact slice), Gate B (semantic scope), and Gate C (ConceptMap).
        """
        t0 = time.perf_counter()
        from app.agents.llm_proposer import LLMProposalAgent
        from app.core.agentic_guardrails import AgenticGuardrails

        ccode = criterion.get("criterion_code", "UNKNOWN")
        cmap = concept_map or self.concept_map

        crit_judgment = judge.judge_criterion_sync(
            criterion=criterion,
            note_text=note,
        )

        quoted_evidence = (crit_judgment.quoted_evidence or "").strip()
        gate_res = {"passed": False, "failing_gate": "NONE", "reason": "No quoted evidence"}
        evidence_span: ClinicalEvidenceSpan | None = None

        if crit_judgment.status == "MET" and quoted_evidence:
            s, e = LLMProposalAgent.locate_claimed_span(note, quoted_evidence, allow_repair=True)
            if s == -1 or e == -1:
                gate_res = {
                    "passed": False,
                    "failing_gate": "GATE_A_EXACT_SLICE",
                    "reason": f"Quoted evidence '{quoted_evidence[:60]}...' not found in note",
                }
            else:
                evidence_span = ClinicalEvidenceSpan(
                    source_text=note[s:e],
                    start_char=s,
                    end_char=e,
                    confidence=crit_judgment.confidence or 0.95,
                )
                gate_res = AgenticGuardrails.evaluate_gate_chain(
                    candidate_span=evidence_span,
                    criterion=criterion,
                    ehr_narrative=note,
                    concept_map=cmap,
                    policy_domain=criterion.get("category") or criterion.get("domain"),
                    policy_id=criterion.get("policy_id"),
                )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        passed = gate_res.get("passed", False)
        final_status = "MET" if (crit_judgment.status == "MET" and passed) else crit_judgment.status

        what_changed = (
            f"Judge criterion {ccode}: status={crit_judgment.status}, gate_passed={passed} "
            f"-> final={final_status}"
        )
        if passed:
            self.tool_attribution[ccode] = "judge_criterion"

        result = {
            "status": final_status,
            "raw_judge_status": crit_judgment.status,
            "confidence": crit_judgment.confidence,
            "rationale": crit_judgment.rationale,
            "quoted_evidence": quoted_evidence,
            "gate_result": gate_res,
            "evidence_span": evidence_span.model_dump() if evidence_span else None,
            "status_code": getattr(crit_judgment, "status_code", "COMPLETED"),
        }

        self._log_execution(
            agent=agent,
            tool="judge_criterion",
            criterion_code=ccode,
            clinical_rationale=rationale,
            inputs={"criterion_code": ccode},
            result=result,
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return result

    # -------------------------------------------------------------------------
    # Tool 5: challenge_judgment
    # -------------------------------------------------------------------------
    def challenge_judgment(
        self,
        agent: str,
        criterion: dict[str, Any],
        note: str,
        proposed_evidence: str,
        judge: Any,
        rationale: str = "Generate adversarial counter-reading against proposed evidence (Agent 3 challenge)",
    ) -> dict[str, Any]:
        """
        Tool 5: Generates an adversarial counter-reading arguing against criterion satisfaction.
        """
        t0 = time.perf_counter()
        ccode = criterion.get("criterion_code", "UNKNOWN")

        adv_challenge = judge.generate_adversarial_counter_reading_sync(
            criterion=criterion,
            proposed_evidence=proposed_evidence,
            note_text=note,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0

        has_objection = adv_challenge.get("has_objection", False)
        obj_type = adv_challenge.get("objection_type", "NONE")
        what_changed = f"Adversarial counter-reading on {ccode}: objection={has_objection} ({obj_type})"

        self._log_execution(
            agent=agent,
            tool="challenge_judgment",
            criterion_code=ccode,
            clinical_rationale=rationale,
            inputs={"criterion_code": ccode, "proposed_evidence": proposed_evidence[:80]},
            result=adv_challenge,
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return adv_challenge

    # -------------------------------------------------------------------------
    # Tool 6: advocate_for
    # -------------------------------------------------------------------------
    def advocate_for(
        self,
        agent: str,
        criterion: dict[str, Any],
        note: str,
        judge: Any,
        concept_map: ConceptMap | None = None,
        rationale: str = "Advocate for criterion satisfaction when otherwise failing (Agent 3 advocacy)",
    ) -> dict[str, Any]:
        """
        Tool 6: Generates advocacy arguing FOR satisfaction of an otherwise-failing criterion.
        """
        t0 = time.perf_counter()
        from app.agents.llm_proposer import LLMProposalAgent
        from app.core.agentic_guardrails import AgenticGuardrails

        ccode = criterion.get("criterion_code", "UNKNOWN")
        cmap = concept_map or self.concept_map

        adv_res = judge.generate_advocacy_sync(
            criterion=criterion,
            note_text=note,
        )
        adv_quote = (adv_res.advocacy_quote or "").strip()
        gate_res = {"passed": False, "failing_gate": "NONE", "reason": "No advocacy quote"}
        evidence_span: ClinicalEvidenceSpan | None = None

        if adv_quote:
            s, e = LLMProposalAgent.locate_claimed_span(note, adv_quote, allow_repair=True)
            if s == -1 or e == -1:
                gate_res = {
                    "passed": False,
                    "failing_gate": "GATE_A_EXACT_SLICE",
                    "reason": f"Advocacy quote '{adv_quote[:60]}...' not found in note",
                }
            else:
                evidence_span = ClinicalEvidenceSpan(
                    source_text=note[s:e],
                    start_char=s,
                    end_char=e,
                    confidence=0.92,
                )
                gate_res = AgenticGuardrails.evaluate_gate_chain(
                    candidate_span=evidence_span,
                    criterion=criterion,
                    ehr_narrative=note,
                    concept_map=cmap,
                    policy_domain=criterion.get("category") or criterion.get("domain"),
                    policy_id=criterion.get("policy_id"),
                )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        passed = gate_res.get("passed", False)
        what_changed = f"Advocacy for {ccode}: quote_found={bool(adv_quote)}, gate_passed={passed}"

        if passed:
            self.tool_attribution[ccode] = "advocate_for"

        result = {
            "passed": passed,
            "advocacy_quote": adv_quote,
            "rationale": adv_res.rationale,
            "gate_result": gate_res,
            "evidence_span": evidence_span.model_dump() if evidence_span else None,
            "status_code": getattr(adv_res, "status_code", "COMPLETED"),
        }

        self._log_execution(
            agent=agent,
            tool="advocate_for",
            criterion_code=ccode,
            clinical_rationale=rationale,
            inputs={"criterion_code": ccode},
            result=result,
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return result

    # -------------------------------------------------------------------------
    # Tool 7: search_spans
    # -------------------------------------------------------------------------
    def search_spans(
        self,
        agent: str,
        criterion: dict[str, Any],
        note: str,
        judge: Any,
        concept_map: ConceptMap | None = None,
        max_spans: int = 1,
        rationale: str = "Extract candidate spans and verify equivalence (capped fallback)",
    ) -> list[dict[str, Any]]:
        """
        Tool 7: CandidateSpanExtractor + judge_equivalence_sync (capped at 1 per criterion).
        """
        t0 = time.perf_counter()
        from app.core.agentic_guardrails import AgenticGuardrails
        from app.core.candidate_span_extractor import CandidateSpanExtractor
        from app.core.llm_judge import EquivalenceVerdict

        ccode = criterion.get("criterion_code", "UNKNOWN")
        cmap = concept_map or self.concept_map

        cands = CandidateSpanExtractor.extract_candidates(
            ehr_narrative=note,
            criterion=criterion,
            max_candidates=max_spans,
        )

        results = []
        for cand in cands[:max_spans]:
            judge_res = judge.judge_equivalence_sync(
                criterion=criterion,
                candidate_span_text=cand.source_text,
            )
            passed = False
            gate_res = {"passed": False, "failing_gate": "NONE", "reason": "Not equivalent"}

            if judge_res.verdict == EquivalenceVerdict.EQUIVALENT:
                ev_span = cand.to_evidence_span(confidence=0.95)
                gate_res = AgenticGuardrails.evaluate_gate_chain(
                    candidate_span=ev_span,
                    criterion=criterion,
                    ehr_narrative=note,
                    concept_map=cmap,
                    policy_domain=criterion.get("category") or criterion.get("domain"),
                    policy_id=criterion.get("policy_id"),
                )
                passed = gate_res.get("passed", False)
                if passed:
                    self.tool_attribution[ccode] = "search_spans"

            results.append({
                "candidate_span": cand.source_text,
                "start_char": cand.start_char,
                "end_char": cand.end_char,
                "verdict": judge_res.verdict.value,
                "rationale": judge_res.rationale,
                "gate_passed": passed,
                "gate_result": gate_res,
            })

        duration_ms = (time.perf_counter() - t0) * 1000.0
        what_changed = f"Search spans on {ccode}: tested {len(results)} spans, passed={any(r['gate_passed'] for r in results)}"

        self._log_execution(
            agent=agent,
            tool="search_spans",
            criterion_code=ccode,
            clinical_rationale=rationale,
            inputs={"criterion_code": ccode, "max_spans": max_spans},
            result={"spans_evaluated": len(results), "evaluations": results},
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return results

    # -------------------------------------------------------------------------
    # Tool 8: defer
    # -------------------------------------------------------------------------
    def defer(
        self,
        agent: str,
        criterion_code: str,
        reason: str,
        rationale: str = "Agent 4 deferral decision for genuine clinical ambiguity",
    ) -> dict[str, Any]:
        """
        Tool 8: Explicit deferral decision owned by Agent 4.
        """
        t0 = time.perf_counter()
        duration_ms = (time.perf_counter() - t0) * 1000.0

        self.tool_attribution[criterion_code] = "defer"
        what_changed = f"Agent 4 explicit deferral on {criterion_code}: {reason}"

        result = {
            "criterion_code": criterion_code,
            "decision": "DEFERRED_TO_HUMAN",
            "deferral_reason": reason,
        }

        self._log_execution(
            agent=agent,
            tool="defer",
            criterion_code=criterion_code,
            clinical_rationale=rationale,
            inputs={"criterion_code": criterion_code, "reason": reason},
            result=result,
            what_changed=what_changed,
            duration_ms=duration_ms,
        )
        return result
