"""
Three-mode benchmark measurement runner (v54).
Runs all 84 author-written development vignettes across three execution modes:
1. Deterministic Mode (Committed ConceptMap - 12 concepts, 0 LLM calls)
2. Declarative Mode (Committed ConceptMap - 12 concepts, LLM Proposer enabled, qwen2.5:3b)
3. Agentic Mode (Merged ConceptMap - 131 concepts, Communicating Multi-Agent Pipeline with LLM Judge, Adversarial Deliberation, Agent 3 Advocate, Capped Fallback, 60s per-case budget, qwen2.5:3b)

Records detailed per-case metrics:
- Adjudication decision, concordancy with gold expected decision
- Safety metrics (False Approvals, False Denials, Safe Deferrals)
- Criteria evaluations and statuses
- Routing counters (otherwise_deferring vs already_settled, advocacy_on_settled, total judge calls)
- Debate dynamics: counter-readings raised (by objection type), defense calls attempted, defense outcomes (defended, conceded, budget-refused)
- Advocacy metrics: attempts, promotions, rejections (Gate A vs Gate B vs Gate C vs empty quote)
- Per-criterion advocate outcome and blocking step for the 18 false deferrals
- Fallback usage: cases entering fallback, fallback calls burned (as real integer on every case), promotions
- Budget: cases exceeding 60s wall time, halts by type, defense refused for budget
- Latency, execution time (mean/min/max per case, mean/max judge)
- Full message board transcripts and records

Outputs are saved to app/data/benchmarks/agentic_v54_three_mode_run.json
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
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_agentic_v54_measurement")

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

TARGET_18_FALSE_DEFERRALS = [
    {"vignette_id": "DEV-LCD-KYPHO-APP", "policy_id": "LCD-KYPHO", "criterion_code": "CRIT-KYPHO-01"},
    {"vignette_id": "DEV-LCD-KYPHO-APP", "policy_id": "LCD-KYPHO", "criterion_code": "CRIT-KYPHO-02"},
    {"vignette_id": "DEV-LCD-MRI-BRAIN-APP", "policy_id": "LCD-MRI-BRAIN", "criterion_code": "CRIT-MRIB-02"},
    {"vignette_id": "DEV-LCD-MRI-LUMBAR-APP", "policy_id": "LCD-MRI-LUMBAR", "criterion_code": "CRIT-MRIL-02"},
    {"vignette_id": "DEV-LCD-PAD-ATHERO-APP", "policy_id": "LCD-PAD-ATHERO", "criterion_code": "CRIT-PAD-01"},
    {"vignette_id": "DEV-LCD-PAD-ATHERO-APP", "policy_id": "LCD-PAD-ATHERO", "criterion_code": "CRIT-PAD-02"},
    {"vignette_id": "DEV-LCD-PCI-APP", "policy_id": "LCD-PCI", "criterion_code": "CRIT-PCI-01"},
    {"vignette_id": "DEV-LCD-POWER-WC-APP", "policy_id": "LCD-POWER-WC", "criterion_code": "CRIT-PWC-02"},
    {"vignette_id": "DEV-LCD-SBRT-APP", "policy_id": "LCD-SBRT", "criterion_code": "CRIT-SBRT-01"},
    {"vignette_id": "DEV-NCD-CATARACT-APP", "policy_id": "NCD-CATARACT", "criterion_code": "CRIT-CAT-01"},
    {"vignette_id": "DEV-NCD-CATARACT-APP", "policy_id": "NCD-CATARACT", "criterion_code": "CRIT-CAT-02"},
    {"vignette_id": "DEV-NCD-CCTA-APP", "policy_id": "NCD-CCTA", "criterion_code": "CRIT-CCTA-01"},
    {"vignette_id": "DEV-NCD-PACEMAKER-APP", "policy_id": "NCD-PACEMAKER", "criterion_code": "CRIT-PACE-02"},
    {"vignette_id": "DEV-NCD-PET-ONC-APP", "policy_id": "NCD-PET-ONC", "criterion_code": "CRIT-PTONC-01"},
    {"vignette_id": "DEV-NCD-SCS-APP", "policy_id": "NCD-SCS", "criterion_code": "CRIT-SCS-01"},
    {"vignette_id": "DEV-NCD-SCS-APP", "policy_id": "NCD-SCS", "criterion_code": "CRIT-SCS-02"},
    {"vignette_id": "DEV-NCD-SGD-APP", "policy_id": "NCD-SGD", "criterion_code": "CRIT-SGD-02"},
    {"vignette_id": "DEV-OPD-SI-FUSION-APP", "policy_id": "OPD-SI-FUSION", "criterion_code": "CRIT-SI-01"},
]


def build_merged_in_memory_map() -> tuple[ConceptMap, int, int]:
    """Builds the in-memory merged concept map: 12 committed + 119 PASS draft concepts = 131 total."""
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


def run_deterministic_mode(vignettes: list[dict[str, Any]], db_session: Any) -> dict[str, Any]:
    """Runs Arm 1: Deterministic Mode (committed 12 concepts, 0 LLM calls)."""
    logger.info("Starting Run: Deterministic Mode (Committed Map 12 concepts, carepolicyguard.db)...")
    cm_mod._GLOBAL_CONCEPT_MAP = ConceptMap()

    pipeline = MultiAgentVerificationPipeline(db=db_session)
    cases = []
    concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    synonymy_resolved = []
    case_latencies = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        c_t0 = time.time()
        res = pipeline.adjudicate_sync(
            patient_id=f"PT-DET-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="deterministic",
            save_record=False,
        )
        c_wall = round(time.time() - c_t0, 3)
        case_latencies.append(c_wall)

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
            "case_wall_time_seconds": c_wall,
            "fallback_calls": 0,
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
        "mean_case_wall_time_seconds": round(sum(case_latencies) / len(case_latencies), 3),
        "min_case_wall_time_seconds": min(case_latencies),
        "max_case_wall_time_seconds": max(case_latencies),
        "cases": cases,
    }


def run_declarative_mode(
    vignettes: list[dict[str, Any]], db_session: Any, span_repair_enabled: bool = True
) -> dict[str, Any]:
    """Runs Arm 2: Declarative Mode (committed 12 concepts, LLM Proposer enabled, local qwen2.5:3b)."""
    logger.info(
        f"Starting Run: Declarative Mode (Committed Map 12 concepts, LLM Proposer enabled, carepolicyguard.db, span_repair={span_repair_enabled})..."
    )
    cm_mod._GLOBAL_CONCEPT_MAP = ConceptMap()
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=db_session)
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
    case_latencies = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        telem_before = dict(pipeline.llm_proposer.telemetry)
        c_t0 = time.time()

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-DEC-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False,
        )
        c_wall = round(time.time() - c_t0, 3)
        case_latencies.append(c_wall)

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
            "case_wall_time_seconds": c_wall,
            "calls": c_calls,
            "fallback_calls": 0,
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
        "mean_case_wall_time_seconds": round(sum(case_latencies) / len(case_latencies), 3),
        "min_case_wall_time_seconds": min(case_latencies),
        "max_case_wall_time_seconds": max(case_latencies),
        "cases": cases,
    }


def run_agentic_mode(
    vignettes: list[dict[str, Any]],
    merged_map: ConceptMap,
    db_session: Any,
    span_repair_enabled: bool = True,
) -> dict[str, Any]:
    """Runs Arm 3: Agentic Mode (merged map 131 concepts, LLM Judge, Adversarial Deliberation, Advocate, Capped Fallback, 60s budget)."""
    logger.info(
        f"Starting Run: Agentic Mode (Merged Map 131 concepts, local qwen2.5:3b judge, carepolicyguard.db, 60s budget, span_repair={span_repair_enabled})..."
    )
    cm_mod._GLOBAL_CONCEPT_MAP = merged_map
    LLMProposalAgent.span_repair_enabled = span_repair_enabled

    pipeline = MultiAgentVerificationPipeline(db=db_session)
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
    total_advocacy_calls_settled = 0

    # Advocacy counters
    total_advocacy_attempts = 0
    total_advocacy_promotions = 0
    total_advocacy_rejections = 0
    advocacy_rejections_gate_a = 0
    advocacy_rejections_gate_b_or_c = 0
    advocacy_rejections_empty_quote = 0
    rescued_criteria_list = []

    # Defense calls counters (calls to generate_defense_sync, not just DEFENSE messages)
    total_defense_calls_attempted = 0
    total_defense_defended = 0
    total_defense_conceded_clinical = 0
    total_defense_refused_budget = 0

    # Debate counters
    total_counter_readings_raised = 0
    counter_reading_types: dict[str, int] = {}
    total_conceded_counter_reading = 0
    total_conceded_gate_failure = 0
    total_unresolved_disagreements = 0
    decisions_changed_by_debate = 0

    # Criterion-judge outcome split
    crit_judge_met_grounded = 0
    crit_judge_met_ungrounded_gate_a = 0
    crit_judge_not_met = 0
    crit_judge_missing_other = 0

    # Fallback tracking
    cases_entered_fallback = 0
    fallback_calls_burned = 0
    fallback_promotions = 0

    # Budget & latency tracking
    total_budget_halts = 0
    budget_halt_reasons: dict[str, int] = {}
    cases_exceeding_60s_wall = 0
    judge_latencies_ms: list[float] = []
    case_wall_times: list[float] = []

    # Per-case details map for target 18 false deferrals
    per_criterion_advocate_records: dict[str, dict[str, Any]] = {}

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
        case_wall_times.append(case_wall_time)
        if case_wall_time > 60.0:
            cases_exceeding_60s_wall += 1

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

        # Inspect board messages for this case
        case_judge_calls = 0
        case_entered_fallback = False
        case_fallback_calls = 0  # real integer, never None
        case_fallback_promotions = 0
        case_budget_halt = False
        case_budget_halt_reason = None

        case_counter_readings = 0
        case_counter_types = []
        case_defense_calls = 0
        case_defense_defended = 0
        case_defense_conceded = 0
        case_defense_budget_refused = 0

        case_advocacy_attempts = 0
        case_advocacy_promotions = 0
        case_advocacy_rejections = 0
        case_advocacy_gate_a = 0
        case_advocacy_gate_b_c = 0
        case_advocacy_empty = 0

        case_conceded_counter = 0
        case_conceded_gate = 0

        for m in board_msgs:
            mtype = m.get("message_type")
            agent = m.get("agent", "")
            meta = m.get("metadata", {})
            content = m.get("content", "")
            ccode = m.get("criterion_code")

            # 1. Initial Criterion Judgment
            if mtype == "JUDGMENT":
                case_judge_calls += 1
                total_judge_calls += 1
                stat = meta.get("status")
                lat = meta.get("elapsed_ms")
                if lat:
                    judge_latencies_ms.append(lat)

                if stat == "MET":
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

            # 2. Counter-Reading Challenges from Agent 3
            if agent.startswith("Agent 3") and mtype == "CHALLENGE":
                if meta.get("adversarial_counter_reading"):
                    case_counter_readings += 1
                    total_counter_readings_raised += 1
                    obj_t = meta.get("objection_type", "UNKNOWN")
                    case_counter_types.append(obj_t)
                    counter_reading_types[obj_t] = counter_reading_types.get(obj_t, 0) + 1
                elif meta.get("failing_gate") or "Gate A" in content:
                    if not meta.get("advocacy_rejected"):
                        case_conceded_gate += 1
                        total_conceded_gate_failure += 1

            # 3. Defense Attempts (calls to generate_defense_sync)
            # A defense call happens when:
            # - Agent 2 posts DEFENSE with objection_type or defense_quote
            # - Agent 2 posts CONCEDE with metadata having defense_quote (failed quote)
            # - If budget refused: Agent 2 posts CONCEDE with content mentioning "operational budget exhaustion" and no defense_quote
            if agent.startswith("Agent 2") and mtype == "DEFENSE" and (meta.get("defense_quote") or meta.get("objection_type")):
                case_defense_calls += 1
                total_defense_calls_attempted += 1
                case_defense_defended += 1
                total_defense_defended += 1

            if agent.startswith("Agent 2") and mtype == "CONCEDE":
                if "operational budget exhaustion" in content:
                    case_defense_budget_refused += 1
                    total_defense_refused_budget += 1
                elif meta.get("defense_quote") is not None or "defense failed to provide" in content:
                    case_defense_calls += 1
                    total_defense_calls_attempted += 1
                    case_defense_conceded += 1
                    total_defense_conceded_clinical += 1
                    case_conceded_counter += 1
                    total_conceded_counter_reading += 1

            # 4. Advocacy Messages
            if agent.startswith("Agent 3") and mtype == "ADVOCACY":
                case_advocacy_attempts += 1
                total_advocacy_attempts += 1
                adv_q = meta.get("advocacy_quote", "")
                adv_rat = meta.get("advocacy_rationale", "")
                lat = meta.get("elapsed_ms")
                if lat:
                    judge_latencies_ms.append(lat)
                if ccode:
                    key = f"{vid}::{ccode}"
                    per_criterion_advocate_records[key] = {
                        "vignette_id": vid,
                        "policy_id": pid,
                        "criterion_code": ccode,
                        "advocate_attempted": True,
                        "advocate_outcome": "PENDING",
                        "blocking_step": None,
                        "advocate_quote": adv_q,
                        "advocate_rationale": adv_rat,
                    }

            if agent.startswith("Agent 2") and mtype == "DEFENSE" and meta.get("advocacy_promoted"):
                case_advocacy_promotions += 1
                total_advocacy_promotions += 1
                rescued_criteria_list.append({
                    "vignette_id": vid,
                    "criterion_code": ccode,
                    "quote": meta.get("quote"),
                    "rationale": content,
                })
                if ccode:
                    key = f"{vid}::{ccode}"
                    if key in per_criterion_advocate_records:
                        per_criterion_advocate_records[key]["advocate_outcome"] = "RESCUED"
                        per_criterion_advocate_records[key]["blocking_step"] = "N/A (Promoted to MET)"

            if agent.startswith("Agent 3") and mtype == "CHALLENGE" and meta.get("advocacy_rejected"):
                case_advocacy_rejections += 1
                total_advocacy_rejections += 1
                fg = meta.get("failing_gate") or meta.get("gate")
                if meta.get("empty_quote"):
                    advocacy_rejections_empty_quote += 1
                    case_advocacy_empty += 1
                    block_reason = "Empty quote (no supporting evidence)"
                elif fg == "Gate A" or "Gate A" in content:
                    advocacy_rejections_gate_a += 1
                    case_advocacy_gate_a += 1
                    block_reason = "Gate A (Verbatim grounding failure)"
                else:
                    advocacy_rejections_gate_b_or_c += 1
                    case_advocacy_gate_b_c += 1
                    block_reason = f"{fg or 'Gate B/C'} ({content[:60]}...)"

                if ccode:
                    key = f"{vid}::{ccode}"
                    if key in per_criterion_advocate_records:
                        per_criterion_advocate_records[key]["advocate_outcome"] = "REJECTED"
                        per_criterion_advocate_records[key]["blocking_step"] = block_reason

            # 5. Fallback VERDICT
            if mtype == "VERDICT":
                case_judge_calls += 1
                total_judge_calls += 1
                case_entered_fallback = True
                case_fallback_calls += 1
                fallback_calls_burned += 1
                lat = meta.get("latency_ms")
                if lat:
                    judge_latencies_ms.append(lat)

            if agent.startswith("Agent 2") and mtype == "DEFENSE" and not meta.get("advocacy_promoted") and not meta.get("defense_quote"):
                case_fallback_promotions += 1
                fallback_promotions += 1

            # 6. Halt
            if mtype == "HALT":
                case_budget_halt = True
                case_budget_halt_reason = meta.get("resource") or meta.get("abstention_reason") or content

        if case_entered_fallback:
            cases_entered_fallback += 1

        if case_budget_halt:
            total_budget_halts += 1
            r_key = str(case_budget_halt_reason)[:50]
            budget_halt_reasons[r_key] = budget_halt_reasons.get(r_key, 0) + 1

        # Routing metadata from audit trail
        routing_meta = res.agentic_audit_trail.get("judge_routing", {})
        calls_def = routing_meta.get("judge_calls_otherwise_deferring", 0)
        calls_settled = routing_meta.get("judge_calls_already_settled", 0)
        debated_outcomes = routing_meta.get("debated_criteria_outcomes", {})

        total_judge_calls_deferring += calls_def
        total_judge_calls_settled += calls_settled

        for outcome in debated_outcomes.values():
            if outcome == "UNRESOLVED_DISAGREEMENT":
                total_unresolved_disagreements += 1

        turns = sum(
            1 for m in board_msgs if m.get("agent", "").startswith("Agent 2") or m.get("agent", "").startswith("Agent 3")
        )

        cases.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "is_concordant": is_conc,
            "abstention_reason": getattr(res, "abstention_reason", None),
            "calibrated_confidence": res.calibrated_aggregate_confidence,
            "case_wall_time_seconds": case_wall_time,
            "wall_time_exceeded_60s": case_wall_time > 60.0,
            "message_count": msg_count,
            "turns_taken": turns,
            "judge_calls": case_judge_calls,
            "judge_calls_otherwise_deferring": calls_def,
            "judge_calls_already_settled": calls_settled,
            "advocacy_calls_on_settled": 0,
            "advocacy_attempts": case_advocacy_attempts,
            "advocacy_promotions": case_advocacy_promotions,
            "advocacy_rejections": case_advocacy_rejections,
            "defense_calls_attempted": case_defense_calls,
            "defense_defended": case_defense_defended,
            "defense_conceded": case_defense_conceded,
            "defense_budget_refused": case_defense_budget_refused,
            "counter_readings_raised": case_counter_readings,
            "debated_criteria_outcomes": debated_outcomes,
            "entered_fallback": case_entered_fallback,
            "fallback_calls": int(case_fallback_calls),
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

    cases_by_id = {c["vignette_id"]: c for c in cases}

    # Build structured 18 false deferrals advocate table
    false_deferrals_advocate_table = []
    for item in TARGET_18_FALSE_DEFERRALS:
        vid = item["vignette_id"]
        cid = item["criterion_code"]
        key = f"{vid}::{cid}"
        rec = per_criterion_advocate_records.get(key)
        if rec:
            false_deferrals_advocate_table.append(rec)
        else:
            c = cases_by_id.get(vid, {})
            crit_stat = "UNKNOWN"
            for ca in c.get("criterion_assessments", []):
                if ca.get("code") == cid:
                    crit_stat = ca.get("status")
                    break

            if crit_stat == "MET":
                blocking_step = "Settled before advocate (Satisfied as MET)"
                adv_outcome = "SETTLED_MET"
            elif c.get("budget_halt"):
                blocking_step = f"Budget halt before advocacy reached ({c.get('budget_halt_reason')})"
                adv_outcome = "BUDGET_HALT"
            else:
                blocking_step = f"Not routed to advocate (Status: {crit_stat}, unaddressed by judge)"
                adv_outcome = "NOT_ROUTED"

            false_deferrals_advocate_table.append({
                "vignette_id": vid,
                "policy_id": item["policy_id"],
                "criterion_code": cid,
                "advocate_attempted": False,
                "advocate_outcome": adv_outcome,
                "blocking_step": blocking_step,
                "advocate_quote": None,
                "advocate_rationale": None,
            })

    # 9-case synonymy table
    synonymy_cases_status = []
    for vid in SYNONYMY_VIGNETTE_IDS:
        c = cases_by_id.get(vid, {})
        synonymy_cases_status.append({
            "vignette_id": vid,
            "expected_decision": c.get("expected_decision"),
            "actual_decision": c.get("actual_decision"),
            "is_concordant": c.get("is_concordant"),
            "wall_time_seconds": c.get("case_wall_time_seconds"),
            "advocacy_attempts": c.get("advocacy_attempts", 0),
            "defense_calls": c.get("defense_calls_attempted", 0),
            "debated_criteria_outcomes": c.get("debated_criteria_outcomes", {}),
        })

    # SBRT and SI-FUSION regression inspection
    sbrt_case = cases_by_id.get("DEV-LCD-SBRT-APP", {})
    si_fusion_case = cases_by_id.get("DEV-OPD-SI-FUSION-APP", {})
    sbrt_si_fusion_status = {
        "DEV-LCD-SBRT-APP": {
            "actual_decision": sbrt_case.get("actual_decision"),
            "is_concordant": sbrt_case.get("is_concordant"),
            "wall_time_seconds": sbrt_case.get("case_wall_time_seconds"),
            "defense_calls_attempted": sbrt_case.get("defense_calls_attempted", 0),
            "defense_conceded": sbrt_case.get("defense_conceded", 0),
            "defense_budget_refused": sbrt_case.get("defense_budget_refused", 0),
            "debated_criteria_outcomes": sbrt_case.get("debated_criteria_outcomes", {}),
        },
        "DEV-OPD-SI-FUSION-APP": {
            "actual_decision": si_fusion_case.get("actual_decision"),
            "is_concordant": si_fusion_case.get("is_concordant"),
            "wall_time_seconds": si_fusion_case.get("case_wall_time_seconds"),
            "defense_calls_attempted": si_fusion_case.get("defense_calls_attempted", 0),
            "defense_conceded": si_fusion_case.get("defense_conceded", 0),
            "defense_budget_refused": si_fusion_case.get("defense_budget_refused", 0),
            "debated_criteria_outcomes": si_fusion_case.get("debated_criteria_outcomes", {}),
        },
    }

    return {
        "mode_name": "Agentic Mode (Communicating Deliberation, Merged Map 131 Concepts, 60s Budget)",
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
            "advocacy_calls_on_settled": total_advocacy_calls_settled,
        },
        "advocacy": {
            "total_advocacy_attempts": total_advocacy_attempts,
            "total_advocacy_promotions": total_advocacy_promotions,
            "total_advocacy_rejections": total_advocacy_rejections,
            "rejections_by_gate": {
                "gate_a_verbatim": advocacy_rejections_gate_a,
                "gate_b_or_c": advocacy_rejections_gate_b_or_c,
                "empty_quote": advocacy_rejections_empty_quote,
            },
            "rescued_criteria": rescued_criteria_list,
            "false_deferrals_advocate_table": false_deferrals_advocate_table,
        },
        "defense": {
            "defense_calls_attempted": total_defense_calls_attempted,
            "defense_defended": total_defense_defended,
            "defense_conceded_clinical": total_defense_conceded_clinical,
            "defense_refused_budget": total_defense_refused_budget,
        },
        "debate_dynamics": {
            "counter_readings_raised": total_counter_readings_raised,
            "counter_reading_objection_types": counter_reading_types,
            "defenses_attempted": total_defense_calls_attempted,
            "defended_count": total_defense_defended,
            "conceded_by_counter_reading": total_conceded_counter_reading,
            "conceded_by_gate_failure": total_conceded_gate_failure,
            "unresolved_disagreements": total_unresolved_disagreements,
            "decisions_changed_by_debate": decisions_changed_by_debate,
        },
        "criterion_judge_split": {
            "met_grounded": crit_judge_met_grounded,
            "met_ungrounded_gate_a_kill": crit_judge_met_ungrounded_gate_a,
            "not_met": crit_judge_not_met,
            "missing_or_other": crit_judge_missing_other,
            "gate_a_kill_rate_pct": round(
                crit_judge_met_ungrounded_gate_a / (crit_judge_met_grounded + crit_judge_met_ungrounded_gate_a) * 100.0, 1
            )
            if (crit_judge_met_grounded + crit_judge_met_ungrounded_gate_a) > 0
            else 0.0,
        },
        "fallback_usage": {
            "cases_entering_fallback": cases_entered_fallback,
            "fallback_calls_burned": fallback_calls_burned,
            "fallback_promotions": fallback_promotions,
        },
        "budget_and_latency": {
            "cases_exceeding_60s_wall": cases_exceeding_60s_wall,
            "total_budget_halts": total_budget_halts,
            "budget_halt_reasons": budget_halt_reasons,
            "defense_refused_for_budget": total_defense_refused_budget > 0,
            "mean_judge_latency_ms": mean_lat,
            "max_judge_latency_ms": max_lat,
            "mean_case_wall_time_seconds": round(sum(case_wall_times) / len(case_wall_times), 2),
            "min_case_wall_time_seconds": min(case_wall_times),
            "max_case_wall_time_seconds": max(case_wall_times),
        },
        "synonymy_cases_status": synonymy_cases_status,
        "sbrt_and_si_fusion_regression": sbrt_si_fusion_status,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 84 dev vignettes in Deterministic, Declarative, and Agentic modes (v54)")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "app" / "data" / "benchmarks" / "agentic_v54_three_mode_run.json"),
        help="Path to output raw JSON",
    )
    args = parser.parse_args()

    vignettes_file = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    logger.info(f"Loaded {len(vignettes)} development vignettes.")
    db_session = SessionLocal()
    db_path = str(ROOT_DIR / "carepolicyguard.db")
    logger.info(f"Database session initialized against: {db_path}")

    try:
        # 1. Deterministic Mode Run
        det_results = run_deterministic_mode(vignettes, db_session)

        # 2. Declarative Mode Run
        dec_results = run_declarative_mode(vignettes, db_session, span_repair_enabled=True)

        # 3. Agentic Mode Run
        merged_map, comm_cnt, draft_cnt = build_merged_in_memory_map()
        age_results = run_agentic_mode(vignettes, merged_map, db_session, span_repair_enabled=True)

        summary = {
            "metadata": {
                "execution_timestamp": datetime.now(UTC).isoformat(),
                "benchmark_run": "v54 three-mode full measurement",
                "git_head": "c06ee6b41ad415eaacb89635990f2bd56ba48be1",
                "database_used": "carepolicyguard.db",
                "database_path": db_path,
                "model": "qwen2.5:3b (local Ollama)",
                "budget": "3 calls / 60s per case (agentic mode)",
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
        }

        out_file = Path(args.output)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"v54 Three-mode benchmark measurement complete. Output written to: {out_file}")
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
