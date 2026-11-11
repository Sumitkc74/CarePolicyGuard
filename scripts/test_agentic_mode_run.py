"""
Execution verification script for execution_mode="agentic" (Deliverable 1).
Runs 3 dev vignettes through the full communicating multi-agent pipeline.
Demonstrates end-to-end operation, shared message board transcript,
message counts, turn tracking, and final adjudication decision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from app.agents.pipeline import MultiAgentVerificationPipeline


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    vignettes_file = repo_root / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"

    with open(vignettes_file, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    target_case_ids = ["DEV-LCD-IMRT-APP", "DEV-LCD-KYPHO-APP", "DEV-LCD-ACDF-APP"]
    selected_vignettes = [v for v in vignettes if v.get("vignette_id") in target_case_ids]

    # Preserve order of target_case_ids
    selected_vignettes.sort(key=lambda v: target_case_ids.index(v.get("vignette_id")))

    print(f"Loaded {len(selected_vignettes)} test cases for agentic execution verification.\n")

    pipeline = MultiAgentVerificationPipeline()
    results = []

    for vig in selected_vignettes:
        cid = vig["vignette_id"]
        ehr = vig["ehr_narrative"]
        policy_id = vig.get("target_policy_id") or vig.get("policy_id")

        print(f"--- Running {cid} in execution_mode='agentic' ---")
        adj = pipeline.adjudicate_sync(
            patient_id=f"PT-{cid}",
            ehr_narrative=ehr,
            policy_id=policy_id,
            execution_mode="agentic",
            save_record=False,
        )

        board_msgs = adj.message_board or []
        msg_count = len(board_msgs)

        # Count turns and judge calls from board
        judge_calls = sum(1 for m in board_msgs if m.get("message_type") == "VERDICT")
        turns = sum(1 for m in board_msgs if m.get("agent", "").startswith("Agent 2") or m.get("agent", "").startswith("Agent 3"))

        results.append({
            "case_id": cid,
            "policy_id": adj.policy_id,
            "decision": adj.adjudication_decision.value,
            "message_count": msg_count,
            "turns_taken": turns,
            "judge_calls": judge_calls,
            "transcript": adj.agentic_audit_trail.get("message_board_transcript", ""),
        })
        print(f"Completed {cid}: decision={adj.adjudication_decision.value}, messages={msg_count}, turns={turns}, judge_calls={judge_calls}\n")

    # Summary table
    print("=" * 80)
    print("AGENTIC EXECUTION SUMMARY (3 DEV CASES)")
    print("=" * 80)
    print(f"{'Case ID':<20} | {'Decision':<12} | {'Messages':<10} | {'Turns':<8} | {'Judge Calls':<12}")
    print("-" * 80)
    for r in results:
        print(f"{r['case_id']:<20} | {r['decision']:<12} | {r['message_count']:<10} | {r['turns_taken']:<8} | {r['judge_calls']:<12}")
    print("=" * 80)

    # Print full transcript for DEV-LCD-IMRT-APP
    imrt_res = next(r for r in results if r["case_id"] == "DEV-LCD-IMRT-APP")
    print("\n" + "=" * 80)
    print("FULL CASE MESSAGE BOARD TRANSCRIPT: DEV-LCD-IMRT-APP")
    print("=" * 80)
    print(imrt_res["transcript"])
    print("=" * 80)


if __name__ == "__main__":
    main()
