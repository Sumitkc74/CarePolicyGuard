"""
Verification script: Recomputes every headline aggregate from per-case records alone
for both Arm A and Arm B from the comparison raw JSON.

Usage:
    python scripts/recompute_agentic_v36_comparison.py [path_to_raw_json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

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


def recompute_arm(arm_data: dict, arm_label: str) -> dict:
    cases = arm_data.get("cases", [])
    total_cases = len(cases)

    concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    synonymy_resolved = []
    total_calls = 0
    gate_a_failures = 0
    gate_b_rejections = 0
    gate_c_map_rejections = 0
    gate_c_vetoes = 0
    claims_accepted_gate_chain = 0
    total_messages = 0
    challenges_raised = 0
    concessions = 0
    unresolved_disagreements = 0

    for c in cases:
        exp = c["expected_decision"]
        act = c["actual_decision"]
        vid = c["vignette_id"]

        is_conc = (act == exp)
        if is_conc:
            concordant += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                synonymy_resolved.append(vid)
        else:
            if exp == "DENIED" and act == "APPROVED":
                false_approvals += 1
            elif exp == "APPROVED" and act == "DENIED":
                false_denials += 1

        if act == "DEFERRED_TO_HUMAN":
            deferrals += 1

        total_calls += c.get("calls", 0)
        gate_a_failures += c.get("gate_a_failures", 0)
        gate_b_rejections += c.get("gate_b_rejections", 0)
        gate_c_map_rejections += c.get("gate_c_map_rejections", 0)
        gate_c_vetoes += c.get("gate_c_vetoes", 0)
        claims_accepted_gate_chain += c.get("claims_accepted_gate_chain_count", 0)

        total_messages += c.get("message_count", 0)
        challenges_raised += c.get("challenges_raised", 0)
        concessions += c.get("concessions", 0)
        unresolved_disagreements += c.get("unresolved_disagreements", 0)

    recomputed = {
        "total_cases": total_cases,
        "concordant_decisions": concordant,
        "accuracy_pct": round(concordant / total_cases * 100.0, 1) if total_cases > 0 else 0.0,
        "false_approvals": false_approvals,
        "false_denials": false_denials,
        "deferrals": deferrals,
        "synonymy_resolved_count": len(synonymy_resolved),
        "synonymy_resolved_cases": synonymy_resolved,
        "calls": total_calls,
        "gate_a_failures": gate_a_failures,
        "gate_b_rejections": gate_b_rejections,
        "gate_c_map_rejections": gate_c_map_rejections,
        "gate_c_vetoes": gate_c_vetoes,
        "claims_accepted": claims_accepted_gate_chain,
    }

    if "conversation_metrics" in arm_data:
        recomputed["conversation_metrics"] = {
            "total_messages": total_messages,
            "mean_messages_per_case": round(total_messages / total_cases, 2) if total_cases > 0 else 0.0,
            "challenges_raised_by_agent_3": challenges_raised,
            "challenges_answered": concessions,
            "concessions_by_agent_2": concessions,
            "assessments_changed_by_debate": concessions,
            "deferrals_from_unresolved_disagreement": unresolved_disagreements,
        }

    return recomputed


def compare_and_report(raw_path: Path) -> bool:
    print("\n===========================================================================")
    print(f"RECOMPUTING AGGREGATES FROM PER-CASE RECORDS: {raw_path.name}")
    print("===========================================================================")

    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_matched = True

    for arm_key, arm_title in [("arm_a", "Arm A (Declarative)"), ("arm_b", "Arm B (Agentic)")]:
        reported = data[arm_key]
        recomputed = recompute_arm(reported, arm_title)

        print(f"\n--- {arm_title} ---")
        metrics_to_check = [
            ("total_cases", "Total cases"),
            ("concordant_decisions", "Concordant decisions"),
            ("accuracy_pct", "Accuracy pct"),
            ("synonymy_resolved_count", "Synonymy resolved count"),
            ("false_approvals", "False approvals"),
            ("false_denials", "False denials"),
            ("deferrals", "Deferrals"),
            ("calls", "Total calls"),
            ("gate_a_failures", "Gate A failures"),
            ("gate_b_rejections", "Gate B rejections"),
            ("gate_c_map_rejections", "Gate C map rejections"),
            ("gate_c_vetoes", "Gate C vetoes"),
            ("claims_accepted", "Claims accepted (gate chain)"),
        ]

        for m_key, m_label in metrics_to_check:
            rep_val = reported.get(m_key)
            rec_val = recomputed.get(m_key)
            match = (rep_val == rec_val)
            if not match:
                all_matched = False
                status = f"FAIL (reported={rep_val}, recomputed={rec_val})"
            else:
                status = f"OK ({rec_val})"
            print(f"  {m_label:<32}: {status}")

        if "conversation_metrics" in reported:
            print("  Conversation Metrics:")
            rep_conv = reported["conversation_metrics"]
            rec_conv = recomputed["conversation_metrics"]
            conv_metrics = [
                ("total_messages", "Total messages"),
                ("mean_messages_per_case", "Mean msgs/case"),
                ("challenges_raised_by_agent_3", "Challenges raised"),
                ("challenges_answered", "Challenges answered"),
                ("concessions_by_agent_2", "Concessions by Agent 2"),
                ("assessments_changed_by_debate", "Assessments changed"),
                ("deferrals_from_unresolved_disagreement", "Unresolved disagreement deferrals"),
            ]
            for c_key, c_label in conv_metrics:
                rep_c = rep_conv.get(c_key)
                rec_c = rec_conv.get(c_key)
                c_match = (rep_c == rec_c)
                if not c_match:
                    all_matched = False
                    c_status = f"FAIL (reported={rep_c}, recomputed={rec_c})"
                else:
                    c_status = f"OK ({rec_c})"
                print(f"    {c_label:<30}: {c_status}")

    print("\n" + "=" * 75)
    if all_matched:
        print("ALL REPORTED AGGREGATES PERFECTLY MATCH RECOMPUTATION FROM PER-CASE RECORDS!")
    else:
        print("MISMATCH DETECTED BETWEEN REPORTED AGGREGATES AND PER-CASE RECORDS!")
    print("=" * 75)
    return all_matched


def main():
    parser = argparse.ArgumentParser(description="Recompute comparison aggregates from per-case records")
    parser.add_argument(
        "json_path",
        nargs="?",
        default=str(ROOT_DIR / "app" / "data" / "benchmarks" / "agentic_v36_comparison_raw_span_repair_on.json"),
        help="Path to comparison raw JSON"
    )
    args = parser.parse_args()

    raw_path = Path(args.json_path)
    if not raw_path.exists():
        print(f"Error: file not found at {raw_path}", file=sys.stderr)
        sys.exit(1)

    ok = compare_and_report(raw_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
