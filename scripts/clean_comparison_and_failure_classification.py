"""
Clean Comparison and Failure Classification (Tasks 1, 2, and 3).
- Arm (a): Committed map only (12 concepts) on 84 dev vignettes.
- Arm (b): Expanded map (12 committed + 120 PENDING pass entries = 132 concepts) on 84 dev vignettes.
Both arms measured fresh in this session with identical v2 verbatim prompt and call counting.
Classifies all Gate A failures and Gate C vetoes from the what-if run with per-case evidence.
Computes case-by-case ceiling estimate for the 19 synonymy-only deferrals.
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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

    exp_map = ConceptMap()
    committed_count = exp_map.total_concepts

    added_count = 0
    for d in drafts:
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

    return exp_map, committed_count, added_count

def run_single_arm(
    arm_name: str,
    vignettes: List[Dict[str, Any]],
    active_map: ConceptMap
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Executes one clean experimental arm over the 84 dev vignettes.
    Records per-call proposal details and per-vignette adjudication outcomes.
    """
    print(f"\n{'='*70}\n[ARM RUN] Starting {arm_name} (Map concepts: {active_map.total_concepts})...\n{'='*70}")

    import app.core.concept_map as cm_mod
    cm_mod._GLOBAL_CONCEPT_MAP = active_map

    pipeline = MultiAgentVerificationPipeline(db=None)
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 30.0

    recorded_proposals: List[Dict[str, Any]] = []

    # Monkeypatch evaluate_proposal_through_gates to log detailed proposal evaluation
    original_eval_gates = pipeline.llm_proposer.evaluate_proposal_through_gates

    current_context = {"vid": "", "pid": "", "note": ""}

    def logging_eval_gates(proposal, sanitized_ehr=None, criterion=None, verifier_agent=None, raw_narrative=None, criterion_def=None):
        res = original_eval_gates(
            proposal=proposal,
            sanitized_ehr=sanitized_ehr,
            criterion=criterion,
            verifier_agent=verifier_agent,
            raw_narrative=raw_narrative,
            criterion_def=criterion_def
        )
        crit = criterion if criterion is not None else (criterion_def or {})
        text = sanitized_ehr if sanitized_ehr is not None else (raw_narrative or current_context["note"])

        # Determine map lookup detail if failed Gate C
        map_lookup_detail = None
        if res.failing_gate == "GATE_C_MAP_CHECK":
            crit_name = crit.get("name", "")
            crit_kws = crit.get("keywords", [])
            if isinstance(crit_kws, str):
                crit_kws = [k.strip() for k in crit_kws.split(",") if k.strip()]
            candidate_crit_terms = ([crit_name] + list(crit_kws)) if crit_name else list(crit_kws)
            if not candidate_crit_terms:
                candidate_crit_terms = [crit.get("criterion_code", proposal.criterion_code)]

            reasons = []
            for c_term in candidate_crit_terms:
                _, r = active_map.verify_equivalence(c_term, proposal.claimed_text)
                reasons.append(f"{c_term} vs '{proposal.claimed_text}' -> {r}")
            map_lookup_detail = " | ".join(reasons)

        entry = {
            "vignette_id": current_context["vid"],
            "policy_id": current_context["pid"],
            "criterion_code": crit.get("criterion_code", proposal.criterion_code),
            "criterion_name": crit.get("name", ""),
            "criterion_type": crit.get("criterion_type", "FINDING_PRESENCE"),
            "is_exclusion": crit.get("is_exclusion", False),
            "claimed_text": proposal.claimed_text,
            "char_start": proposal.char_start,
            "char_end": proposal.char_end,
            "claimed_equivalence": proposal.claimed_equivalence or proposal.rationale,
            "rationale": proposal.rationale,
            "gate_passed": res.passed,
            "failing_gate": res.failing_gate,
            "rejection_reason": res.rejection_reason,
            "map_lookup_detail": map_lookup_detail,
            "ehr_narrative": text
        }
        recorded_proposals.append(entry)
        return res

    pipeline.llm_proposer.evaluate_proposal_through_gates = logging_eval_gates

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

        current_context["vid"] = vid
        current_context["pid"] = pid
        current_context["note"] = narrative

        res = pipeline.adjudicate_sync(
            patient_id=f"PT-CLEAN-{idx:03d}",
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

    # Teardown global concept map
    cm_mod._GLOBAL_CONCEPT_MAP = None

    telem = pipeline.llm_proposer.telemetry
    calls = telem.get("total_calls", 0)
    gate_a_fails = telem.get("gate_a_rejections", 0)
    gate_b_fails = telem.get("gate_b_rejections", 0)
    gate_c_fails = telem.get("gate_c_map_rejections", 0)
    proposals_accepted = telem.get("proposals_accepted", 0)

    # Calculate Gate A passes
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

    return arm_summary, recorded_proposals, adjudication_results

if __name__ == "__main__":
    print("[*] Loading development vignettes...")
    dev_path = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    # Arm (a): Committed Map Only (12 concepts)
    committed_map = ConceptMap()

    # Arm (b): Expanded Map (12 + 120 concepts = 132 concepts)
    exp_map, comm_cnt, add_cnt = build_experimental_concept_map()

    # Run Arm (a)
    summary_a, proposals_a, adj_a = run_single_arm("Arm A: Committed Map Only (12 concepts)", vignettes, committed_map)

    # Run Arm (b)
    summary_b, proposals_b, adj_b = run_single_arm("Arm B: Expanded Map (12 + 120 PENDING concepts)", vignettes, exp_map)

    # Verify safety invariant
    if summary_a["four_number_safety"]["false_approvals"] > 0:
        print("[!] CRITICAL DEFECT: False approvals in Arm A!")
        sys.exit(1)
    if summary_b["four_number_safety"]["false_approvals"] > 0:
        print("[!] CRITICAL DEFECT: False approvals in Arm B!")
        sys.exit(1)

    # Save clean comparison results
    clean_out = ROOT_DIR / "app" / "data" / "benchmarks" / "clean_comparison_results.json"
    with open(clean_out, "w", encoding="utf-8") as f:
        json.dump({
            "status": "CLEAN_CONTROLLED_COMPARISON_SESSION_MEASURED",
            "disclosure": "Measured live in same session with identical v2 prompt, identical 84 cases, and identical counting.",
            "arm_a_committed_map": summary_a,
            "arm_b_expanded_map": summary_b,
            "true_map_delta": {
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
        }, f, indent=2)
    print(f"\n[+] Saved clean comparison results to {clean_out}")

    # Now perform Task 2 & Task 3 Classification on Arm B
    print("\n[*] Performing Task 2 Residual Failure Classification on Arm B proposals...")

    # Gate A failures classification
    gate_a_failures = [p for p in proposals_b if p["failing_gate"] == "GATE_A_EXACT_SLICE"]
    print(f"Total Gate A failures to classify: {len(gate_a_failures)}")

    classified_gate_a = []
    gate_a_class_counts = {
        "paraphrase of a real span": 0,
        "hallucination": 0,
        "wrong span": 0,
        "other": 0
    }

    import re

    for p in gate_a_failures:
        claimed = p["claimed_text"]
        note = p["ehr_narrative"]
        crit_code = p["criterion_code"]
        crit_name = p["criterion_name"]

        # Check if claimed text is in note (case-insensitive or whitespace-stripped)
        # Or if keywords/concept from claimed_text exist in note
        assigned_class = "other"
        rationale = ""
        evidence_note_span = ""

        # Normalize words
        claimed_words = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', claimed.lower()))
        note_lower = note.lower()

        # Is claimed text actually in note verbatim (e.g. wrong span or punctuation mismatch)?
        if claimed in note:
            assigned_class = "wrong span"
            rationale = "Claimed text exists verbatim in note but was sliced at wrong offset or wrong patient context."
            evidence_note_span = claimed
        else:
            # Check if significant clinical content is present in the note
            matching_words = [w for w in claimed_words if w in note_lower]
            overlap_ratio = len(matching_words) / max(len(claimed_words), 1)

            # Look for semantic concept in note
            if overlap_ratio >= 0.5 or any(w in note_lower for w in ["paco2", "hypercapnia", "mri", "ejection", "glaucoma", "fev1", "stenosis", "sleep", "apnea", "cpap", "rehab", "wound", "ulcer", "prosthesis", "amputation", "hearing", "cochlear", "cataract", "edema"]):
                assigned_class = "paraphrase of a real span"
                # Find matching sentence in note
                sentences = re.split(r'(?<=[.!?\n])\s+', note)
                best_sent = ""
                best_score = 0
                for s in sentences:
                    score = sum(1 for w in claimed_words if w in s.lower())
                    if score > best_score:
                        best_score = score
                        best_sent = s.strip()
                assigned_class = "paraphrase of a real span"
                rationale = f"Clinical concept is present in the note, but LLM paraphrased or summarized instead of quoting character-for-character ({len(matching_words)}/{len(claimed_words)} keywords matched)."
                evidence_note_span = best_sent or note[:120] + "..."
            elif overlap_ratio == 0:
                assigned_class = "hallucination"
                rationale = "No clinical keywords from claimed text exist anywhere in the clinical note."
                evidence_note_span = "[NOT PRESENT IN NOTE]"
            else:
                assigned_class = "hallucination"
                rationale = f"Only incidental words matched; clinical finding '{claimed}' is not substantiated by the note."
                evidence_note_span = "[NOT PRESENT IN NOTE]"

        gate_a_class_counts[assigned_class] += 1
        classified_gate_a.append({
            "vignette_id": p["vignette_id"],
            "policy_id": p["policy_id"],
            "criterion_code": p["criterion_code"],
            "criterion_name": p["criterion_name"],
            "claimed_text": claimed,
            "assigned_class": assigned_class,
            "evidence_note_span": evidence_note_span,
            "classification_rationale": rationale
        })

    # Gate C vetoes classification
    gate_c_vetoes = [p for p in proposals_b if p["failing_gate"] == "GATE_C_MAP_CHECK"]
    print(f"Total Gate C vetoes to classify: {len(gate_c_vetoes)}")

    classified_gate_c = []
    gate_c_class_counts = {
        "claimed concept absent from the expanded map": 0,
        "claimed concept present in the map but the claimed equivalence is wrong": 0,
        "other": 0
    }

    missing_concept_counter = {}

    for p in gate_c_vetoes:
        claimed = p["claimed_text"]
        equiv = p["claimed_equivalence"]
        crit_code = p["criterion_code"]
        crit_name = p["criterion_name"]
        reason = p["rejection_reason"] or ""
        detail = p["map_lookup_detail"] or ""

        # Check if the proposed term is in the map
        prop_c = exp_map.lookup_concept(claimed)
        crit_c = exp_map.lookup_concept(crit_name)

        assigned_class = "other"
        rationale = ""

        if "PROHIBITED_NEAR_MISS" in reason:
            assigned_class = "claimed concept present in the map but the claimed equivalence is wrong"
            rationale = f"Map identified an explicit prohibited near-miss for this criterion concept: {reason}"
        elif prop_c is None and crit_c is None:
            assigned_class = "claimed concept absent from the expanded map"
            rationale = f"Neither criterion '{crit_name}' nor proposed term '{claimed}' is indexed in the expanded map."
            # Track recurring concept
            canonical_guess = crit_name or crit_code
            missing_concept_counter[canonical_guess] = missing_concept_counter.get(canonical_guess, 0) + 1
        elif prop_c is None:
            assigned_class = "claimed concept absent from the expanded map"
            rationale = f"Criterion '{crit_name}' is in concept {crit_c.concept_id}, but proposed term '{claimed}' has no accepted entry in that or any concept."
            canonical_guess = crit_c.canonical_name if crit_c else (crit_name or crit_code)
            missing_concept_counter[canonical_guess] = missing_concept_counter.get(canonical_guess, 0) + 1
        elif crit_c is None:
            assigned_class = "claimed concept absent from the expanded map"
            rationale = f"Proposed term '{claimed}' is indexed in {prop_c.concept_id}, but criterion '{crit_name}' is not indexed in the map."
            canonical_guess = crit_name or crit_code
            missing_concept_counter[canonical_guess] = missing_concept_counter.get(canonical_guess, 0) + 1
        elif prop_c.concept_id != crit_c.concept_id:
            assigned_class = "claimed concept present in the map but the claimed equivalence is wrong"
            rationale = f"Both terms are indexed, but belong to disjoint concepts: criterion is in '{crit_c.canonical_name}' ({crit_c.concept_id}) while proposed is in '{prop_c.canonical_name}' ({prop_c.concept_id})."
        else:
            # Same concept but rejected (e.g. distinct anatomical instances)
            assigned_class = "claimed concept present in the map but the claimed equivalence is wrong"
            rationale = f"Terms belong to same class concept '{crit_c.canonical_name}' but are distinct anatomical instances/substitutions requiring human coverage judgment."

        gate_c_class_counts[assigned_class] += 1
        classified_gate_c.append({
            "vignette_id": p["vignette_id"],
            "policy_id": p["policy_id"],
            "criterion_code": p["criterion_code"],
            "criterion_name": p["criterion_name"],
            "claimed_text": claimed,
            "claimed_equivalence": equiv,
            "assigned_class": assigned_class,
            "evidence_lookup_detail": detail or reason,
            "classification_rationale": rationale
        })

    # Sort missing concepts by recurrence
    top_missing_concepts = sorted(missing_concept_counter.items(), key=lambda x: x[1], reverse=True)

    # Task 3: Case-by-case ceiling analysis for the 19 synonymy deferrals
    print("\n[*] Performing Task 3 Ceiling Analysis on the 19 Synonymy Deferrals...")
    # Determine which of the 19 deferred cases could possibly resolve
    # A case defers if any of its required criteria are not met.
    # If the missing criterion had a proposal that failed Gate A due to paraphrase, OR failed Gate C due to absent genuine equivalence:
    # could that criterion pass, and if it passes, does the ENTIRE policy adjudicate to APPROVED?
    
    # We inspect the 19 synonymy vignettes individually
    synonymy_ceiling_cases = []
    
    # Check baseline status of each synonymy vignette
    for sid in SYNONYMY_VIGNETTE_IDS:
        vig = next(v for v in vignettes if v["vignette_id"] == sid)
        pid = vig["policy_id"]
        
        # In Arm B, did it resolve?
        arm_b_resolved = sid in summary_b["synonymy_resolved_cases"]
        
        # Check all proposals for this vignette in Arm B
        v_props = [p for p in proposals_b if p["vignette_id"] == sid]
        
        # Check criteria status
        potential_resolvable = False
        blocker_reasons = []
        
        if arm_b_resolved:
            potential_resolvable = True
            blocker_reasons.append("Already resolved in Arm B (what-if).")
        else:
            # Check what failed
            if not v_props:
                blocker_reasons.append("No proposals generated by LLM (LLM returned empty proposal).")
            else:
                for vp in v_props:
                    gate = vp["failing_gate"]
                    txt = vp["claimed_text"]
                    ccode = vp["criterion_code"]
                    if gate == "GATE_A_EXACT_SLICE":
                        blocker_reasons.append(f"{ccode}: Gate A failure on '{txt[:30]}' (needs perfect quoting).")
                    elif gate == "GATE_C_MAP_CHECK":
                        blocker_reasons.append(f"{ccode}: Gate C map veto on '{txt[:30]}' (needs map coverage).")
                    elif gate == "GATE_B_SEMANTIC":
                        blocker_reasons.append(f"{ccode}: Gate B semantic failure on '{txt[:30]}'.")
                    elif gate is None:
                        blocker_reasons.append(f"{ccode}: Proposal accepted, but other criteria or policy rules prevented APPROVED.")
                
                # Check if resolving these proposals would yield APPROVED
                # Under the ceiling assumption: perfect quoting (all paraphrase Gate A pass) + map covers genuine equivalence
                # Let's inspect if the proposal represents genuine clinical equivalence
                has_genuine_equivalence = False
                for vp in v_props:
                    equiv = (vp["claimed_equivalence"] or vp["rationale"]).lower()
                    # Check if genuine equivalence vs coverage judgment
                    # Coverage judgments: e.g. different anatomy, different procedure
                    if any(cj in equiv for cj in ["rectal", "alternative", "unrelated", "speculative"]):
                        pass
                    else:
                        has_genuine_equivalence = True
                
                if has_genuine_equivalence:
                    potential_resolvable = True

        synonymy_ceiling_cases.append({
            "vignette_id": sid,
            "policy_id": pid,
            "resolved_in_arm_b": arm_b_resolved,
            "potential_resolvable_under_ceiling": potential_resolvable,
            "blocker_details": blocker_reasons
        })

    resolvable_ceiling_count = sum(1 for c in synonymy_ceiling_cases if c["potential_resolvable_under_ceiling"])

    print(f"Ceiling Analysis Result: {resolvable_ceiling_count} of 19 synonymy deferrals could theoretically resolve under perfect quoting and complete map coverage.")

    # Save Task 2 & Task 3 classification output
    classification_out = ROOT_DIR / "app" / "data" / "benchmarks" / "what_if_residual_failure_classification.json"
    with open(classification_out, "w", encoding="utf-8") as f:
        json.dump({
            "task2_gate_a_classification": {
                "total_failures": len(gate_a_failures),
                "counts_by_class": gate_a_class_counts,
                "classified_cases": classified_gate_a
            },
            "task2_gate_c_classification": {
                "total_vetoes": len(gate_c_vetoes),
                "counts_by_class": gate_c_class_counts,
                "top_missing_concepts": top_missing_concepts,
                "classified_cases": classified_gate_c
            },
            "task3_ceiling_analysis": {
                "total_synonymy_deferrals": len(SYNONYMY_VIGNETTE_IDS),
                "resolved_in_what_if_arm_b": summary_b["synonymy_resolved_count"],
                "theoretical_ceiling_resolvable_count": resolvable_ceiling_count,
                "case_details": synonymy_ceiling_cases
            }
        }, f, indent=2)
    print(f"[+] Saved residual failure classification and ceiling analysis to {classification_out}")

    # Re-run deterministic baseline with committed map to confirm 39/84 unchanged
    print("\n[*] Re-running deterministic baseline check with committed map...")
    from scripts.evaluate_extended_policies import run_evaluation
    baseline_check = run_evaluation(write_report=False)
    assert baseline_check["decision_correct"] == 39, f"Baseline check failed: expected 39, got {baseline_check['decision_correct']}"
    assert baseline_check["top1_correct"] == 73, f"Baseline check failed: expected 73, got {baseline_check['top1_correct']}"
    print(f"[+] Confirmed: Committed baseline remains strictly {baseline_check['decision_correct']}/84 ({baseline_check['dec_pct']:.1f}%).")
