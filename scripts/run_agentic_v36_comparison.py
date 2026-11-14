"""
Clean comparison between Arm A (declarative pipeline path with committed map)
and Arm B (agentic message-board mode with merged map in-memory).

Measures live over the 84 author-written development vignettes:
- Arm A: Committed ConceptMap (12 concepts), execution_mode="declarative", LLM proposer enabled (qwen2.5:3b, 3 calls / 30s budget).
- Arm B: Merged ConceptMap (12 committed + 119 PASS drafts = 131 concepts), execution_mode="agentic", local LLM judge (qwen2.5:3b, 3 calls / 30s budget).

Outputs saved to app/data/benchmarks/agentic_v36_comparison_raw.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.core.concept_map as cm_mod
from app.agents.llm_proposer import LLMProposalAgent
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.concept_map import ConceptDefinition, ConceptMap, ConceptSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agentic_v36_comparison")

SYNONYMY_VIGNETTE_IDS = [
    "DEV-LCD-IMRT-APP",
    "DEV-LCD-KNEE-ORTHOSIS-APP",
    "DEV-LCD-KYPHO-APP",
    "DEV-LCD-LUMBAR-DECOMP-APP",
    "DEV-LCD-MRI-BRAIN-APP",
    "DEV-LCD-MRI-LUMBAR-APP",
    "DEV-LCD-PAD-ATHERO-APP",
    "DEV-LCD-POWER-WC-APP",
    "DEV-LCD-PROTON-APP",
    "DEV-LCD-RAD-NIV-APP",
    "DEV-LCD-SBRT-APP",
    "DEV-NCD-CARDIAC-REHAB-APP",
    "DEV-NCD-CCTA-APP",
    "DEV-NCD-MPI-PET-APP",
    "DEV-NCD-PACEMAKER-APP",
    "DEV-NCD-PET-ONC-APP",
    "DEV-NCD-PUMP-APP",
    "DEV-NCD-SGD-APP",
    "DEV-OPD-SI-FUSION-APP",
]


def build_merged_in_memory_map() -> tuple[ConceptMap, int, int]:
    """Builds the in-memory merged concept map: 12 committed + 119 PASS draft concepts."""
    merged_map = ConceptMap()
    committed_count = merged_map.total_concepts

    draft_file = ROOT_DIR / "app" / "data" / "concept_map" / "draft_concept_entries.json"
    added_drafts = 0
    if draft_file.exists():
        with open(draft_file, "r", encoding="utf-8") as f:
            drafts = json.load(f)
        for d in drafts:
            if d.get("governing_rule_check") == "PASS_EQUIVALENCE":
                cdef = ConceptDefinition(
                    concept_id=d["concept_id"],
                    canonical_name=d["canonical_name"],
                    domain=d["domain"],
                    accepted_terms=d["accepted_terms"],
                    prohibited_near_misses=d.get("prohibited_near_misses", []),
                    source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
                    source_reason=f"Unified draft: {d.get('governing_rule_rationale', '')}"
                )
                merged_map.register_concept(cdef)
                added_drafts += 1

    logger.info(
        f"Merged ConceptMap assembled: {committed_count} committed + {added_drafts} drafts = "
        f"{merged_map.total_concepts} total concepts."
    )
    return merged_map, committed_count, added_drafts


def run_arm_a(vignettes: list[dict[str, Any]], span_repair_enabled: bool = True) -> dict[str, Any]:
    """Runs Arm A: existing pipeline path (declarative mode) with committed map (12 concepts)."""
    logger.info(
        f"Starting Arm A: Existing Pipeline Path (Declarative, Committed Map 12 concepts, "
        f"span_repair={span_repair_enabled})..."
    )

    # Ensure clean committed map and configured span repair
    cm_mod._GLOBAL_CONCEPT_MAP = ConceptMap()
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0
    pipeline.llm_proposer.span_repair_enabled = span_repair_enabled

    cases = []
    concordant_count = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    resolved_synonymy = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        telem_before = dict(pipeline.llm_proposer.telemetry)

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-ARM-A-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False,
        )
        act_dec = res.adjudication_decision.value
        is_concordant = (act_dec == exp_dec)

        telem_after = dict(pipeline.llm_proposer.telemetry)
        c_calls = telem_after.get("total_calls", 0) - telem_before.get("total_calls", 0)
        c_ga = telem_after.get("gate_a_rejections", 0) - telem_before.get("gate_a_rejections", 0)
        c_gb = telem_after.get("gate_b_rejections", 0) - telem_before.get("gate_b_rejections", 0)
        c_gcm = telem_after.get("gate_c_map_rejections", 0) - telem_before.get("gate_c_map_rejections", 0)
        c_gcv = telem_after.get("gate_c_vetoes", 0) - telem_before.get("gate_c_vetoes", 0)
        c_acc = telem_after.get("proposals_accepted", 0) - telem_before.get("proposals_accepted", 0)

        if is_concordant:
            concordant_count += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                resolved_synonymy.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

        # Collect accepted claims
        accepted_claims = []
        for ca in res.criterion_assessments:
            if ca.status.value == "MET" and ca.verified_spans:
                for sp in ca.verified_spans:
                    accepted_claims.append({
                        "criterion_code": ca.criterion_code,
                        "source_text": sp.source_text,
                        "start_char": sp.start_char,
                        "end_char": sp.end_char,
                        "confidence": sp.confidence,
                    })

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_concordant,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
            "calls": c_calls,
            "gate_a_failures": c_ga,
            "gate_b_rejections": c_gb,
            "gate_c_map_rejections": c_gcm,
            "gate_c_vetoes": c_gcv,
            "claims_accepted_gate_chain_count": c_acc,
            "accepted_claims": accepted_claims,
            "criterion_assessments": [
                {
                    "code": ca.criterion_code,
                    "status": ca.status.value,
                    "rationale": ca.clinical_rationale,
                    "is_exclusion": ca.is_exclusion,
                }
                for ca in res.criterion_assessments
            ],
        })

    elapsed = round(time.time() - t0, 2)
    telem = pipeline.llm_proposer.telemetry

    calls = telem.get("total_calls", 0)
    gate_a_fails = telem.get("gate_a_rejections", 0)
    gate_b_fails = telem.get("gate_b_rejections", 0)
    gate_c_fails = telem.get("gate_c_map_rejections", 0)
    gate_c_vetoes = telem.get("gate_c_vetoes", 0)
    proposals_accepted = telem.get("proposals_accepted", 0)

    # Teardown
    cm_mod._GLOBAL_CONCEPT_MAP = None

    return {
        "arm_name": "Arm A: Pipeline Path (Declarative, Committed Map 12 Concepts)",
        "span_repair_enabled": span_repair_enabled,
        "elapsed_seconds": elapsed,
        "total_cases": len(vignettes),
        "calls": calls,
        "gate_a_failures": gate_a_fails,
        "gate_b_rejections": gate_b_fails,
        "gate_c_map_rejections": gate_c_fails,
        "gate_c_vetoes": gate_c_vetoes,
        "claims_accepted": proposals_accepted,
        "concordant_decisions": concordant_count,
        "accuracy_pct": round(concordant_count / len(vignettes) * 100.0, 1),
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(resolved_synonymy),
        "synonymy_resolved_cases": resolved_synonymy,
        "cases": cases,
    }


def run_arm_b(vignettes: list[dict[str, Any]], merged_map: ConceptMap, span_repair_enabled: bool = True) -> dict[str, Any]:
    """Runs Arm B: agentic message-board mode with merged map in-memory."""
    logger.info(
        f"Starting Arm B: Agentic Mode (Message Board, Merged Map 131 concepts, "
        f"span_repair={span_repair_enabled})..."
    )

    cm_mod._GLOBAL_CONCEPT_MAP = merged_map
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0
    pipeline.llm_proposer.span_repair_enabled = span_repair_enabled

    cases = []
    concordant_count = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    resolved_synonymy = []

    total_messages = 0
    total_judge_calls = 0
    total_challenges_raised = 0
    total_challenges_answered = 0
    total_concessions = 0
    total_deferrals_unresolved_disagreement = 0
    gate_a_failures = 0
    gate_b_rejections = 0
    gate_c_map_rejections = 0
    gate_c_vetoes = 0
    total_claims_accepted = 0

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-ARM-B-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="agentic",
            save_record=False,
        )
        act_dec = res.adjudication_decision.value
        is_concordant = (act_dec == exp_dec)

        if is_concordant:
            concordant_count += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                resolved_synonymy.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

        board_msgs = res.message_board or []
        msg_count = len(board_msgs)
        total_messages += msg_count

        case_judge_calls = 0
        case_challenges = 0
        case_concessions = 0
        case_defenses = 0
        case_claims_accepted = 0
        case_gate_a_failures = 0
        case_gate_b_rejections = 0
        case_gate_c_map_rejections = 0
        case_gate_c_vetoes = 0
        case_gate_chain_accepted_claims = []
        case_unresolved_disagreements = 0

        for m in board_msgs:
            mtype = m.get("message_type")
            agent = m.get("agent", "")
            meta = m.get("metadata", {})

            if mtype == "VERDICT":
                case_judge_calls += 1
                total_judge_calls += 1

            if agent.startswith("Agent 3") and mtype == "CHALLENGE":
                case_challenges += 1
                total_challenges_raised += 1
                fg = meta.get("failing_gate", "")
                if fg == "GATE_A_EXACT_SLICE":
                    case_gate_a_failures += 1
                    gate_a_failures += 1
                elif fg == "GATE_B_SEMANTIC":
                    case_gate_b_rejections += 1
                    gate_b_rejections += 1
                elif fg == "GATE_C_MAP_CHECK":
                    case_gate_c_map_rejections += 1
                    gate_c_map_rejections += 1
                elif fg in ("GATE_C_VETO", "GATE_C_AGENT3_VETO", "GATE_C_ADVERSARIAL_VETO"):
                    case_gate_c_vetoes += 1
                    gate_c_vetoes += 1

            if agent.startswith("Agent 2") and mtype == "CONCEDE":
                case_concessions += 1
                total_concessions += 1
                total_challenges_answered += 1

            if agent.startswith("Agent 2") and mtype == "DEFENSE":
                case_defenses += 1
                if meta.get("gate_chain_passed"):
                    case_claims_accepted += 1
                    total_claims_accepted += 1
                    ev = m.get("evidence")
                    source_txt = ""
                    if ev:
                        if hasattr(ev, "source_text"):
                            source_txt = ev.source_text
                        elif isinstance(ev, dict):
                            source_txt = ev.get("source_text", "")
                    case_gate_chain_accepted_claims.append({
                        "criterion_code": m.get("criterion_code"),
                        "source_text": source_txt,
                        "content": m.get("content"),
                    })

            if meta.get("disagreement_unresolved"):
                case_unresolved_disagreements += 1
                total_deferrals_unresolved_disagreement += 1

        # Accepted claims in case
        accepted_claims = []
        for ca in res.criterion_assessments:
            if ca.status.value == "MET" and ca.verified_spans:
                for sp in ca.verified_spans:
                    accepted_claims.append({
                        "criterion_code": ca.criterion_code,
                        "source_text": sp.source_text,
                        "start_char": sp.start_char,
                        "end_char": sp.end_char,
                        "confidence": sp.confidence,
                    })

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_concordant,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
            "message_count": msg_count,
            "judge_calls": case_judge_calls,
            "challenges_raised": case_challenges,
            "concessions": case_concessions,
            "calls": case_judge_calls,
            "gate_a_failures": case_gate_a_failures,
            "gate_b_rejections": case_gate_b_rejections,
            "gate_c_map_rejections": case_gate_c_map_rejections,
            "gate_c_vetoes": case_gate_c_vetoes,
            "claims_accepted_gate_chain_count": case_claims_accepted,
            "claims_accepted_gate_chain": case_gate_chain_accepted_claims,
            "unresolved_disagreements": case_unresolved_disagreements,
            "claims_accepted": accepted_claims,
            "criterion_assessments": [
                {
                    "code": ca.criterion_code,
                    "status": ca.status.value,
                    "rationale": ca.clinical_rationale,
                    "is_exclusion": ca.is_exclusion,
                }
                for ca in res.criterion_assessments
            ],
            "message_board_transcript": res.agentic_audit_trail.get("message_board_transcript", ""),
        })

    elapsed = round(time.time() - t0, 2)

    # Teardown
    cm_mod._GLOBAL_CONCEPT_MAP = None

    return {
        "arm_name": "Arm B: Agentic Mode (Message Board, Merged Map 131 Concepts)",
        "span_repair_enabled": span_repair_enabled,
        "elapsed_seconds": elapsed,
        "total_cases": len(vignettes),
        "calls": total_judge_calls,
        "gate_a_failures": gate_a_failures,
        "gate_b_rejections": gate_b_rejections,
        "gate_c_map_rejections": gate_c_map_rejections,
        "gate_c_vetoes": gate_c_vetoes,
        "claims_accepted": total_claims_accepted,
        "concordant_decisions": concordant_count,
        "accuracy_pct": round(concordant_count / len(vignettes) * 100.0, 1),
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(resolved_synonymy),
        "synonymy_resolved_cases": resolved_synonymy,
        "conversation_metrics": {
            "total_messages": total_messages,
            "mean_messages_per_case": round(total_messages / len(vignettes), 2),
            "challenges_raised_by_agent_3": total_challenges_raised,
            "challenges_answered": total_challenges_answered,
            "concessions_by_agent_2": total_concessions,
            "assessments_changed_by_debate": total_concessions,
            "deferrals_from_unresolved_disagreement": total_deferrals_unresolved_disagreement,
        },
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare Arm A (declarative) and Arm B (agentic)")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "app" / "data" / "benchmarks" / "agentic_v36_comparison_raw_span_repair_on.json"),
        help="Path to output raw JSON"
    )
    parser.add_argument(
        "--span-repair",
        dest="span_repair",
        action="store_true",
        default=True,
        help="Enable span repair (production default: True)"
    )
    parser.add_argument(
        "--no-span-repair",
        dest="span_repair",
        action="store_false",
        help="Disable span repair (v37 historical setting)"
    )
    args = parser.parse_args()

    logger.info("Loading 84 development vignettes...")
    vignettes_file = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    merged_map, committed_count, added_drafts = build_merged_in_memory_map()

    # Run Arm A
    arm_a_results = run_arm_a(vignettes, span_repair_enabled=args.span_repair)

    # Run Arm B
    arm_b_results = run_arm_b(vignettes, merged_map, span_repair_enabled=args.span_repair)

    comparison_summary = {
        "metadata": {
            "execution_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "script_version": "v37.1 (span repair enabled, recomputable per-case records)",
            "git_head": "8b72d5236b22e96d7aef28cb9dfb5e3ce01e13ab",
            "span_repair_enabled": args.span_repair,
            "note": "Supersedes v37 benchmark numbers where they differ due to production-default span repair setting.",
            "dataset": "84 dev vignettes, author-written, not held-out, not clinical validation",
            "model": "qwen2.5:3b (local Ollama)",
            "budget": "3 calls / 30s per case",
            "concept_map_arm_a": f"Committed map ({committed_count} concepts)",
            "concept_map_arm_b": f"Merged map ({committed_count} committed + {added_drafts} drafts = {merged_map.total_concepts} concepts)",
        },
        "headline_metrics": {
            "arm_a_concordant_decisions": f"{arm_a_results['concordant_decisions']}/{arm_a_results['total_cases']} ({arm_a_results['accuracy_pct']}%)",
            "arm_b_concordant_decisions": f"{arm_b_results['concordant_decisions']}/{arm_b_results['total_cases']} ({arm_b_results['accuracy_pct']}%)",
            "arm_a_synonymy_resolved": f"{arm_a_results['synonymy_resolved_count']}/19",
            "arm_b_synonymy_resolved": f"{arm_b_results['synonymy_resolved_count']}/19",
            "decision_delta": arm_b_results["concordant_decisions"] - arm_a_results["concordant_decisions"],
            "synonymy_resolved_delta": arm_b_results["synonymy_resolved_count"] - arm_a_results["synonymy_resolved_count"],
            "arm_b_false_approvals": arm_b_results["false_approvals"],
        },
        "arm_a": arm_a_results,
        "arm_b": arm_b_results,
    }

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(comparison_summary, f, indent=2)

    logger.info(f"Comparison completed successfully. Raw results saved to: {out_file}")

    print("\n" + "=" * 75)
    print(f"CLEAN COMPARISON SUMMARY: ARM A vs ARM B (span_repair={args.span_repair})")
    print("=" * 75)
    print(f"{'Metric':<35} | {'Arm A (Pipeline)':<18} | {'Arm B (Agentic)':<18}")
    print("-" * 75)
    print(f"{'Concordant Decisions':<35} | {arm_a_results['concordant_decisions']}/{arm_a_results['total_cases']} ({arm_a_results['accuracy_pct']}%)  | {arm_b_results['concordant_decisions']}/{arm_b_results['total_cases']} ({arm_b_results['accuracy_pct']}%)")
    print(f"{'Synonymy Cases Resolved':<35} | {arm_a_results['synonymy_resolved_count']}/19               | {arm_b_results['synonymy_resolved_count']}/19")
    print(f"{'LLM Calls':<35} | {arm_a_results['calls']:<18} | {arm_b_results['calls']:<18}")
    print(f"{'Gate A Failures':<35} | {arm_a_results['gate_a_failures']:<18} | {arm_b_results['gate_a_failures']:<18}")
    print(f"{'Gate B Rejections':<35} | {arm_a_results['gate_b_rejections']:<18} | {arm_b_results['gate_b_rejections']:<18}")
    print(f"{'Gate C Map Rejections':<35} | {arm_a_results['gate_c_map_rejections']:<18} | {arm_b_results['gate_c_map_rejections']:<18}")
    print(f"{'Gate C Vetoes':<35} | {arm_a_results['gate_c_vetoes']:<18} | {arm_b_results['gate_c_vetoes']:<18}")
    print(f"{'Claims Accepted':<35} | {arm_a_results['claims_accepted']:<18} | {arm_b_results['claims_accepted']:<18}")
    print(f"{'False Approvals':<35} | {arm_a_results['false_approvals']:<18} | {arm_b_results['false_approvals']:<18}")
    print(f"{'False Denials':<35} | {arm_a_results['false_denials']:<18} | {arm_b_results['false_denials']:<18}")
    print(f"{'Safe Deferrals':<35} | {arm_a_results['deferrals']:<18} | {arm_b_results['deferrals']:<18}")
    print("-" * 75)
    print("CONVERSATION METRICS (ARM B):")
    conv = arm_b_results["conversation_metrics"]
    print(f"- Total Messages: {conv['total_messages']} (Mean: {conv['mean_messages_per_case']} msgs/case)")
    print(f"- Challenges Raised by Agent 3: {conv['challenges_raised_by_agent_3']}")
    print(f"- Challenges Answered: {conv['challenges_answered']}")
    print(f"- Concessions by Agent 2: {conv['concessions_by_agent_2']}")
    print(f"- Assessments Changed by Debate: {conv['assessments_changed_by_debate']}")
    print(f"- Deferrals from Unresolved Disagreement: {conv['deferrals_from_unresolved_disagreement']}")
    print("=" * 75)


if __name__ == "__main__":
    main()
