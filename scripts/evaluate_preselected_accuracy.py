"""Evaluates decision accuracy on the 84 dev vignettes using the REAL pipeline:

1. On the 40 preselected cases:
   - Evaluated under GOLD policy vs expected_decision
   - Evaluated under PRESELECTED policy vs expected_decision
   - Preselected policy match rate (is_match)
2. On the 44 selection-required cases:
   - Evaluated under GOLD policy vs expected_decision (clinician-pick reference)
3. Persists complete per-case table to tests/policy_shortlist_preselected_accuracy.json
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.policy_shortlist_service import PolicyShortlistService


def run_preselected_accuracy_evaluation():
    vignettes_file = REPO_ROOT / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(vignettes_file, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    print(f"[*] Loaded {len(vignettes)} development vignettes.")
    pipeline = MultiAgentVerificationPipeline(db=None)

    preselected_records = []
    selection_required_records = []

    for idx, vig in enumerate(vignettes):
        vid = vig.get("vignette_id", f"VIG-{idx}")
        gold_policy = vig["policy_id"]
        expected_decision = vig.get("expected_decision")
        ehr = vig["ehr_narrative"]

        shortlist_res = PolicyShortlistService.compute_shortlist(ehr, top_k=5)
        status = shortlist_res.get("status")
        preselected_id = shortlist_res.get("preselected_policy_id")

        if status == "PRESELECTED" and preselected_id:
            # 1. Real pipeline adjudication under GOLD policy
            adj_gold = pipeline.adjudicate_sync(
                patient_id=f"PT-EVAL-GOLD-{idx}",
                policy_id=gold_policy,
                ehr_narrative=ehr,
                execution_mode="deterministic",
                save_record=False,
            )
            dec_gold = adj_gold.adjudication_decision.value

            # 2. Real pipeline adjudication under PRESELECTED policy
            if preselected_id == gold_policy:
                dec_pre = dec_gold
            else:
                adj_pre = pipeline.adjudicate_sync(
                    patient_id=f"PT-EVAL-PRE-{idx}",
                    policy_id=preselected_id,
                    ehr_narrative=ehr,
                    execution_mode="deterministic",
                    save_record=False,
                )
                dec_pre = adj_pre.adjudication_decision.value

            is_match = (preselected_id == gold_policy)
            gold_matches_expected = (dec_gold == expected_decision)
            pre_matches_expected = (dec_pre == expected_decision)
            decisions_agree = (dec_gold == dec_pre)

            preselected_records.append({
                "vignette_id": vid,
                "title": vig.get("title", ""),
                "gold_policy": gold_policy,
                "preselected_policy": preselected_id,
                "is_match": is_match,
                "expected_decision": expected_decision,
                "decision_under_gold": dec_gold,
                "decision_under_preselected": dec_pre,
                "gold_matches_expected": gold_matches_expected,
                "preselected_matches_expected": pre_matches_expected,
                "decisions_agree": decisions_agree,
                "score_margin": shortlist_res.get("preselection_margin"),
                "coverage_ratio": shortlist_res.get("preselection_coverage_ratio")
            })
        else:
            # Selection required case (clinician pick path)
            adj_gold = pipeline.adjudicate_sync(
                patient_id=f"PT-EVAL-REQ-{idx}",
                policy_id=gold_policy,
                ehr_narrative=ehr,
                execution_mode="deterministic",
                save_record=False,
            )
            dec_gold = adj_gold.adjudication_decision.value
            gold_matches_expected = (dec_gold == expected_decision)

            selection_required_records.append({
                "vignette_id": vid,
                "title": vig.get("title", ""),
                "gold_policy": gold_policy,
                "status": status,
                "expected_decision": expected_decision,
                "decision_under_gold": dec_gold,
                "gold_matches_expected": gold_matches_expected,
                "shortlist_candidates": [c["policy_id"] for c in shortlist_res.get("shortlist", [])]
            })

    # Summary metrics
    n_pre = len(preselected_records)
    policy_matches = sum(1 for r in preselected_records if r["is_match"])
    policy_match_rate = policy_matches / n_pre if n_pre else 0.0

    gold_acc_pre = sum(1 for r in preselected_records if r["gold_matches_expected"]) / n_pre if n_pre else 0.0
    pre_acc_pre = sum(1 for r in preselected_records if r["preselected_matches_expected"]) / n_pre if n_pre else 0.0
    dec_agree_pre = sum(1 for r in preselected_records if r["decisions_agree"]) / n_pre if n_pre else 0.0

    n_req = len(selection_required_records)
    gold_acc_req = sum(1 for r in selection_required_records if r["gold_matches_expected"]) / n_req if n_req else 0.0

    summary = {
        "dataset": "84 dev vignettes, author-written, not held-out, not clinical validation",
        "database": "carepolicyguard.db (repo SQLite database)",
        "pipeline_mode": "MultiAgentVerificationPipeline.adjudicate_sync (deterministic)",
        "preselected_count": n_pre,
        "selection_required_count": n_req,
        "policy_match_count": policy_matches,
        "policy_match_rate": round(policy_match_rate, 4),
        "preselected_decision_accuracy_under_gold": round(gold_acc_pre, 4),
        "preselected_decision_accuracy_under_preselected": round(pre_acc_pre, 4),
        "preselected_decision_agreement_rate": round(dec_agree_pre, 4),
        "selection_required_decision_accuracy_under_gold": round(gold_acc_req, 4),
        "preselected_cases": preselected_records,
        "selection_required_cases": selection_required_records
    }

    out_file = REPO_ROOT / "tests" / "policy_shortlist_preselected_accuracy.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 65)
    print("TASK 2 ACCURACY COMPARISON ON REAL PIPELINE")
    print("=" * 65)
    print(f"Preselected cases:                             {n_pre}")
    print(f"Policy match count (is_match):                 {policy_matches}/{n_pre} ({policy_match_rate:.1%})")
    print(f"Decision accuracy under GOLD policy:           {sum(1 for r in preselected_records if r['gold_matches_expected'])}/{n_pre} ({gold_acc_pre:.1%})")
    print(f"Decision accuracy under PRESELECTED policy:    {sum(1 for r in preselected_records if r['preselected_matches_expected'])}/{n_pre} ({pre_acc_pre:.1%})")
    print(f"Decision agreement between gold & preselected: {sum(1 for r in preselected_records if r['decisions_agree'])}/{n_pre} ({dec_agree_pre:.1%})")
    print(f"Reference: Clinician-pick accuracy (gold):     {sum(1 for r in selection_required_records if r['gold_matches_expected'])}/{n_req} ({gold_acc_req:.1%})")
    print(f"Persisted to:                                  {out_file.name}")
    print("=" * 65)

    misses = [r for r in preselected_records if not r["is_match"]]
    if misses:
        print(f"\nPreselection Policy Misses ({len(misses)} case):")
        for m in misses:
            print(f"- {m['vignette_id']}: Gold={m['gold_policy']} vs Preselected={m['preselected_policy']}")
            print(f"  Decision under gold: {m['decision_under_gold']} | Decision under preselected: {m['decision_under_preselected']} | Expected: {m['expected_decision']}")


if __name__ == "__main__":
    run_preselected_accuracy_evaluation()
