"""
Runs the 3-case smoke test and the 9 unresolved synonymy cases in execution_mode="agentic",
and saves the complete board transcripts and case metadata to:
app/data/benchmarks/agentic_smoke_transcripts_v51_fix.json

This provides committed, reproducible evidence of PLAN, JUDGMENT, counter-reading,
DEFENSE / CONCEDE deliberation, and routing counters.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from app.agents.pipeline import MultiAgentVerificationPipeline

THREE_SMOKE_CASES = [
    "DEV-LCD-IMRT-APP",
    "DEV-LCD-KYPHO-APP",
    "DEV-LCD-ACDF-APP",
]

NINE_SYNONYMY_CASES = [
    "DEV-LCD-KYPHO-APP",
    "DEV-LCD-MRI-BRAIN-APP",
    "DEV-LCD-MRI-LUMBAR-APP",
    "DEV-LCD-PAD-ATHERO-APP",
    "DEV-LCD-POWER-WC-APP",
    "DEV-NCD-CCTA-APP",
    "DEV-NCD-PACEMAKER-APP",
    "DEV-NCD-PET-ONC-APP",
    "DEV-NCD-SGD-APP",
]


def run_case(pipeline: MultiAgentVerificationPipeline, vignette: dict) -> dict:
    cid = vignette["vignette_id"]
    ehr = vignette["ehr_narrative"]
    policy_id = vignette.get("target_policy_id") or vignette.get("policy_id")

    adj = pipeline.adjudicate_sync(
        patient_id=f"PT-{cid}",
        ehr_narrative=ehr,
        policy_id=policy_id,
        execution_mode="agentic",
        save_record=False,
    )

    board_msgs = adj.message_board or []
    msg_count = len(board_msgs)

    # Determine message types present
    has_plan = any(m.get("message_type") == "PLAN" for m in board_msgs)
    has_judgment = any(m.get("message_type") == "JUDGMENT" for m in board_msgs)
    has_counter = any(
        m.get("message_type") == "CHALLENGE" and m.get("metadata", {}).get("adversarial_counter_reading") is True
        for m in board_msgs
    )
    has_defend = any(m.get("message_type") == "DEFENSE" for m in board_msgs)
    has_concede = any(m.get("message_type") == "CONCEDE" for m in board_msgs)

    turns = sum(1 for m in board_msgs if m.get("agent", "").startswith("Agent 2") or m.get("agent", "").startswith("Agent 3"))
    judge_calls = sum(1 for m in board_msgs if m.get("message_type") in ("JUDGMENT", "VERDICT"))

    routing = adj.agentic_audit_trail.get("judge_routing", {})

    return {
        "case_id": cid,
        "policy_id": adj.policy_id,
        "decision": adj.adjudication_decision.value,
        "message_count": msg_count,
        "turns_taken": turns,
        "judge_calls": judge_calls,
        "has_plan": has_plan,
        "has_judgment": has_judgment,
        "has_counter_reading": has_counter,
        "has_defend": has_defend,
        "has_concede": has_concede,
        "judge_routing": routing,
        "board_records": board_msgs,
        "transcript": adj.agentic_audit_trail.get("message_board_transcript", ""),
    }


def main() -> None:
    vignettes_file = repo_root / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        all_vignettes = json.load(f)

    vignette_map = {v["vignette_id"]: v for v in all_vignettes}

    pipeline = MultiAgentVerificationPipeline()

    print("Running 3-case smoke run...")
    three_case_runs = []
    for cid in THREE_SMOKE_CASES:
        vig = vignette_map[cid]
        res = run_case(pipeline, vig)
        three_case_runs.append(res)
        print(f"  {cid}: decision={res['decision']}, msgs={res['message_count']}, turns={res['turns_taken']}")

    print("\nRunning 9 unresolved synonymy cases smoke run...")
    nine_case_runs = []
    for cid in NINE_SYNONYMY_CASES:
        vig = vignette_map[cid]
        res = run_case(pipeline, vig)
        nine_case_runs.append(res)
        print(f"  {cid}: decision={res['decision']}, msgs={res['message_count']}, turns={res['turns_taken']}")

    out_file = repo_root / "app" / "data" / "benchmarks" / "agentic_smoke_transcripts_v51_fix.json"
    payload = {
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "description": "Committed board transcripts and routing metadata for v51-fix smoke check",
            "model": "qwen2.5:3b (local Ollama)",
            "budget": "3 calls / 30s per case",
            "execution_mode": "agentic",
        },
        "three_case_smoke": three_case_runs,
        "nine_case_synonymy_smoke": nine_case_runs,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\nSaved smoke transcripts to: {out_file}")


if __name__ == "__main__":
    main()
