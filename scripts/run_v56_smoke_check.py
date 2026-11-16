"""
Runner script for Task 8: Smoke Check on 12 Cases (v56).

Evaluates:
- 9 unresolved synonymy cases:
  DEV-LCD-KYPHO-APP, DEV-LCD-MRI-BRAIN-APP, DEV-LCD-MRI-LUMBAR-APP,
  DEV-LCD-PAD-ATHERO-APP, DEV-LCD-POWER-WC-APP, DEV-NCD-CCTA-APP,
  DEV-NCD-PACEMAKER-APP, DEV-NCD-PET-ONC-APP, DEV-NCD-SGD-APP
- 3 additional selected cases:
  DEV-LCD-WOUND-VAC-NEG, DEV-NCD-SPACER-APP (DEV-LCD-IMRT-APP), DEV-LCD-CATARACT-APP (DEV-NCD-CATARACT-APP)

Under execution_mode="agentic" using local Ollama (qwen2.5:3b).
Extracts and verifies:
(a) Tool-choice diversity across cases
(b) At least 1 recorded mind-change
(c) At least 1 debate/advocacy outcome changing criterion status
(d) Per-criterion tool-attribution table

Saves output to: app/data/benchmarks/v56_smoke_transcripts.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from app.agents.pipeline import MultiAgentVerificationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("smoke_v56")

ALIASES = {
    "DEV-LCD-CATARACT-APP": "DEV-NCD-CATARACT-APP",
    "DEV-NCD-SPACER-APP": "DEV-LCD-IMRT-APP",
}

TARGET_CASES = [
    # 9 unresolved synonymy cases
    "DEV-LCD-KYPHO-APP",
    "DEV-LCD-MRI-BRAIN-APP",
    "DEV-LCD-MRI-LUMBAR-APP",
    "DEV-LCD-PAD-ATHERO-APP",
    "DEV-LCD-POWER-WC-APP",
    "DEV-NCD-CCTA-APP",
    "DEV-NCD-PACEMAKER-APP",
    "DEV-NCD-PET-ONC-APP",
    "DEV-NCD-SGD-APP",
    # 3 additional selected cases
    "DEV-LCD-WOUND-VAC-NEG",
    "DEV-NCD-SPACER-APP",
    "DEV-LCD-CATARACT-APP",
]


def run_case(pipeline: MultiAgentVerificationPipeline, vignette: dict, requested_id: str) -> dict:
    cid = vignette["vignette_id"]
    ehr = vignette["ehr_narrative"]
    policy_id = vignette.get("target_policy_id") or vignette.get("policy_id")

    logger.info("Executing %s (resolved from %s, policy: %s)...", cid, requested_id, policy_id)
    adj = pipeline.adjudicate_sync(
        patient_id=f"PT-{cid}",
        ehr_narrative=ehr,
        policy_id=policy_id,
        execution_mode="agentic",
        save_record=False,
    )

    board_msgs = adj.message_board or []
    audit = adj.agentic_audit_trail or {}

    tool_attribution = audit.get("tool_attribution", {})
    mind_changes = audit.get("mind_changes", [])
    tool_logs = audit.get("tool_logs", [])

    # Check for debate / advocacy status changes
    status_changes = [
        mc for mc in mind_changes
        if mc.get("from_status") != mc.get("to_status")
    ]

    return {
        "requested_case_id": requested_id,
        "vignette_id": cid,
        "policy_id": policy_id,
        "expected_decision": vignette.get("expected_decision", "UNKNOWN"),
        "actual_decision": adj.adjudication_decision.value,
        "is_concordant": (adj.adjudication_decision.value == vignette.get("expected_decision")),
        "abstention_status": adj.abstention_status,
        "sufficiency_score": adj.sufficiency_score,
        "execution_time_ms": adj.execution_time_ms,
        "tool_attribution": tool_attribution,
        "mind_changes": mind_changes,
        "status_changes": status_changes,
        "tool_logs_count": len(tool_logs),
        "message_count": len(board_msgs),
        "board_records": board_msgs,
        "transcript": audit.get("message_board_transcript", ""),
        "judge_routing": audit.get("judge_routing", {}),
    }


def build_merged_in_memory_map() -> tuple[Any, int, int]:
    import app.core.concept_map as cm_mod
    from app.core.concept_map import ConceptDefinition, ConceptMap, ConceptSource

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

    cm_mod._GLOBAL_CONCEPT_MAP = merged_map
    logger.info("Merged ConceptMap assembled: %d committed + %d drafts = %d total", committed_count, added_drafts, merged_map.total_concepts)
    return merged_map, committed_count, added_drafts


def main() -> None:
    build_merged_in_memory_map()
    vignettes_file = repo_root / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        all_vignettes = json.load(f)

    vig_map = {v["vignette_id"]: v for v in all_vignettes}

    pipeline = MultiAgentVerificationPipeline(db=None)

    case_results = []
    all_mind_changes = []
    all_status_changes = []
    tool_usage_counts: dict[str, int] = {}
    attribution_table: dict[str, dict[str, str]] = {}

    for req_id in TARGET_CASES:
        resolved_id = ALIASES.get(req_id, req_id)
        if resolved_id not in vig_map:
            logger.error("Vignette %s (resolved: %s) not found in dev set!", req_id, resolved_id)
            continue

        vignette = vig_map[resolved_id]
        res = run_case(pipeline, vignette, req_id)
        case_results.append(res)

        # Aggregate tool attribution
        attr = res.get("tool_attribution", {})
        attribution_table[req_id] = attr
        for tool in attr.values():
            tool_usage_counts[tool] = tool_usage_counts.get(tool, 0) + 1

        # Aggregate mind changes and status changes
        all_mind_changes.extend(res.get("mind_changes", []))
        all_status_changes.extend(res.get("status_changes", []))

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_cases_run": len(case_results),
        "cases_concordant": sum(1 for c in case_results if c["is_concordant"]),
        "tool_usage_counts": tool_usage_counts,
        "tool_choice_diversity_count": len(tool_usage_counts),
        "total_mind_changes": len(all_mind_changes),
        "total_status_changes": len(all_status_changes),
        "attribution_table": attribution_table,
        "case_summaries": [
            {
                "case_id": c["requested_case_id"],
                "resolved_id": c["vignette_id"],
                "policy_id": c["policy_id"],
                "expected": c["expected_decision"],
                "actual": c["actual_decision"],
                "concordant": c["is_concordant"],
                "sufficiency": c["sufficiency_score"],
                "mind_changes_count": len(c["mind_changes"]),
                "status_changes_count": len(c["status_changes"]),
                "tool_attribution": c["tool_attribution"],
            }
            for c in case_results
        ],
        "cases": case_results,
    }

    out_file = repo_root / "app" / "data" / "benchmarks" / "v56_smoke_transcripts.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Saved smoke results to %s", out_file)

    # Print summary report
    print("\n" + "=" * 70)
    print("v56 AGENTIC ARCHITECTURAL INVERSION - 12-CASE SMOKE REPORT")
    print("=" * 70)
    print(f"Total Cases Run: {len(case_results)}/12")
    print(f"Concordance: {summary['cases_concordant']}/{len(case_results)}")
    print(f"Tool Choice Diversity ({len(tool_usage_counts)} tools): {tool_usage_counts}")
    print(f"Total Mind Changes: {len(all_mind_changes)}")
    print(f"Total Debate/Advocacy Status Changes: {len(all_status_changes)}")
    print("\nPer-Criterion Tool-Attribution Table:")
    for cid, attr in attribution_table.items():
        print(f"  {cid}:")
        for crit, tool in attr.items():
            print(f"    - {crit}: {tool}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
