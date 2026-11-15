"""
Runner script for Task 4: Smoke Check with Committed Transcripts (v53).
Evaluates:
1. 3-case smoke (IMRT, KYPHO, ACDF)
2. 9 unresolved synonymy cases
3. SBRT + SI-FUSION regression cases
4. 14 false-deferral vignettes
Under execution_mode="agentic" using local Ollama (qwen2.5:3b).
Saves structured board transcripts and routing metadata to:
app/data/benchmarks/agentic_smoke_transcripts_v53.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import app.core.concept_map as cm_mod
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.concept_map import ConceptDefinition, ConceptMap, ConceptSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("smoke_v53")


def build_merged_in_memory_map() -> tuple[ConceptMap, int, int]:
    """Builds the in-memory merged concept map: 12 committed + 119 PASS draft concepts."""
    merged_map = ConceptMap()
    committed_count = merged_map.total_concepts

    draft_file = repo_root / "app" / "data" / "concept_map" / "draft_concept_entries.json"
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


def run_case(pipeline: MultiAgentVerificationPipeline, vignette: dict) -> dict:
    cid = vignette["vignette_id"]
    ehr = vignette["ehr_narrative"]
    policy_id = vignette.get("target_policy_id") or vignette.get("policy_id")

    logger.info("Running %s (policy: %s)...", cid, policy_id)
    adj = pipeline.adjudicate_sync(
        patient_id=f"PT-{cid}",
        ehr_narrative=ehr,
        policy_id=policy_id,
        execution_mode="agentic",
        save_record=False,
    )

    board_msgs = adj.message_board or []
    msg_count = len(board_msgs)

    # Detailed action counts
    has_plan = any(m.get("message_type") == "PLAN" for m in board_msgs)
    has_judgment = any(m.get("message_type") == "JUDGMENT" for m in board_msgs)
    has_counter_reading = any(
        m.get("message_type") == "CHALLENGE" and m.get("metadata", {}).get("adversarial_counter_reading")
        for m in board_msgs
    )
    has_defend = any(m.get("message_type") == "DEFENSE" for m in board_msgs)
    has_advocacy = any(m.get("message_type") == "ADVOCACY" for m in board_msgs)
    has_concede = any(m.get("message_type") == "CONCEDE" for m in board_msgs)
    has_halt = any(m.get("message_type") == "HALT" for m in board_msgs)

    # Advocate rescues: criteria where advocacy was promoted
    advocate_rescues = []
    for m in board_msgs:
        if m.get("message_type") == "DEFENSE" and m.get("metadata", {}).get("advocacy_promoted"):
            advocate_rescues.append({
                "criterion_code": m.get("criterion_code"),
                "quote": m.get("metadata", {}).get("quote", ""),
                "content": m.get("content", "")
            })

    # Defenses attempted (defense against counter-reading)
    defenses_attempted = []
    for m in board_msgs:
        if m.get("message_type") == "DEFENSE" and not m.get("metadata", {}).get("advocacy_promoted") and m.get("metadata", {}).get("objection_type") not in (None, "NONE"):
            defenses_attempted.append({
                "criterion_code": m.get("criterion_code"),
                "objection_type": m.get("metadata", {}).get("objection_type"),
                "quote": m.get("metadata", {}).get("defense_quote", ""),
                "content": m.get("content", "")
            })

    turns = sum(1 for m in board_msgs if m.get("agent", "").startswith("Agent 2") or m.get("agent", "").startswith("Agent 3"))
    judge_calls = adj.llm_proposal_metadata.get("judge_calls_total_case", 0)

    routing = adj.agentic_audit_trail.get("judge_routing", {})

    return {
        "case_id": cid,
        "policy_id": policy_id,
        "expected_decision": vignette.get("expected_decision", "UNKNOWN"),
        "actual_decision": adj.adjudication_decision.value,
        "is_concordant": (adj.adjudication_decision.value == vignette.get("expected_decision")),
        "message_count": msg_count,
        "turns_taken": turns,
        "judge_calls": judge_calls,
        "has_plan": has_plan,
        "has_judgment": has_judgment,
        "has_counter_reading": has_counter_reading,
        "has_advocacy": has_advocacy,
        "has_defend": has_defend,
        "has_concede": has_concede,
        "has_halt": has_halt,
        "advocate_rescues": advocate_rescues,
        "defenses_attempted": defenses_attempted,
        "judge_routing": routing,
        "criterion_assessments": [
            {
                "criterion_code": ca.criterion_code,
                "status": ca.status.value if hasattr(ca.status, "value") else str(ca.status),
                "clinical_rationale": ca.clinical_rationale,
                "verified_spans": [
                    {"text": s.source_text, "start": s.start_char, "end": s.end_char}
                    for s in (ca.verified_spans or [])
                ]
            }
            for ca in (adj.criterion_assessments or [])
        ],
        "board_records": board_msgs,
        "transcript": adj.agentic_audit_trail.get("message_board_transcript", ""),
    }


def main() -> None:
    vignettes_file = repo_root / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        all_vignettes = json.load(f)

    vig_map = {v["vignette_id"]: v for v in all_vignettes}

    three_case_ids = ["DEV-LCD-IMRT-APP", "DEV-LCD-KYPHO-APP", "DEV-LCD-ACDF-APP"]
    synonymy_ids = [
        "DEV-LCD-KYPHO-APP", "DEV-LCD-MRI-BRAIN-APP", "DEV-LCD-MRI-LUMBAR-APP",
        "DEV-LCD-PAD-ATHERO-APP", "DEV-LCD-POWER-WC-APP", "DEV-NCD-CCTA-APP",
        "DEV-NCD-PACEMAKER-APP", "DEV-NCD-PET-ONC-APP", "DEV-NCD-SGD-APP"
    ]
    regression_ids = ["DEV-LCD-SBRT-APP", "DEV-OPD-SI-FUSION-APP"]
    false_deferral_ids = [
        "DEV-LCD-KYPHO-APP", "DEV-LCD-MRI-BRAIN-APP", "DEV-LCD-MRI-LUMBAR-APP",
        "DEV-LCD-PAD-ATHERO-APP", "DEV-LCD-PCI-APP", "DEV-LCD-POWER-WC-APP",
        "DEV-LCD-SBRT-APP", "DEV-NCD-CATARACT-APP", "DEV-NCD-CCTA-APP",
        "DEV-NCD-PACEMAKER-APP", "DEV-NCD-PET-ONC-APP", "DEV-NCD-SCS-APP",
        "DEV-NCD-SGD-APP", "DEV-OPD-SI-FUSION-APP"
    ]

    all_target_ids = sorted(set(three_case_ids + synonymy_ids + regression_ids + false_deferral_ids))
    logger.info("Total unique smoke vignettes to run: %d", len(all_target_ids))

    merged_map, _comm_cnt, _draft_cnt = build_merged_in_memory_map()
    cm_mod._GLOBAL_CONCEPT_MAP = merged_map

    pipeline = MultiAgentVerificationPipeline()

    executed_results = {}
    for vid in all_target_ids:
        v = vig_map[vid]
        executed_results[vid] = run_case(pipeline, v)

    # Compile sections
    three_case_records = [executed_results[vid] for vid in three_case_ids]
    synonymy_records = [executed_results[vid] for vid in synonymy_ids]
    regression_records = [executed_results[vid] for vid in regression_ids]
    false_deferral_records = [executed_results[vid] for vid in false_deferral_ids]

    output_data = {
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "description": "Committed board transcripts, routing metadata, advocacy results, and defense traces for v53 smoke check",
            "model": "qwen2.5:3b (local Ollama)",
            "budget": "3 calls / 60s per case (agentic mode)",
            "execution_mode": "agentic",
            "git_head_parent": "b9a639d90576bdcc48b83e1c6dbbc0e5da6c22f9"
        },
        "three_case_smoke": three_case_records,
        "nine_case_synonymy_smoke": synonymy_records,
        "regression_cases_smoke": regression_records,
        "fourteen_case_false_deferral_smoke": false_deferral_records,
    }

    out_file = repo_root / "app" / "data" / "benchmarks" / "agentic_smoke_transcripts_v53.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    logger.info("Transcripts committed to %s", out_file)


if __name__ == "__main__":
    main()
