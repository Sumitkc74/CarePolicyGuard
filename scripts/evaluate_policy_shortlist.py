"""Evaluates the Medicare Policy Shortlist service across the 84 dev vignettes.

Measures:
1. Gold policy in Top-1, Top-3, Top-5 rates.
2. Pre-selected rate vs Clinician-pick rate.
3. Decision accuracy on pre-selected subset (pre-selected policy vs gold policy).
4. Full inventory of all cases where gold policy is NOT #1 (with root cause analysis).
5. Latency metrics: p50, p90, p95 across all 84 vignettes.
"""

import json
import time
import numpy as np

import sys
import os
sys.path.insert(0, os.path.abspath("."))

from app.services.policy_shortlist_service import PolicyShortlistService
from app.services.declarative_engine import DeclarativePolicyEngine


def get_policy_decision(policy_id: str, ehr_text: str) -> str:
    policy = DeclarativePolicyEngine.load_policy(policy_id)
    if not policy:
        return "DEFERRED_TO_HUMAN"
    assessments = DeclarativePolicyEngine.evaluate_policy(policy, ehr_text)
    for a in assessments:
        if getattr(a, "is_exclusion", False) and getattr(a.status, "value", str(a.status)) == "MET":
            return "DENIED"
    non_excl = [a for a in assessments if not getattr(a, "is_exclusion", False)]
    if non_excl and all(getattr(a.status, "value", str(a.status)) == "MET" for a in non_excl):
        return "APPROVED"
    return "DEFERRED_TO_HUMAN"


def evaluate():
    with open("app/data/policies_extended/dev_vignettes_extended.json", "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    total_cases = len(vignettes)
    print(f"Total vignettes: {total_cases}")

    top1_count = 0
    top3_count = 0
    top5_count = 0
    preselected_count = 0
    selection_required_count = 0
    no_governing_count = 0

    latencies = []
    missed_top1_cases = []
    preselected_cases = []

    for idx, vig in enumerate(vignettes):
        vid = vig.get("vignette_id", f"VIG-{idx}")
        gold_policy = vig["policy_id"]
        expected_decision = vig.get("expected_decision")
        ehr = vig["ehr_narrative"]

        t0 = time.perf_counter()
        res = PolicyShortlistService.compute_shortlist(ehr, top_k=5)
        dt = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt)

        shortlist = res.get("shortlist", [])
        status = res.get("status")
        preselected_id = res.get("preselected_policy_id")

        pids = [c["policy_id"] for c in shortlist]

        in_top1 = (len(pids) > 0 and pids[0] == gold_policy)
        in_top3 = (gold_policy in pids[:3])
        in_top5 = (gold_policy in pids[:5])

        if in_top1:
            top1_count += 1
        else:
            top1_cand = pids[0] if pids else "NONE"
            top1_score = shortlist[0]["reranked_score"] if shortlist else 0.0
            gold_cand = next((c for c in shortlist if c["policy_id"] == gold_policy), None)
            gold_score = gold_cand["reranked_score"] if gold_cand else None
            gold_rank = gold_cand["rank"] if gold_cand else ">5"

            missed_top1_cases.append({
                "vignette_id": vid,
                "gold_policy": gold_policy,
                "top1_policy": top1_cand,
                "gold_rank": gold_rank,
                "top1_score": top1_score,
                "gold_score": gold_score,
                "status": status,
                "title": vig.get("title", "")
            })

        if in_top3:
            top3_count += 1
        if in_top5:
            top5_count += 1

        if status == "PRESELECTED":
            preselected_count += 1
            # Evaluate decision under preselected policy vs gold policy
            # Using declarative policy engine evaluate
            gold_decision = get_policy_decision(gold_policy, ehr)
            pre_decision = get_policy_decision(preselected_id, ehr)
            preselected_cases.append({
                "vignette_id": vid,
                "gold_policy": gold_policy,
                "preselected_policy": preselected_id,
                "gold_decision": gold_decision,
                "pre_decision": pre_decision,
                "is_match": (preselected_id == gold_policy)
            })
        elif status == "SELECTION_REQUIRED":
            selection_required_count += 1
        else:
            no_governing_count += 1

    top1_rate = top1_count / total_cases
    top3_rate = top3_count / total_cases
    top5_rate = top5_count / total_cases
    preselected_rate = preselected_count / total_cases
    selection_required_rate = selection_required_count / total_cases

    lat_p50 = float(np.percentile(latencies, 50))
    lat_p90 = float(np.percentile(latencies, 90))
    lat_p95 = float(np.percentile(latencies, 95))

    # Preselected decision agreement
    decision_matches = sum(1 for c in preselected_cases if c["gold_decision"] == c["pre_decision"])
    decision_acc = (decision_matches / len(preselected_cases)) if preselected_cases else 1.0

    print("\n" + "=" * 60)
    print("MEDICARE POLICY SHORTLIST EVALUATION ON 84 DEV VIGNETTES")
    print("=" * 60)
    print(f"Total vignettes:             {total_cases}")
    print(f"Gold in Top-1:               {top1_count}/{total_cases} ({top1_rate*100:.1f}%)")
    print(f"Gold in Top-3:               {top3_count}/{total_cases} ({top3_rate*100:.1f}%)")
    print(f"Gold in Top-5:               {top5_count}/{total_cases} ({top5_rate*100:.1f}%)")
    print(f"Pre-selected rate:           {preselected_count}/{total_cases} ({preselected_rate*100:.1f}%)")
    print(f"Clinician selection required: {selection_required_count}/{total_cases} ({selection_required_rate*100:.1f}%)")
    print(f"No governing policy:         {no_governing_count}/{total_cases} ({no_governing_count/total_cases*100:.1f}%)")
    print(f"Pre-selected decision acc:   {decision_matches}/{len(preselected_cases)} ({decision_acc*100:.1f}%)")
    print(f"Latency p50:                 {lat_p50:.1f} ms")
    print(f"Latency p90:                 {lat_p90:.1f} ms")
    print(f"Latency p95:                 {lat_p95:.1f} ms")
    print("=" * 60)

    print(f"\nInventory of Cases where Gold Policy was NOT #1 ({len(missed_top1_cases)} cases):")
    for m in missed_top1_cases:
        print(f"- Case: {m['vignette_id']} | Gold: {m['gold_policy']} (Rank #{m['gold_rank']}, Score: {m['gold_score']}) | Top-1: {m['top1_policy']} (Score: {m['top1_score']:.3f}) | Status: {m['status']}")
        print(f"  Title/Context: {m['title']}")

    # Save detailed JSON report
    report = {
        "total_cases": total_cases,
        "top1_count": top1_count,
        "top1_rate": round(top1_rate, 4),
        "top3_count": top3_count,
        "top3_rate": round(top3_rate, 4),
        "top5_count": top5_count,
        "top5_rate": round(top5_rate, 4),
        "preselected_count": preselected_count,
        "preselected_rate": round(preselected_rate, 4),
        "selection_required_count": selection_required_count,
        "selection_required_rate": round(selection_required_rate, 4),
        "no_governing_count": no_governing_count,
        "preselected_decision_matches": decision_matches,
        "preselected_decision_accuracy": round(decision_acc, 4),
        "latency_p50_ms": round(lat_p50, 2),
        "latency_p90_ms": round(lat_p90, 2),
        "latency_p95_ms": round(lat_p95, 2),
        "missed_top1_cases": missed_top1_cases
    }
    with open("tests/policy_shortlist_eval_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    evaluate()
