"""
Trace Service for CarePolicyGuard (Prompt v80 Task 1).

Extracts and structures the reviewer-facing criterion agent trace from persisted
adjudication records (FinalAdjudication, message board transcripts, adversarial audits,
and criterion assessments).

Distinguishes:
1. Evaluator's proposed evidence (quoted span, coordinates, Gate A verbatim check).
2. Verifier's action on that proposal (upheld, challenged, or rejected, with counter-quote,
   Gate C concept-scope result, or judge-in-the-loop verdict).
3. How the objection was resolved (defended with defense quote, conceded, or promoted via advocacy,
   leading to the final criterion outcome).
"""

from __future__ import annotations

from typing import Any


def build_criterion_agent_trace(
    adjudication_data: dict[str, Any],
    sanitized_ehr: str = ""
) -> list[dict[str, Any]]:
    """
    Constructs a structured, per-criterion reviewer-facing trace list from adjudication data.
    """
    trace_list: list[dict[str, Any]] = []

    criteria = adjudication_data.get("criterion_assessments") or []
    audits = adjudication_data.get("verification_audits") or []
    board_messages = adjudication_data.get("message_board") or []
    debated_outcomes = adjudication_data.get("debated_criteria_outcomes") or {}
    tool_attribution = adjudication_data.get("tool_attribution") or {}

    # Index audits by criterion_code
    audit_map: dict[str, dict[str, Any]] = {}
    for a in audits:
        if isinstance(a, dict):
            ccode = a.get("criterion_code")
            if ccode:
                audit_map[ccode] = a
        elif hasattr(a, "criterion_code"):
            audit_map[a.criterion_code] = a.__dict__

    # Index board messages by criterion_code
    board_by_crit: dict[str, list[dict[str, Any]]] = {}
    for m in board_messages:
        cc = m.get("criterion_code") if isinstance(m, dict) else getattr(m, "criterion_code", None)
        if cc:
            board_by_crit.setdefault(cc, []).append(m if isinstance(m, dict) else m.__dict__)

    ehr_text = sanitized_ehr or adjudication_data.get("sanitized_ehr_text") or ""

    for c in criteria:
        if isinstance(c, dict):
            ccode = c.get("criterion_code") or c.get("id") or "CRIT-UNKNOWN"
            cname = c.get("name") or c.get("criterion_name") or ccode
            cdesc = c.get("description") or ""
            cstatus = c.get("status") or "INSUFFICIENT_EVIDENCE"
            cquote = c.get("extracted_evidence_quote") or ""
            coords = c.get("evidence_span_coordinates") or []
            rationale = c.get("clinical_rationale") or ""
        else:
            ccode = getattr(c, "criterion_code", "CRIT-UNKNOWN")
            cname = getattr(c, "name", ccode)
            cdesc = getattr(c, "description", "")
            cstatus = getattr(c, "status", "INSUFFICIENT_EVIDENCE")
            cquote = getattr(c, "extracted_evidence_quote", "")
            coords = getattr(c, "evidence_span_coordinates", [])
            rationale = getattr(c, "clinical_rationale", "")

        audit = audit_map.get(ccode, {})
        crit_board = board_by_crit.get(ccode, [])

        # 1. EVALUATOR PROPOSAL (Agent 1)
        has_quote = bool(cquote and cquote.strip())
        gate_a_passed = bool(has_quote and ehr_text and cquote.strip() in ehr_text)
        evaluator_proposal = {
            "proposed_evidence_quote": cquote if has_quote else "No supporting evidence documented in EHR narrative.",
            "span_coordinates": coords if coords else [],
            "gate_a_verbatim_grounded": gate_a_passed,
            "gate_a_status": "PASSED" if gate_a_passed else ("FAILED_NO_QUOTE" if not has_quote else "FAILED_NOT_GROUNDED"),
            "clinical_intent": cdesc,
            "evaluator_rationale": rationale or ("Extracted candidate evidence for criterion satisfaction." if has_quote else "No clinical evidence matching requirement found in chart."),
        }

        # 2. VERIFIER FINDING (Agent 2)
        has_contra = bool(audit.get("has_contradiction") or audit.get("has_objection"))
        obj_type = audit.get("objection_type") or "NONE"
        counter_quote = audit.get("counter_evidence_quote") or audit.get("counter_quote") or ""
        spec_contra = bool(audit.get("specific_contradiction"))

        # Look for challenge or objection messages on board
        challenge_msgs = [m for m in crit_board if m.get("message_type") in ("CHALLENGE", "OBJECTION", "VETO")]
        if challenge_msgs:
            first_chal = challenge_msgs[0]
            if not obj_type or obj_type == "NONE":
                obj_type = first_chal.get("metadata", {}).get("objection_type") or "CLINICAL_DISAGREEMENT"
            if not counter_quote:
                counter_quote = first_chal.get("evidence") or first_chal.get("metadata", {}).get("counter_quote") or ""
            has_contra = True

        # Gate C concept scope evaluation
        gate_c_passed = True
        gate_c_detail = "Concept scope aligns with Medicare statutory coverage terms."
        if "provisional" in rationale.lower() or any("provisional" in str(m.get("content", "")).lower() for m in crit_board):
            gate_c_detail = "Provisional clinical equivalence established via semantic reasoning."
        elif "Gate C" in rationale or any("Gate C" in str(m.get("content", "")).lower() for m in crit_board):
            gate_c_passed = False
            gate_c_detail = "Concept scope rejected by Gate C (disjoint concept or excluded clinical domain)."

        # Judge-in-the-loop evaluation
        judge_verdict = "SKIPPED"
        judge_rationale = "Not required for deterministic statutory check."
        judge_posts = [m for m in crit_board if "judge" in str(m.get("content", "")).lower() or m.get("metadata", {}).get("judge_action")]
        if judge_posts:
            jp = judge_posts[0]
            judge_verdict = "EQUIVALENT" if "equivalent" in str(jp.get("content", "")).lower() else "REVIEWED"
            judge_rationale = jp.get("content") or "Evaluated by local LLM clinical equivalence judge."

        verifier_finding = {
            "action": "CHALLENGED" if has_contra else ("UPHELD" if cstatus == "MET" else "INSUFFICIENT"),
            "has_objection": has_contra,
            "objection_type": obj_type,
            "counter_evidence_quote": counter_quote,
            "specific_contradiction": spec_contra,
            "gate_c_concept_scope": "PASSED" if gate_c_passed else "REJECTED",
            "gate_c_detail": gate_c_detail,
            "judge_in_loop_verdict": judge_verdict,
            "judge_rationale": judge_rationale,
            "verifier_summary": (
                f"Raised {obj_type} objection: '{counter_quote}'" if (has_contra and counter_quote)
                else (f"Raised {obj_type} objection." if has_contra else "No contradictory clinical findings identified.")
            )
        }

        # 3. RESOLUTION & OUTCOME
        defense_msgs = [m for m in crit_board if m.get("message_type") == "DEFENSE"]
        concede_msgs = [m for m in crit_board if m.get("message_type") == "CONCEDE"]

        outcome = debated_outcomes.get(ccode)
        defense_quote = ""
        resolution_type = "UNCONTESTED"

        if defense_msgs:
            last_def = defense_msgs[-1]
            defense_quote = last_def.get("evidence") or last_def.get("metadata", {}).get("quote") or last_def.get("metadata", {}).get("defense_quote") or ""
            if last_def.get("metadata", {}).get("advocacy_promoted"):
                resolution_type = "ADVOCACY_PROMOTED"
                outcome = "PROMOTED"
            else:
                resolution_type = "DEFENDED_HOLD"
                outcome = outcome or "DEFENDED"
        elif concede_msgs:
            resolution_type = "CONCEDED"
            outcome = "CONCEDED"
        elif tool_attribution.get(ccode) == "advocate_for":
            resolution_type = "ADVOCACY_PROMOTED"
            outcome = "PROMOTED"
        elif cstatus == "MET":
            resolution_type = "DETERMINISTIC_PASS"
            outcome = "SATISFIED"
        else:
            resolution_type = "UNFULFILLED"
            outcome = "INSUFFICIENT"

        resolution = {
            "resolution_type": resolution_type,
            "debated_outcome": outcome or resolution_type,
            "defense_quote": defense_quote,
            "final_status": cstatus,
            "is_met": (cstatus == "MET"),
            "resolution_summary": (
                f"Successfully defended using clinical evidence '{defense_quote}'." if defense_quote
                else (f"Conceded after verified contradiction: criterion marked {cstatus}." if resolution_type == "CONCEDED"
                      else f"Criterion outcome determined as {cstatus}.")
            )
        }

        trace_list.append({
            "criterion_code": ccode,
            "name": cname,
            "description": cdesc,
            "final_status": cstatus,
            "evaluator_proposal": evaluator_proposal,
            "verifier_finding": verifier_finding,
            "resolution": resolution,
        })

    return trace_list
