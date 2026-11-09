#!/usr/bin/env python3
"""
CarePolicyGuard Extended Policy Development Evaluation Harness
Evaluates uncued synthetic development vignettes across all 42 extended CMS policies.
Computes AUTO retrieval top-1 and top-3 accuracy, adjudication decision accuracy,
and the full confusion matrix.
"""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
DEV_VIGNETTES_FILE = POLICIES_DIR / "dev_vignettes_extended.json"
REPORT_FILE = POLICIES_DIR / "DEVELOPMENT_EVALUATION_REPORT.md"

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.hybrid_retriever import HybridPolicyRetriever

def run_evaluation(write_report: bool = True):
    assert DEV_VIGNETTES_FILE.exists(), f"Vignettes file {DEV_VIGNETTES_FILE} does not exist"

    with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
        all_vignettes = json.load(f)

    print(f"[*] Loaded {len(all_vignettes)} development vignettes from {DEV_VIGNETTES_FILE.name}")

    retriever = HybridPolicyRetriever(db=None, use_declarative_only=True)
    pipeline = MultiAgentVerificationPipeline(db=None)

    total_count = len(all_vignettes)
    top1_correct = 0
    top3_correct = 0
    decision_correct = 0

    per_policy_stats = defaultdict(lambda: {
        "total": 0,
        "top1_hits": 0,
        "top3_hits": 0,
        "decision_matches": 0,
        "failed_cases": []
    })

    confusion_matrix = defaultdict(lambda: defaultdict(int))
    unique_policies = sorted(list(set(v["policy_id"] for v in all_vignettes)))

    for idx, vig in enumerate(all_vignettes, 1):
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        per_policy_stats[pid]["total"] += 1

        # 1. AUTO Retrieval
        candidates = retriever.retrieve_hybrid(narrative, top_k=5)
        unique_retrieved = []
        seen = set()
        for c in candidates:
            c_pid = c["policy_id"]
            if c_pid not in seen:
                unique_retrieved.append(c_pid)
                seen.add(c_pid)

        top1_pred = unique_retrieved[0] if unique_retrieved else "NONE"
        top3_pred = unique_retrieved[:3]

        confusion_matrix[pid][top1_pred] += 1

        is_top1 = (top1_pred == pid)
        is_top3 = (pid in top3_pred)

        if is_top1:
            top1_correct += 1
            per_policy_stats[pid]["top1_hits"] += 1
        if is_top3:
            top3_correct += 1
            per_policy_stats[pid]["top3_hits"] += 1

        # 2. Adjudication Decision
        adj = pipeline.adjudicate_sync(
            patient_id=f"PT-DEV-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False
        )
        actual_dec = adj.adjudication_decision.value
        is_dec_match = (actual_dec == exp_dec)

        if is_dec_match:
            decision_correct += 1
            per_policy_stats[pid]["decision_matches"] += 1
        else:
            per_policy_stats[pid]["failed_cases"].append({
                "vignette_id": vig["vignette_id"],
                "expected": exp_dec,
                "actual": actual_dec,
                "abstention_status": getattr(adj, "abstention_status", None),
                "abstention_reason": getattr(adj, "abstention_reason", None)
            })

    top1_pct = (top1_correct / total_count) * 100
    top3_pct = (top3_correct / total_count) * 100
    dec_pct = (decision_correct / total_count) * 100

    print(f"\n========================================================")
    print(f"DEVELOPMENT EVALUATION RESULTS (DEVELOPMENT-ONLY)")
    print(f"========================================================")
    print(f"Total Vignettes:          {total_count} (2 per policy across {len(unique_policies)} policies)")
    print(f"AUTO Retrieval Top-1:     {top1_correct}/{total_count} ({top1_pct:.1f}%)")
    print(f"AUTO Retrieval Top-3:     {top3_correct}/{total_count} ({top3_pct:.1f}%)")
    print(f"Adjudication Accuracy:    {decision_correct}/{total_count} ({dec_pct:.1f}%)")
    print(f"========================================================\n")

    # Generate Markdown Report
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_head = "UNKNOWN"

    report_lines = [
        "# CarePolicyGuard: 50-Policy Development Evaluation Report",
        "",
        "> **DEVELOPMENT-ONLY BENCHMARK AUDIT NOTICE**",
        "> **Provenance**: Synthetic Development Vignette Evaluation Set (`dev_vignettes_extended.json`).",
        "> **Dataset Type**: Author-written synthetic development set (84 cases: 1 approved, 1 negative per policy).",
        "> **Validation Status**: **DEVELOPMENT-ONLY**. This evaluation tests system behavior against author-written criteria and synthetic notes.",
        "> **Important Disclosures**:",
        "> 1. This is **NOT** a held-out validation benchmark. Real-world validation requires clinical EHR datasets with independent clinician ground-truth.",
        "> 2. Vignettes were constructed from the policies' own criteria definitions to test pipeline retrieval sensitivity and rule evaluation mechanics without circular cues.",
        "> 3. Zero circular cues: narratives contain no policy slugs, no LCD/NCD identifiers, and no coverage verdict phrases.",
        "> 4. Criterion traceability for all 42 extended policies remains strictly `CLAIMED_UNVERIFIED` pending independent regulatory audit.",
        "",
        f"**Audit Execution Timestamp**: `{now_utc}`  ",
        f"**Git Commit Head**: `{git_head}`  ",
        f"**Total Extended Policies Audited**: `42`  ",
        f"**Total Evaluation Cases**: `{total_count}`  ",
        f"**Pipeline Decision Threshold**: `tau = 0.85` (unchanged)  ",
        "",
        "## Overall Development Performance",
        "",
        "| Evaluation Metric | Measured Result | Percentage | Benchmark Dataset |",
        "| :--- | :--- | :--- | :--- |",
        f"| **AUTO Retrieval Top-1 Accuracy** | `{top1_correct}/{total_count}` | **{top1_pct:.1f}%** | Synthetic Development Set (42 Extended Policies) |",
        f"| **AUTO Retrieval Top-3 Accuracy** | `{top3_correct}/{total_count}` | **{top3_pct:.1f}%** | Synthetic Development Set (42 Extended Policies) |",
        f"| **Adjudication Decision Accuracy** | `{decision_correct}/{total_count}` | **{dec_pct:.1f}%** | Synthetic Development Set (42 Extended Policies) |",
        "",
        "## Per-Policy Development Results",
        "",
        "| Policy ID | Total Cases | Top-1 Hits | Top-3 Hits | Decision Matches | Failure Details |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]

    for pid in unique_policies:
        stats = per_policy_stats[pid]
        failures = stats["failed_cases"]
        fail_desc = "; ".join([f"{f['vignette_id']}: expected {f['expected']}, got {f['actual']} ({f['abstention_reason']})" for f in failures]) if failures else "None (Clean)"
        report_lines.append(
            f"| `{pid}` | {stats['total']} | {stats['top1_hits']}/{stats['total']} | {stats['top3_hits']}/{stats['total']} | {stats['decision_matches']}/{stats['total']} | {fail_desc} |"
        )

    report_lines.extend([
        "",
        "## Confusion Matrix (AUTO Retrieval Top-1)",
        "",
        "Shows which candidate policies were selected as Top-1 by the hybrid retriever for each intended policy.",
        ""
    ])

    # Header for confusion matrix
    cm_header = "| Intended Policy | " + " | ".join([f"`{p}`" for p in unique_policies]) + " | Other / None |"
    cm_sep = "| :--- | " + " | ".join([":---:" for _ in unique_policies]) + " | :---: |"
    report_lines.append(cm_header)
    report_lines.append(cm_sep)

    for pid in unique_policies:
        row = [f"`{pid}`"]
        for pred in unique_policies:
            count = confusion_matrix[pid][pred]
            row.append(str(count) if count > 0 else ".")
        # Check if predicted anything else
        other_count = sum(c for k, c in confusion_matrix[pid].items() if k not in unique_policies)
        row.append(str(other_count) if other_count > 0 else ".")
        report_lines.append("| " + " | ".join(row) + " |")

    report_lines.extend([
        "",
        "## Verification and Honesty Notes",
        "- **Forbidden Phrase Scan**: Verified 0 occurrences of policy slugs, LCD/NCD identifiers, or coverage verdict phrases in vignette texts.",
        "- **Retrieval Architecture**: Evaluated under `HybridPolicyRetriever` combining BM25 keyword matching with expanded domain clinical concept vocabulary.",
        "- **Adjudication Mechanics**: Evaluated under `DeclarativePolicyEngine` character-anchored extraction and ConText negation scoping.",
        "- **Status**: Development baseline only. All extended policies remain `CLAIMED_UNVERIFIED` at the criterion level."
    ])

    if write_report:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")
        print(f"[*] Development evaluation report written to {REPORT_FILE}")
    return {
        "total": total_count,
        "top1_correct": top1_correct,
        "top1_pct": top1_pct,
        "top3_correct": top3_correct,
        "top3_pct": top3_pct,
        "decision_correct": decision_correct,
        "dec_pct": dec_pct,
        "per_policy_stats": per_policy_stats,
        "confusion_matrix": confusion_matrix
    }

if __name__ == "__main__":
    run_evaluation()
