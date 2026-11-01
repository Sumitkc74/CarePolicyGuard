import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from typing import Dict, Any, List
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.core.cache import policy_cache

def run_heldout_evaluation():
    base_dir = Path(__file__).resolve().parent
    vignettes_path = base_dir / "heldout_vignettes.json"
    
    with open(vignettes_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    vignettes = data.get("vignettes", [])
    modes = ["deterministic", "state_machine", "declarative"]
    
    evaluation_run: Dict[str, Any] = {
        "metadata": {
            "set_name": data.get("set_name", "CarePolicyGuard Held-Out Vignette Set v1"),
            "status": "UNSEALED - Evaluated once across deterministic, state_machine, and declarative modes",
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_vignettes": len(vignettes),
            "gold_distribution": data.get("decision_counts", {}),
            "created_by": data.get("created_by", ""),
            "field_notes": data.get("field_notes", "")
        },
        "mode_summaries": {},
        "vignette_details": {}
    }
    
    print(f"Loaded {len(vignettes)} held-out vignettes from {vignettes_path.name}")
    print("=" * 80)
    
    for mode in modes:
        print(f"\nEvaluating mode: {mode.upper()}...")
        policy_cache.clear()
        pipeline = MultiAgentVerificationPipeline(db=None)
        
        mode_results: List[Dict[str, Any]] = []
        latencies: List[float] = []
        
        for idx, v in enumerate(vignettes, 1):
            t0 = time.perf_counter()
            res = pipeline.adjudicate_sync(
                patient_id=f"PT-HELD-{v['id']}",
                policy_id=v["policy_id"],
                ehr_narrative=v["ehr"],
                execution_mode=mode,
                save_record=False
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat_ms)
            
            pred_decision = res.adjudication_decision.value
            pred_abstain = res.abstention_status
            gold_decision = v["gold_decision"]
            gold_abstain = v.get("gold_abstain", False)
            
            is_correct = (pred_decision == gold_decision)
            is_false_approval = (pred_decision == "APPROVED" and gold_decision != "APPROVED")
            
            rationale_summary = res.abstention_reason or "; ".join(
                f"{c.criterion_code}: {c.clinical_rationale}" for c in res.criterion_assessments if c.clinical_rationale
            )
            
            item_detail = {
                "id": v["id"],
                "name": v["name"],
                "policy_id": v["policy_id"],
                "domain": v.get("domain", ""),
                "case_type": v.get("case_type", ""),
                "gold_decision": gold_decision,
                "gold_abstain": gold_abstain,
                "predicted_decision": pred_decision,
                "predicted_abstain": pred_abstain,
                "is_correct": is_correct,
                "is_false_approval": is_false_approval,
                "raw_confidence": res.raw_aggregate_confidence,
                "calibrated_confidence": res.calibrated_aggregate_confidence,
                "clinical_rationale": rationale_summary,
                "latency_ms": round(lat_ms, 2)
            }
            mode_results.append(item_detail)
            
            status_symbol = "MATCH" if is_correct else "MISMATCH"
            fa_flag = " [FALSE APPROVAL!]" if is_false_approval else ""
            print(f"  [{v['id']}] {status_symbol} | Pred: {pred_decision:<18} | Gold: {gold_decision:<18}{fa_flag}")

        total_cases = len(vignettes)
        correct_count = sum(1 for r in mode_results if r["is_correct"])
        false_approvals_count = sum(1 for r in mode_results if r["is_false_approval"])
        abstentions_count = sum(1 for r in mode_results if r["predicted_decision"] == "DEFERRED_TO_HUMAN")
        
        mode_summary = {
            "total_cases": total_cases,
            "correct_count": correct_count,
            "accuracy": round(correct_count / total_cases, 4),
            "false_approvals_count": false_approvals_count,
            "false_approval_rate": round(false_approvals_count / total_cases, 4),
            "abstentions_count": abstentions_count,
            "abstention_rate": round(abstentions_count / total_cases, 4),
            "mean_latency_ms": round(sum(latencies) / len(latencies), 2),
            "false_approval_cases": [r["id"] for r in mode_results if r["is_false_approval"]],
            "mismatched_cases": [
                {
                    "id": r["id"],
                    "policy_id": r["policy_id"],
                    "case_type": r["case_type"],
                    "gold": r["gold_decision"],
                    "predicted": r["predicted_decision"],
                    "is_false_approval": r["is_false_approval"],
                    "rationale": r["clinical_rationale"]
                }
                for r in mode_results if not r["is_correct"]
            ]
        }
        
        evaluation_run["mode_summaries"][mode] = mode_summary
        evaluation_run["vignette_details"][mode] = mode_results
        
        print(f"  -> Accuracy: {mode_summary['accuracy'] * 100:.1f}% ({correct_count}/{total_cases})")
        print(f"  -> False Approvals: {false_approvals_count} ({mode_summary['false_approval_rate'] * 100:.1f}%)")

    # Save results json
    results_path = base_dir / "heldout_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(evaluation_run, f, indent=2)
    print(f"\nSaved raw results to: {results_path}")
    
    # Save markdown report
    md_path = base_dir / "HELD_OUT_EVALUATION_REPORT.md"
    generate_markdown_report(evaluation_run, md_path)
    print(f"Saved markdown report to: {md_path}")
    
    return evaluation_run

def generate_markdown_report(run_data: Dict[str, Any], output_path: Path):
    meta = run_data["metadata"]
    summaries = run_data["mode_summaries"]
    details = run_data["vignette_details"]
    
    md_lines = [
        f"# CarePolicyGuard Development-Set (v1) Diagnostic Evaluation Report",
        f"",
        f"> [!IMPORTANT]",
        f"> **Development-Set Status**: This set (v1) is an unsealed development dataset used for regression testing and failure diagnosis.",
        f"> Diagnostic numbers reported here are internal benchmarks and must not be cited as held-out generalization claims.",
        f"> Held-out evaluation is strictly reserved for the sealed v2 dataset pending clinician sign-off.",
        f"",
        f"**Dataset**: {meta['set_name']} (Development Diagnostic Set)  ",
        f"**Execution Timestamp**: {meta['evaluation_timestamp']}  ",
        f"**Total Vignettes**: {meta['total_vignettes']} (Gold: {meta['gold_distribution']})  ",
        f"**Status**: UNSEALED DEVELOPMENT SET  ",
        f"",
        f"## 1. Summary Performance by Execution Mode",
        f"",
        f"| Execution Mode | Accuracy | Correct / Total | False Approvals | False Approval Rate | Abstentions | Mean Latency |",
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for mode, s in summaries.items():
        acc_pct = f"{s['accuracy'] * 100:.1f}%"
        fa_pct = f"{s['false_approval_rate'] * 100:.1f}%"
        abs_pct = f"{s['abstention_rate'] * 100:.1f}%"
        lat = f"{s['mean_latency_ms']} ms"
        md_lines.append(
            f"| `{mode}` | **{acc_pct}** | {s['correct_count']} / {s['total_cases']} | **{s['false_approvals_count']}** | **{fa_pct}** | {s['abstentions_count']} ({abs_pct}) | {lat} |"
        )
        
    md_lines.extend([
        f"",
        f"## 2. Granular Vignette Results Across Modes",
        f"",
        f"| ID | Policy ID | Case Type | Gold Decision | Deterministic | State Machine | Declarative |",
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    # Table of each vignette
    det_map = {r["id"]: r for r in details.get("deterministic", [])}
    sm_map = {r["id"]: r for r in details.get("state_machine", [])}
    decl_map = {r["id"]: r for r in details.get("declarative", [])}
    
    for r in details.get("deterministic", []):
        vid = r["id"]
        pid = r["policy_id"]
        ctype = r["case_type"]
        gold = r["gold_decision"]
        
        det_res = det_map.get(vid, {}).get("predicted_decision", "-")
        sm_res = sm_map.get(vid, {}).get("predicted_decision", "-")
        decl_res = decl_map.get(vid, {}).get("predicted_decision", "-")
        
        # Highlight mismatches
        det_str = f"`{det_res}`" if det_res == gold else f"**`{det_res}` (FAIL)**"
        sm_str = f"`{sm_res}`" if sm_res == gold else f"**`{sm_res}` (FAIL)**"
        decl_str = f"`{decl_res}`" if decl_res == gold else f"**`{decl_res}` (FAIL)**"
        
        md_lines.append(f"| {vid} | {pid} | {ctype} | `{gold}` | {det_str} | {sm_str} | {decl_str} |")

    md_lines.extend([
        f"",
        f"## 3. False Approvals and Mismatch Analysis",
        f""
    ])
    
    for mode, s in summaries.items():
        md_lines.append(f"### Mode: `{mode}`")
        if not s["mismatched_cases"]:
            md_lines.append("No mismatches observed. 100% concordance with gold labels.")
        else:
            md_lines.append(f"Total Mismatches: {len(s['mismatched_cases'])} | False Approvals: {s['false_approvals_count']}")
            md_lines.append("")
            for m in s["mismatched_cases"]:
                fa_tag = " **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**" if m["is_false_approval"] else ""
                md_lines.append(f"- **{m['id']}** ({m['policy_id']} - `{m['case_type']}`): Gold = `{m['gold']}`, Predicted = `{m['predicted']}`{fa_tag}")
                md_lines.append(f"  - Rationale: {m['rationale']}")
        md_lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

if __name__ == "__main__":
    run_heldout_evaluation()
