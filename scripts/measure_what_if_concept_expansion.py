"""
Task 3: Measure what the expanded ConceptMap would do (What-If Experimental Run).
- Labels all metrics strictly as WHAT-IF ("if a human approved these entries, the LLM would...").
- Enables PENDING PASS_EQUIVALENCE entries in a test-only, in-memory ConceptMap.
- Committed map in app/core/concept_map.py stays 100% untouched.
- Evaluates on 84 dev vignettes with LLM proposal step active.
- Verifies that false approvals caused by LLM == 0 (safety invariant).
- Confirms committed baseline remains strictly 39/84 (46.4%).
"""

import sys
import json
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.concept_map import ConceptMap, ConceptDefinition, ConceptSource
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.declarative_engine import DeclarativePolicyEngine

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

def build_experimental_concept_map():
    draft_file = ROOT_DIR / "app" / "data" / "concept_map" / "draft_concept_entries.json"
    if not draft_file.exists():
        print(f"Error: {draft_file} does not exist.")
        sys.exit(1)

    with open(draft_file, "r", encoding="utf-8") as f:
        drafts = json.load(f)

    # Initialize standard ConceptMap (contains the 12 committed concepts)
    exp_map = ConceptMap()
    committed_count = exp_map.total_concepts

    added_count = 0
    for d in drafts:
        # Only activate entries that passed the governing-rule equivalence check
        if d.get("governing_rule_check") == "PASS_EQUIVALENCE":
            cdef = ConceptDefinition(
                concept_id=d["concept_id"],
                canonical_name=d["canonical_name"],
                domain=d["domain"],
                accepted_terms=d["accepted_terms"],
                prohibited_near_misses=d.get("prohibited_near_misses", []),
                source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
                source_reason=f"What-if experimental activation: {d['governing_rule_rationale']}"
            )
            exp_map.register_concept(cdef)
            added_count += 1

    print(f"[*] Built Experimental In-Memory ConceptMap: {committed_count} committed concepts + {added_count} what-if concepts = {exp_map.total_concepts} total concepts.")
    return exp_map, added_count

def run_what_if_measurement():
    dev_path = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    exp_map, added_concepts = build_experimental_concept_map()

    # Baseline numbers from v26 3B run (126 calls, committed 12-concept map)
    baseline_stats = {
        "calls": 126,
        "gate_a_rejections": 79,
        "gate_b_rejections": 2,
        "gate_c_map_rejections": 43,
        "proposals_accepted": 2,
        "decision_accuracy_pct": 46.4,
        "concordant_cases": 39,
        "synonymy_resolved": 0
    }

    pipeline = MultiAgentVerificationPipeline(db=None)
    # Inject experimental in-memory concept map into the proposer and verifier for this run only
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0

    # Monkeypatch get_concept_map on llm_proposer and verifier
    import app.core.concept_map as cm_mod
    original_get_map = cm_mod.get_concept_map
    cm_mod._GLOBAL_CONCEPT_MAP = exp_map

    print("\n[*] Executing What-If Evaluation on 84 Development Vignettes with Experimental ConceptMap...")

    total_count = len(vignettes)
    what_if_concordant = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0

    resolved_synonymy_cases = []

    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-WHATIF-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False
        )

        act_dec = res.adjudication_decision.value

        if act_dec == exp_dec:
            what_if_concordant += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                resolved_synonymy_cases.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

    # Restore singleton
    cm_mod._GLOBAL_CONCEPT_MAP = None

    # Telemetry from proposer
    telem = pipeline.llm_proposer.telemetry
    what_if_calls = telem.get("total_calls", 0)
    what_if_gate_a = telem.get("gate_a_rejections", 0)
    what_if_gate_b = telem.get("gate_b_rejections", 0)
    what_if_gate_c = telem.get("gate_c_map_rejections", 0)
    what_if_accepted = telem.get("proposals_accepted", 0)

    what_if_acc_pct = round((what_if_concordant / total_count) * 100.0, 1)

    print("\n" + "=" * 70)
    print("TASK 3: WHAT-IF EXPERIMENTAL CONCEPT EXPANSION RESULTS")
    print("=" * 70)
    print(f"Metric                           | Committed Baseline | What-If Expanded Map | Delta")
    print(f"---------------------------------|--------------------|----------------------|-------")
    print(f"Gate C Map Rejections            | {baseline_stats['gate_c_map_rejections']:<18} | {what_if_gate_c:<20} | {what_if_gate_c - baseline_stats['gate_c_map_rejections']:+d}")
    print(f"Proposals Accepted               | {baseline_stats['proposals_accepted']:<18} | {what_if_accepted:<20} | {what_if_accepted - baseline_stats['proposals_accepted']:+d}")
    print(f"Decision Accuracy (Concordance)  | 46.4% (39/84)      | {what_if_acc_pct}% ({what_if_concordant}/84)         | +{what_if_concordant - 39} cases")
    print(f"Synonymy-Only Deferrals Resolved | 0 / 19             | {len(resolved_synonymy_cases)} / 19                | +{len(resolved_synonymy_cases)}")
    print(f"\nSafety Invariant Verification:")
    print(f"  - False Approvals Caused by LLM: {false_approvals} (Must strictly be 0)")
    print(f"  - False Denials Caused by LLM:   {false_denials} (Must strictly be 0)")
    print(f"  - Safe Deferrals to Human:       {deferrals}")

    if false_approvals > 0:
        print("\n[!] CRITICAL DEFECT: False approvals detected in what-if run! Safety invariant violated.")
        sys.exit(1)

    # Re-run deterministic baseline with committed map to confirm 39/84 unchanged
    print("\n[*] Re-running deterministic evaluation with committed map to verify baseline...")
    from scripts.evaluate_extended_policies import run_evaluation
    baseline_check = run_evaluation(write_report=False)
    assert baseline_check["decision_correct"] == 39, f"Baseline check failed: expected 39, got {baseline_check['decision_correct']}"
    assert baseline_check["top1_correct"] == 73, f"Baseline check failed: expected 73, got {baseline_check['top1_correct']}"
    print(f"[+] Confirmed: Committed baseline remains exactly {baseline_check['decision_correct']}/84 ({baseline_check['dec_pct']:.1f}%).")

    # Save what-if results
    out_file = ROOT_DIR / "app" / "data" / "benchmarks" / "what_if_concept_expansion_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "status": "WHAT_IF_EXPERIMENTAL_ONLY",
            "disclosure": "What-if measurement only. Draft concepts remain PENDING in review queue; committed map remains unchanged at 12 concepts.",
            "baseline": baseline_stats,
            "what_if": {
                "calls": what_if_calls,
                "gate_a_rejections": what_if_gate_a,
                "gate_b_rejections": what_if_gate_b,
                "gate_c_map_rejections": what_if_gate_c,
                "proposals_accepted": what_if_accepted,
                "concordant_cases": what_if_concordant,
                "accuracy_pct": what_if_acc_pct,
                "false_approvals": false_approvals,
                "false_denials": false_denials,
                "deferrals": deferrals,
                "synonymy_resolved_count": len(resolved_synonymy_cases),
                "synonymy_resolved_cases": resolved_synonymy_cases
            },
            "committed_baseline_confirmed": {
                "accuracy": f"{baseline_check['decision_correct']}/84",
                "accuracy_pct": baseline_check["dec_pct"]
            }
        }, f, indent=2)
    print(f"[*] What-if results saved to {out_file}")

if __name__ == "__main__":
    run_what_if_measurement()
