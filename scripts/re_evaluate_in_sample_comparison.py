"""
Task 3: Re-run clean comparison and report true delta, labelled IN-SAMPLE.
Evaluates the 84 dev vignettes live in this session:
- Arm A: Committed map only (12 concepts), span-repair disabled.
- Arm B: In-memory expanded map (12 committed + 120 v27 PASS entries + 15 v29 PASS attested entries = 147 concepts), span-repair enabled.
Both arms measured fresh in this session with same v2 prompt, same 84 cases, and same call counting.
Results saved to app/data/benchmarks/in_sample_comparison_results.json.
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.concept_map import ConceptMap, ConceptDefinition, ConceptSource
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.llm_proposer import LLMProposalAgent

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

def build_in_sample_concept_map() -> Tuple[ConceptMap, int, int, int]:
    """
    Builds the in-sample test-only concept map:
    12 committed + 120 v27 policy drafts + 15 v29 attested drafts = 147 total.
    """
    exp_map = ConceptMap()
    committed_count = exp_map.total_concepts

    # 1. Load v27 drafts
    draft_v27_file = ROOT_DIR / "app" / "data" / "concept_map" / "draft_concept_entries.json"
    added_v27 = 0
    if draft_v27_file.exists():
        with open(draft_v27_file, "r", encoding="utf-8") as f:
            drafts_v27 = json.load(f)
        for d in drafts_v27:
            if d.get("governing_rule_check") == "PASS_EQUIVALENCE":
                cdef = ConceptDefinition(
                    concept_id=d["concept_id"],
                    canonical_name=d["canonical_name"],
                    domain=d["domain"],
                    accepted_terms=d["accepted_terms"],
                    prohibited_near_misses=d.get("prohibited_near_misses", []),
                    source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
                    source_reason=f"What-if v27: {d['governing_rule_rationale']}"
                )
                exp_map.register_concept(cdef)
                added_v27 += 1

    # 2. Load v29 attested drafts
    draft_v29_file = ROOT_DIR / "app" / "data" / "concept_map" / "draft_attested_concept_entries.json"
    added_v29 = 0
    if draft_v29_file.exists():
        with open(draft_v29_file, "r", encoding="utf-8") as f:
            drafts_v29 = json.load(f)
        for d in drafts_v29.get("entries", []):
            if d.get("governing_rule_check") == "PASS_EQUIVALENCE":
                cdef = ConceptDefinition(
                    concept_id=d["concept_id"],
                    canonical_name=d["canonical_name"],
                    domain=d["domain"],
                    accepted_terms=d["accepted_terms"],
                    prohibited_near_misses=d.get("prohibited_near_misses", []),
                    source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
                    source_reason=f"In-sample v29: {d['governing_rule_rationale']}"
                )
                exp_map.register_concept(cdef)
                added_v29 += 1

    print(f"[*] In-Sample ConceptMap assembled: {committed_count} committed + {added_v27} v27 drafts + {added_v29} v29 attested drafts = {exp_map.total_concepts} total concepts.")
    return exp_map, committed_count, added_v27, added_v29


def run_clean_arm(
    arm_name: str,
    vignettes: List[Dict[str, Any]],
    active_map: ConceptMap,
    enable_span_repair: bool
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Executes one clean experimental arm over the 84 dev vignettes.
    """
    print(f"\n{'='*70}\n[ARM RUN] {arm_name}\nMap Concepts: {active_map.total_concepts} | Span Repair: {enable_span_repair}\n{'='*70}")

    import app.core.concept_map as cm_mod
    cm_mod._GLOBAL_CONCEPT_MAP = active_map

    LLMProposalAgent.span_repair_enabled = enable_span_repair

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0
    pipeline.llm_proposer.span_repair_enabled = enable_span_repair

    adjudication_results = []
    concordant_count = 0
    false_approvals = 0
    false_denials = 0
    deferrals = 0
    resolved_synonymy = []

    t0 = time.time()
    for idx, vig in enumerate(vignettes, 1):
        vid = vig["vignette_id"]
        pid = vig["policy_id"]
        exp_dec = vig["expected_decision"]
        narrative = vig["ehr_narrative"]

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-INSAMPLE-{idx:03d}",
            policy_id=pid,
            ehr_narrative=narrative,
            execution_mode="declarative",
            save_record=False
        )
        act_dec = res.adjudication_decision.value

        is_concordant = (act_dec == exp_dec)
        if is_concordant:
            concordant_count += 1
            if vid in SYNONYMY_VIGNETTE_IDS:
                resolved_synonymy.append(vid)
        else:
            if exp_dec == "DENIED" and act_dec == "APPROVED":
                false_approvals += 1
            elif exp_dec == "APPROVED" and act_dec == "DENIED":
                false_denials += 1

        if act_dec == "DEFERRED_TO_HUMAN":
            deferrals += 1

        adjudication_results.append({
            "vignette_id": vid,
            "policy_id": pid,
            "expected_decision": exp_dec,
            "actual_decision": act_dec,
            "concordant": is_concordant,
            "abstention_reason": getattr(res, "abstention_reason", None)
        })

    elapsed = round(time.time() - t0, 1)

    # Teardown
    cm_mod._GLOBAL_CONCEPT_MAP = None
    LLMProposalAgent.span_repair_enabled = True

    telem = pipeline.llm_proposer.telemetry
    calls = telem.get("total_calls", 0)
    gate_a_fails = telem.get("gate_a_rejections", 0)
    gate_b_fails = telem.get("gate_b_rejections", 0)
    gate_c_fails = telem.get("gate_c_map_rejections", 0)
    proposals_accepted = telem.get("proposals_accepted", 0)
    gate_a_passes = calls - gate_a_fails

    acc_pct = round((concordant_count / len(vignettes)) * 100.0, 1)

    arm_summary = {
        "arm_name": arm_name,
        "elapsed_seconds": elapsed,
        "total_cases": len(vignettes),
        "calls": calls,
        "gate_a_passes": gate_a_passes,
        "gate_a_fails": gate_a_fails,
        "gate_b_rejections": gate_b_fails,
        "gate_c_map_rejections": gate_c_fails,
        "proposals_accepted": proposals_accepted,
        "concordant_decisions": concordant_count,
        "accuracy_pct": acc_pct,
        "four_number_safety": {
            "false_approvals": false_approvals,
            "false_denials": false_denials,
            "safe_deferrals": deferrals,
            "concordant_decisions": concordant_count
        },
        "synonymy_resolved_count": len(resolved_synonymy),
        "synonymy_resolved_cases": resolved_synonymy
    }

    print(f"[{arm_name}] Finished in {elapsed}s:")
    print(f"  Calls: {calls} | Gate A Fail: {gate_a_fails} | Gate C Fail: {gate_c_fails} | Accepted: {proposals_accepted}")
    print(f"  Accuracy: {concordant_count}/{len(vignettes)} ({acc_pct}%) | False Approvals: {false_approvals}")
    print(f"  Synonymy Resolved: {len(resolved_synonymy)}/19 ({resolved_synonymy})")

    return arm_summary, adjudication_results


if __name__ == "__main__":
    dev_path = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    # Arm A: Committed Map Only (12 concepts), span-repair disabled
    committed_map = ConceptMap()
    summary_a, adj_a = run_clean_arm(
        arm_name="Arm A: Committed Map Only (12 concepts, span repair OFF)",
        vignettes=vignettes,
        active_map=committed_map,
        enable_span_repair=False
    )

    # Arm B: In-Sample Expanded Map (147 concepts), span-repair enabled
    in_sample_map, c_cnt, v27_cnt, v29_cnt = build_in_sample_concept_map()
    summary_b, adj_b = run_clean_arm(
        arm_name="Arm B: In-Sample Expanded Map (147 concepts, span repair ON) [IN-SAMPLE]",
        vignettes=vignettes,
        active_map=in_sample_map,
        enable_span_repair=True
    )

    if summary_a["four_number_safety"]["false_approvals"] > 0:
        print("[!] CRITICAL DEFECT: False approvals in Arm A!")
        sys.exit(1)
    if summary_b["four_number_safety"]["false_approvals"] > 0:
        print("[!] CRITICAL DEFECT: False approvals in Arm B!")
        sys.exit(1)

    delta = {
        "calls_delta": summary_b["calls"] - summary_a["calls"],
        "gate_a_fail_delta": summary_b["gate_a_fails"] - summary_a["gate_a_fails"],
        "gate_b_fail_delta": summary_b["gate_b_rejections"] - summary_a["gate_b_rejections"],
        "gate_c_map_rejections_delta": summary_b["gate_c_map_rejections"] - summary_a["gate_c_map_rejections"],
        "proposals_accepted_delta": summary_b["proposals_accepted"] - summary_a["proposals_accepted"],
        "concordant_decisions_delta": summary_b["concordant_decisions"] - summary_a["concordant_decisions"],
        "accuracy_pct_delta": round(summary_b["accuracy_pct"] - summary_a["accuracy_pct"], 1),
        "synonymy_resolved_delta": summary_b["synonymy_resolved_count"] - summary_a["synonymy_resolved_count"],
        "false_approvals_delta": summary_b["four_number_safety"]["false_approvals"] - summary_a["four_number_safety"]["false_approvals"]
    }

    out_file = ROOT_DIR / "app" / "data" / "benchmarks" / "in_sample_comparison_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "status": "IN_SAMPLE_UPPER_BOUND_EVALUATION",
            "disclosure": (
                "IN-SAMPLE EVALUATION: Task 1 concept entries were curated from these exact development vignettes. "
                "The reported accuracy gains represent an upper bound and proof of mechanism, NOT proof of generalization. "
                "Generalization remains unmeasured until evaluated against the sealed held-out benchmark."
            ),
            "arm_a_committed_baseline": summary_a,
            "arm_b_in_sample_expanded": summary_b,
            "in_sample_true_delta": delta
        }, f, indent=2)

    print(f"\n[+] Saved in-sample comparison results to {out_file}")

    # Re-run deterministic baseline check with committed map to confirm 39/84 unchanged
    print("\n[*] Re-running deterministic baseline check with committed map...")
    from scripts.evaluate_extended_policies import run_evaluation
    baseline_check = run_evaluation(write_report=False)
    assert baseline_check["decision_correct"] == 39, f"Baseline check failed: expected 39, got {baseline_check['decision_correct']}"
    assert baseline_check["top1_correct"] == 73, f"Baseline check failed: expected 73, got {baseline_check['top1_correct']}"
    print(f"[+] Confirmed: Committed baseline remains strictly {baseline_check['decision_correct']}/84 ({baseline_check['dec_pct']:.1f}%).")
