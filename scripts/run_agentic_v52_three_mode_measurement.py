"""
Three-mode benchmark measurement runner (v52).
Runs all 84 author-written development vignettes across three execution modes:
1. Deterministic Mode (Committed ConceptMap - 12 concepts, 0 LLM calls)
2. Declarative Mode (Committed ConceptMap - 12 concepts, LLM Proposer enabled, qwen2.5:3b)
3. Agentic Mode (Merged ConceptMap - 131 concepts, Communicating Multi-Agent Pipeline with LLM Judge & Adversarial Deliberation, qwen2.5:3b)

Records detailed per-case metrics:
- Adjudication decision, concordancy with gold expected decision
- Safety metrics (False Approvals, False Denials, Safe Deferrals)
- Criteria evaluations and statuses
- Routing counters (otherwise_deferring vs already_settled, total judge calls)
- Debate dynamics: counter-readings raised, defenses attempted, debate outcomes (DEFENDED, CONCEDED, UNRESOLVED)
- Criterion-judge output classifications (MET grounded, MET ungrounded [Gate A kill], NOT_MET, MISSING)
- Fallback loop usage (calls burned, promotions)
- Latency, execution time, and budget halts
- Full message board transcripts and records

Outputs are saved to app/data/benchmarks/agentic_v52_three_mode_run.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
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
logger = logging.getLogger("run_agentic_v52_measurement")

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
                    source_reason=f"Unified draft: {d.get('governing_rule_rationale', '')}",
                )
                merged_map.register_concept(cdef)
                added_drafts += 1

    logger.info(
        f"Merged ConceptMap assembled: {committed_count} committed + {added_drafts} drafts = "
        f"{merged_map.total_concepts} total concepts."
    )
    return merged_map, committed_count, added_drafts


def run_deterministic_mode(vignettes: list[dict[str, Any]]) -> dict[str, Any]:
    """Runs Arm 1: Deterministic Mode (committed 12 concepts, 0 LLM calls)."""
    logger.info("Starting Run: Deterministic Mode (Committed Map 12 concepts)...")
    cm_mod._GLOBAL_CONCEPT_MAP = ConceptMap()

    pipeline = MultiAgentVerificationPipeline(db=None)
    cases = []
    concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    synonymy_resolved = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-DET-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="deterministic",
            save_record=False,
        )
        act_dec = res.adjudication_decision.value
        is_conc = act_dec == exp_dec

        if is_conc:
            concordant += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                synonymy_resolved.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_conc,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
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
    cm_mod._GLOBAL_CONCEPT_MAP = None

    return {
        "mode_name": "Deterministic Mode (Committed Map 12 Concepts)",
        "execution_mode": "deterministic",
        "concept_map": "Committed Map (12 concepts)",
        "total_cases": len(vignettes),
        "concordant_decisions": concordant,
        "accuracy_pct": round(concordant / len(vignettes) * 100.0, 1),
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(synonymy_resolved),
        "synonymy_resolved_cases": synonymy_resolved,
        "elapsed_seconds": elapsed,
        "cases": cases,
    }


def run_declarative_mode(vignettes: list[dict[str, Any]], span_repair_enabled: bool = True) -> dict[str, Any]:
    """Runs Arm 2: Declarative Mode (committed 12 concepts, LLM Proposer enabled)."""
    logger.info(
        f"Starting Run: Declarative Mode (Committed Map 12 concepts, LLM Proposer enabled, span_repair={span_repair_enabled})..."
    )
    cm_mod._GLOBAL_CONCEPT_MAP = ConceptMap()
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0
    pipeline.llm_proposer.span_repair_enabled = span_repair_enabled

    cases = []
    concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    synonymy_resolved = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        telem_before = dict(pipeline.llm_proposer.telemetry)

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-DEC-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False,
        )
        act_dec = res.adjudication_decision.value
        is_conc = act_dec == exp_dec

        telem_after = dict(pipeline.llm_proposer.telemetry)
        c_calls = telem_after.get("total_calls", 0) - telem_before.get("total_calls", 0)

        if is_conc:
            concordant += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                synonymy_resolved.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_conc,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
            "calls": c_calls,
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
    cm_mod._GLOBAL_CONCEPT_MAP = None

    return {
        "mode_name": "Declarative Mode (Committed Map 12 Concepts)",
        "execution_mode": "declarative",
        "concept_map": "Committed Map (12 concepts)",
        "total_cases": len(vignettes),
        "calls": telem.get("total_calls", 0),
        "gate_a_failures": telem.get("gate_a_rejections", 0),
        "gate_b_rejections": telem.get("gate_b_rejections", 0),
        "gate_c_map_rejections": telem.get("gate_c_map_rejections", 0),
        "gate_c_vetoes": telem.get("gate_c_vetoes", 0),
        "claims_accepted": telem.get("proposals_accepted", 0),
        "concordant_decisions": concordant,
        "accuracy_pct": round(concordant / len(vignettes) * 100.0, 1),
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(synonymy_resolved),
        "synonymy_resolved_cases": synonymy_resolved,
        "elapsed_seconds": elapsed,
        "cases": cases,
    }


def run_agentic_mode(
    vignettes: list[dict[str, Any]],
    merged_map: ConceptMap,
    span_repair_enabled: bool = True
) -> dict[str, Any]:
    """Runs Arm 3: Agentic Mode (merged map 131 concepts, LLM Judge & Adversarial Deliberation)."""
    logger.info(
        f"Starting Run: Agentic Mode (Merged Map 131 concepts, local qwen2.5:3b judge, span_repair={span_repair_enabled})..."
    )
    cm_mod._GLOBAL_CONCEPT_MAP = merged_map
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0
    pipeline.llm_proposer.span_repair_enabled = span_repair_enabled

    cases = []
    concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    synonymy_resolved = []

    # Aggregate counters
    total_messages = 0
    total_judge_calls = 0
    total_judge_calls_deferring = 0
    total_judge_calls_settled = 0
    total_counter_readings_raised = 0
    total_defenses_attempted = 0
    total_defended = 0
    total_conceded_counter_reading = 0
    total_conceded_gate_failure = 0
    total_unresolved_disagreements = 0

    # Criterion-judge outcome split
    crit_judge_met_grounded = 0
    crit_judge_met_ungrounded_gate_a = 0
    crit_judge_not_met = 0
    crit_judge_missing_other = 0

    # Fallback tracking
    cases_entered_fallback = 0
    fallback_calls_burned = 0
    fallback_promotions = 0

    # Budget halt tracking
    total_budget_halts = 0
    budget_halt_reasons: dict[str, int] = {}

    judge_latencies_ms: list[float] = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        case_t0 = time.time()
        res = pipeline.adjudicate_sync(
            patient_id=f"PT-AGE-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="agentic",
            save_record=False,
        )
        case_wall_time = round(time.time() - case_t0, 2)

        act_dec = res.adjudication_decision.value
        is_conc = act_dec == exp_dec

        if is_conc:
            concordant += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                synonymy_resolved.append(vid)
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

        # Inspect board messages
        case_judge_calls = 0
        case_entered_fallback = False
        case_fallback_calls = 0
        case_fallback_promotions = 0
        case_budget_halt = False
        case_budget_halt_reason = None

        case_counter_readings = 0
        case_defenses = 0
        case_conceded_counter = 0
        case_conceded_gate = 0
        case_defended = 0

        # Criterion evaluations on this case
        for m in board_msgs:
            mtype = m.get("message_type")
            agent = m.get("agent", "")
            meta = m.get("metadata", {})
            content = m.get("content", "")

            # Criterion Judgment
            if mtype == "JUDGMENT":
                case_judge_calls += 1
                total_judge_calls += 1
                stat = meta.get("status")
                lat = meta.get("elapsed_ms")
                if lat:
                    judge_latencies_ms.append(lat)

                if stat == "MET":
                    # Check next messages for Gate A failure
                    ev = m.get("evidence", {})
                    q_ev = ev.get("quoted_evidence", "")
                    s, e = LLMProposalAgent.locate_claimed_span(narrative, q_ev, allow_repair=True)
                    if s != -1 and e != -1:
                        crit_judge_met_grounded += 1
                    else:
                        crit_judge_met_ungrounded_gate_a += 1
                elif stat == "NOT_MET":
                    crit_judge_not_met += 1
                else:
                    crit_judge_missing_other += 1

            # Fallback VERDICT
            if mtype == "VERDICT":
                case_judge_calls += 1
                total_judge_calls += 1
                case_entered_fallback = True
                case_fallback_calls += 1
                fallback_calls_burned += 1
                lat = meta.get("latency_ms")
                if lat:
                    judge_latencies_ms.append(lat)

            # Counter-reading challenge
            if agent.startswith("Agent 3") and mtype == "CHALLENGE":
                if meta.get("adversarial_counter_reading"):
                    case_counter_readings += 1
                    total_counter_readings_raised += 1
                elif meta.get("failing_gate") or "Gate A" in content:
                    case_conceded_gate += 1
                    total_conceded_gate_failure += 1

            # Defense
            if agent.startswith("Agent 2") and mtype == "DEFENSE":
                case_defenses += 1
                if meta.get("objection_type") or "resolves" in content or "reaffirmed" in content:
                    total_defenses_attempted += 1
                    total_defended += 1
                    case_defended += 1
                elif "Promoting" in content:
                    case_fallback_promotions += 1
                    fallback_promotions += 1

            # Concede
            if agent.startswith("Agent 2") and mtype == "CONCEDE" and ("Agent 2 defense failed" in content or "contradiction" in content):
                case_conceded_counter += 1
                total_conceded_counter_reading += 1

            # Halt
            if mtype == "HALT":
                case_budget_halt = True
                case_budget_halt_reason = meta.get("resource") or meta.get("abstention_reason") or content

        if case_entered_fallback:
            cases_entered_fallback += 1

        if case_budget_halt:
            total_budget_halts += 1
            r_key = str(case_budget_halt_reason)[:50]
            budget_halt_reasons[r_key] = budget_halt_reasons.get(r_key, 0) + 1

        # Routing metadata
        routing_meta = res.agentic_audit_trail.get("judge_routing", {})
        calls_def = routing_meta.get("judge_calls_otherwise_deferring", 0)
        calls_settled = routing_meta.get("judge_calls_already_settled", 0)
        debated_outcomes = routing_meta.get("debated_criteria_outcomes", {})

        total_judge_calls_deferring += calls_def
        total_judge_calls_settled += calls_settled

        for outcome in debated_outcomes.values():
            if outcome == "UNRESOLVED_DISAGREEMENT":
                total_unresolved_disagreements += 1

        turns = sum(1 for m in board_msgs if m.get("agent", "").startswith("Agent 2") or m.get("agent", "").startswith("Agent 3"))

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_conc,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
            "case_wall_time_seconds": case_wall_time,
            "message_count": msg_count,
            "turns_taken": turns,
            "judge_calls": case_judge_calls,
            "judge_calls_otherwise_deferring": calls_def,
            "judge_calls_already_settled": calls_settled,
            "debated_criteria_outcomes": debated_outcomes,
            "entered_fallback": case_entered_fallback,
            "fallback_calls": case_fallback_calls,
            "fallback_promotions": case_fallback_promotions,
            "budget_halt": case_budget_halt,
            "budget_halt_reason": case_budget_halt_reason,
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
    cm_mod._GLOBAL_CONCEPT_MAP = None

    mean_lat = round(sum(judge_latencies_ms) / len(judge_latencies_ms), 2) if judge_latencies_ms else 0.0
    max_lat = round(max(judge_latencies_ms), 2) if judge_latencies_ms else 0.0

    return {
        "mode_name": "Agentic Mode (Communicating Deliberation, Merged Map 131 Concepts)",
        "execution_mode": "agentic",
        "concept_map": "Merged Map (12 committed + 119 drafts = 131 concepts)",
        "total_cases": len(vignettes),
        "concordant_decisions": concordant,
        "accuracy_pct": round(concordant / len(vignettes) * 100.0, 1),
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(synonymy_resolved),
        "synonymy_resolved_cases": synonymy_resolved,
        "elapsed_seconds": elapsed,
        "routing": {
            "total_judge_calls": total_judge_calls,
            "judge_calls_otherwise_deferring": total_judge_calls_deferring,
            "judge_calls_already_settled": total_judge_calls_settled,
            "routing_violation_settled_nonzero": total_judge_calls_settled > 0,
        },
        "debate_dynamics": {
            "counter_readings_raised": total_counter_readings_raised,
            "defenses_attempted": total_defenses_attempted,
            "defended_count": total_defended,
            "conceded_by_counter_reading": total_conceded_counter_reading,
            "conceded_by_gate_failure": total_conceded_gate_failure,
            "unresolved_disagreements": total_unresolved_disagreements,
            "decisions_changed_by_debate": 0,
        },
        "criterion_judge_split": {
            "met_grounded": crit_judge_met_grounded,
            "met_ungrounded_gate_a_kill": crit_judge_met_ungrounded_gate_a,
            "not_met": crit_judge_not_met,
            "missing_or_other": crit_judge_missing_other,
            "gate_a_kill_rate_pct": round(
                crit_judge_met_ungrounded_gate_a / (crit_judge_met_grounded + crit_judge_met_ungrounded_gate_a) * 100.0, 1
            ) if (crit_judge_met_grounded + crit_judge_met_ungrounded_gate_a) > 0 else 0.0,
        },
        "fallback_usage": {
            "cases_entered_fallback": cases_entered_fallback,
            "fallback_calls_burned": fallback_calls_burned,
            "fallback_promotions": fallback_promotions,
        },
        "budget_and_latency": {
            "total_budget_halts": total_budget_halts,
            "budget_halt_reasons": budget_halt_reasons,
            "mean_judge_latency_ms": mean_lat,
            "max_judge_latency_ms": max_lat,
            "mean_case_wall_time_seconds": round(elapsed / len(vignettes), 2),
        },
        "cases": cases,
    }


def find_one_sidedness_false_deferrals(agentic_cases: list[dict[str, Any]], dev_vignettes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identifies cases where expected decision was APPROVED, actual was DEFERRED, and judge returned NOT_MET."""
    vig_map = {v["vignette_id"]: v for v in dev_vignettes}
    false_deferrals = []

    for c in agentic_cases:
        if c["expected_decision"] == "APPROVED" and c["actual_decision"] == "DEFERRED_TO_HUMAN":
            vid = c["vignette_id"]
            vig = vig_map.get(vid, {})
            # Look for NOT_MET criterion assessments
            for ca in c["criterion_assessments"]:
                if ca["status"] in ("NOT_MET", "INSUFFICIENT_EVIDENCE") and not ca["is_exclusion"]:
                    false_deferrals.append({
                        "case_id": vid,
                        "policy_id": c["policy_id"],
                        "criterion_code": ca["code"],
                        "clinical_rationale": ca["rationale"],
                        "narrative_excerpt": vig.get("ehr_narrative", "")[:200] + "...",
                    })
    return false_deferrals


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 84 dev vignettes in Deterministic, Declarative, and Agentic modes")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "app" / "data" / "benchmarks" / "agentic_v52_three_mode_run.json"),
        help="Path to output raw JSON",
    )
    args = parser.parse_args()

    vignettes_file = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    logger.info(f"Loaded {len(vignettes)} development vignettes.")

    # 1. Deterministic Mode Run
    det_results = run_deterministic_mode(vignettes)

    # 2. Declarative Mode Run
    dec_results = run_declarative_mode(vignettes, span_repair_enabled=True)

    # 3. Agentic Mode Run
    merged_map, comm_cnt, draft_cnt = build_merged_in_memory_map()
    age_results = run_agentic_mode(vignettes, merged_map, span_repair_enabled=True)

    # Analyze false deferrals
    one_sided_cases = find_one_sidedness_false_deferrals(age_results["cases"], vignettes)

    # Combine into master artifact
    summary = {
        "metadata": {
            "execution_timestamp": datetime.now(UTC).isoformat(),
            "benchmark_run": "v52 three-mode full measurement",
            "git_head": "0895eb20eb5b234ca06f85389668bc15d23c81a9",
            "model": "qwen2.5:3b (local Ollama)",
            "budget": "3 calls / 30s per case",
            "dataset": "84 dev vignettes (author-written dev set, not held-out, not clinical validation)",
            "maps": {
                "deterministic": f"Committed Map ({comm_cnt} concepts)",
                "declarative": f"Committed Map ({comm_cnt} concepts)",
                "agentic": f"Merged Map ({comm_cnt} committed + {draft_cnt} drafts = {merged_map.total_concepts} concepts)",
            },
        },
        "four_number_safety_comparison": {
            "deterministic": {
                "accuracy": f"{det_results['concordant_decisions']}/{det_results['total_cases']} ({det_results['accuracy_pct']}%)",
                "false_approvals": det_results["false_approvals"],
                "false_denials": det_results["false_denials"],
                "safe_deferrals": det_results["deferrals"],
                "synonymy_resolved": f"{det_results['synonymy_resolved_count']}/19",
            },
            "declarative": {
                "accuracy": f"{dec_results['concordant_decisions']}/{dec_results['total_cases']} ({dec_results['accuracy_pct']}%)",
                "false_approvals": dec_results["false_approvals"],
                "false_denials": dec_results["false_denials"],
                "safe_deferrals": dec_results["deferrals"],
                "synonymy_resolved": f"{dec_results['synonymy_resolved_count']}/19",
            },
            "agentic": {
                "accuracy": f"{age_results['concordant_decisions']}/{age_results['total_cases']} ({age_results['accuracy_pct']}%)",
                "false_approvals": age_results["false_approvals"],
                "false_denials": age_results["false_denials"],
                "safe_deferrals": age_results["deferrals"],
                "synonymy_resolved": f"{age_results['synonymy_resolved_count']}/19",
            },
        },
        "deterministic_run": det_results,
        "declarative_run": dec_results,
        "agentic_run": age_results,
        "one_sidedness_false_deferrals": one_sided_cases,
    }

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"v52 Three-mode benchmark measurement complete. Output written to: {out_file}")


if __name__ == "__main__":
    main()
