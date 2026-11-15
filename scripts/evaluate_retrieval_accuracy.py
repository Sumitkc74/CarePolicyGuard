"""
Retrieval Accuracy Measurement Runner (v55).
Measures top-1, top-3, and top-5 policy retrieval rates across all 84 dev vignettes
under policy-not-given condition, comparing directly against v47 baseline.
Saves detailed benchmark artifacts to app/data/benchmarks/retrieval_v55_measurement.json.
"""

import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# Set up project path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from app.services.policy_shortlist_service import PolicyShortlistService

VIGNETTES_PATH = PROJECT_ROOT / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
OUTPUT_JSON_PATH = PROJECT_ROOT / "app" / "data" / "benchmarks" / "retrieval_v55_measurement.json"

# v47 baseline metrics for comparative analysis
V47_BASELINE = {
    "top_1_count": 75,
    "top_1_rate": 0.8929,
    "top_3_count": 81,
    "top_3_rate": 0.9643,
    "top_5_count": 82,
    "top_5_rate": 0.9762,
    "total_cases": 84
}


def run_retrieval_evaluation():
    start_eval_time = time.perf_counter()
    print(f"[v55-eval] Loading dev vignettes from {VIGNETTES_PATH}...")

    with open(VIGNETTES_PATH, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    total_cases = len(vignettes)
    print(f"[v55-eval] Total dev vignettes: {total_cases}")
    assert total_cases == 84, f"Expected 84 dev vignettes, got {total_cases}"

    case_results = []
    top1_count = 0
    top3_count = 0
    top5_count = 0
    preselected_count = 0
    selection_required_count = 0
    no_governing_count = 0
    latencies = []

    print("[v55-eval] Executing policy shortlist evaluation across 84 cases...")
    for idx, vig in enumerate(vignettes):
        vid = vig.get("vignette_id", f"VIG-{idx:03d}")
        gold_policy = vig["policy_id"]
        ehr_narrative = vig["ehr_narrative"]
        expected_decision = vig.get("expected_decision", "")

        t0 = time.perf_counter()
        shortlist_res = PolicyShortlistService.compute_shortlist(ehr_narrative, top_k=5)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

        shortlist = shortlist_res.get("shortlist", [])
        status = shortlist_res.get("status")
        preselected_id = shortlist_res.get("preselected_policy_id")

        candidate_pids = [c["policy_id"] for c in shortlist]

        # Determine gold rank
        gold_rank = None
        for rank_idx, pid in enumerate(candidate_pids, 1):
            if pid == gold_policy:
                gold_rank = rank_idx
                break

        in_top1 = (gold_rank == 1)
        in_top3 = (gold_rank is not None and gold_rank <= 3)
        in_top5 = (gold_rank is not None and gold_rank <= 5)

        if in_top1:
            top1_count += 1
        if in_top3:
            top3_count += 1
        if in_top5:
            top5_count += 1

        if status == "PRESELECTED":
            preselected_count += 1
        elif status == "SELECTION_REQUIRED":
            selection_required_count += 1
        elif status == "NO_GOVERNING_POLICY":
            no_governing_count += 1

        case_record = {
            "vignette_id": vid,
            "title": vig.get("title", ""),
            "gold_policy": gold_policy,
            "expected_decision": expected_decision,
            "gold_rank": gold_rank if gold_rank is not None else ">5",
            "in_top1": in_top1,
            "in_top3": in_top3,
            "in_top5": in_top5,
            "status": status,
            "preselected_policy_id": preselected_id,
            "retrieved_candidates": [
                {
                    "rank": c["rank"],
                    "policy_id": c["policy_id"],
                    "policy_title": c.get("policy_title", ""),
                    "reranked_score": c.get("reranked_score", 0.0),
                    "coverage_ratio": c.get("coverage_ratio", 0.0)
                }
                for c in shortlist
            ],
            "latency_ms": round(dt_ms, 2)
        }
        case_results.append(case_record)

    top1_rate = top1_count / total_cases
    top3_rate = top3_count / total_cases
    top5_rate = top5_count / total_cases

    lat_p50 = float(np.percentile(latencies, 50))
    lat_p90 = float(np.percentile(latencies, 90))
    lat_p95 = float(np.percentile(latencies, 95))

    # Identify vocabulary-mismatch and notable test cases
    vocab_mismatch_case = next((c for c in case_results if "WOUND-VAC-NEG" in c["vignette_id"]), None)

    summary = {
        "benchmark_session": "v55",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": total_cases,
        "metrics": {
            "top_1_count": top1_count,
            "top_1_rate": round(top1_rate, 4),
            "top_3_count": top3_count,
            "top_3_rate": round(top3_rate, 4),
            "top_5_count": top5_count,
            "top_5_rate": round(top5_rate, 4),
            "preselected_count": preselected_count,
            "preselected_rate": round(preselected_count / total_cases, 4),
            "selection_required_count": selection_required_count,
            "no_governing_count": no_governing_count,
            "latency_ms_p50": round(lat_p50, 2),
            "latency_ms_p90": round(lat_p90, 2),
            "latency_ms_p95": round(lat_p95, 2)
        },
        "comparison_v47_baseline": {
            "top_1_delta": top1_count - V47_BASELINE["top_1_count"],
            "top_3_delta": top3_count - V47_BASELINE["top_3_count"],
            "top_5_delta": top5_count - V47_BASELINE["top_5_count"],
            "v47_top_1_rate": V47_BASELINE["top_1_rate"],
            "v47_top_3_rate": V47_BASELINE["top_3_rate"],
            "v47_top_5_rate": V47_BASELINE["top_5_rate"]
        },
        "notable_cases": {
            "DEV_LCD_WOUND_VAC_NEG": vocab_mismatch_case
        },
        "cases": case_results
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "="*60)
    print("           v55 RETRIEVAL ACCURACY EVALUATION RESULTS")
    print("="*60)
    print(f"Total Cases:     {total_cases}")
    print(f"Top-1 Accuracy:  {top1_count}/{total_cases} ({top1_rate*100:.1f}%) [v47: {V47_BASELINE['top_1_count']}/84 ({V47_BASELINE['top_1_rate']*100:.1f}%)] Delta: {top1_count - V47_BASELINE['top_1_count']:+d}")
    print(f"Top-3 Accuracy:  {top3_count}/{total_cases} ({top3_rate*100:.1f}%) [v47: {V47_BASELINE['top_3_count']}/84 ({V47_BASELINE['top_3_rate']*100:.1f}%)] Delta: {top3_count - V47_BASELINE['top_3_count']:+d}")
    print(f"Top-5 Accuracy:  {top5_count}/{total_cases} ({top5_rate*100:.1f}%) [v47: {V47_BASELINE['top_5_count']}/84 ({V47_BASELINE['top_5_rate']*100:.1f}%)] Delta: {top5_count - V47_BASELINE['top_5_count']:+d}")
    print(f"Pre-selected:    {preselected_count}/{total_cases} ({preselected_count/total_cases*100:.1f}%)")
    print(f"Latency:         p50={lat_p50:.1f}ms, p90={lat_p90:.1f}ms, p95={lat_p95:.1f}ms")
    if vocab_mismatch_case:
        print(f"DEV-LCD-WOUND-VAC-NEG: Gold Rank={vocab_mismatch_case['gold_rank']}, Status={vocab_mismatch_case['status']}")
    print(f"Saved results to {OUTPUT_JSON_PATH}")
    print("="*60 + "\n")

    return summary


if __name__ == "__main__":
    run_retrieval_evaluation()
