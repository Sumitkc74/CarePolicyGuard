"""
Controlled experiment for Task 1(b):
Compares current production prompt vs. explicit verbatim prompt variant with worked example
on the 19 controlled synonymy failure cases using local qwen2.5:3b.
Both arms are evaluated identically using evaluate_proposal_through_gates (Gate A: exact slice).
"""
import sys
import time
import json
import re
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.agents.llm_proposer import LLMProposalAgent, LLMProposedSpan
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

def run_prompt_experiment():
    dev_path = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        all_dev = json.load(f)

    # Filter strictly to the 19 synonymy failure cases
    cases = [c for c in all_dev if c["vignette_id"] in SYNONYMY_VIGNETTE_IDS]
    assert len(cases) == 19, f"Expected 19 cases, found {len(cases)}"
    print(f"[*] Running prompt experiment on {len(cases)} controlled synonymy failure cases...")

    agent_base = LLMProposalAgent(
        endpoint_url="http://127.0.0.1:11434/v1/chat/completions",
        model_name="qwen2.5:3b",
        timeout_seconds=30.0,
        max_calls_per_case=10,
        max_time_per_case_seconds=60.0
    )
    agent_base.enabled = True

    # Warmup call
    try:
        agent_base._execute_network_request({
            "model": "qwen2.5:3b",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 2
        })
    except Exception:
        pass

    # Extract all unmet inclusion criteria for these cases
    evaluation_pairs = []
    for case in cases:
        policy = DeclarativePolicyEngine.load_policy(case["policy_id"])
        assessments = DeclarativePolicyEngine.evaluate_policy(policy, case["ehr_narrative"])
        for ass in assessments:
            if ass.status.value in ["INSUFFICIENT_EVIDENCE", "NOT_MET"] and not ass.is_exclusion:
                crit_obj = [c for c in policy.criteria if c.criterion_code == ass.criterion_code][0]
                evaluation_pairs.append((case, crit_obj))

    print(f"[*] Total criterion-vignette evaluation pairs: {len(evaluation_pairs)}")

    # Statistics tracking
    stats_base = {"calls": 0, "proposals": 0, "gate_a_pass": 0, "gate_a_fail": 0, "accepted": 0, "decision_changes": 0}
    stats_variant = {"calls": 0, "proposals": 0, "gate_a_pass": 0, "gate_a_fail": 0, "accepted": 0, "decision_changes": 0}

    # 1. Evaluate with Production Prompt
    print("\n--- Arm 1: Evaluating Production Prompt ---")
    for case, crit in evaluation_pairs:
        agent_base.reset_case_budget()
        stats_base["calls"] += 1
        crit_dict = {
            "criterion_code": crit.criterion_code,
            "name": crit.name,
            "description": crit.description,
            "criterion_type": crit.criterion_type.value,
            "is_exclusion": crit.is_exclusion
        }
        res = agent_base.propose_spans_sync(
            sanitized_ehr=case["ehr_narrative"],
            criterion=crit_dict,
            policy_id=case["policy_id"]
        )
        for prop in res.proposals:
            stats_base["proposals"] += 1
            gate_res = agent_base.evaluate_proposal_through_gates(
                proposal=prop,
                sanitized_ehr=case["ehr_narrative"],
                criterion=crit_dict
            )
            # Gate A passes if and only if failing_gate is NOT "GATE_A_EXACT_SLICE"
            passed_gate_a = (gate_res.failing_gate != "GATE_A_EXACT_SLICE")
            if passed_gate_a:
                stats_base["gate_a_pass"] += 1
            else:
                stats_base["gate_a_fail"] += 1
            if gate_res.passed:
                stats_base["accepted"] += 1

    # 2. Evaluate with Prompt Variant (Explicit Verbatim + Worked Example)
    print("\n--- Arm 2: Evaluating Prompt Variant (Verbatim Instruction + Worked Example) ---")
    def prompt_variant_generator(ehr_text, ccode, cname, cdesc, ctype, is_excl):
        return (
            f"You are a clinical evidence extraction assistant for Medicare coverage evaluation.\n"
            f"CLINICAL NOTE:\n\"\"\"{ehr_text}\"\"\"\n\n"
            f"CRITERION:\n"
            f"- Code: {ccode}\n"
            f"- Name: {cname}\n"
            f"- Description: {cdesc}\n"
            f"- Type: {ctype}\n"
            f"- Is Exclusion: {is_excl}\n\n"
            f"TASK:\n"
            f"Find any verbatim substring in the clinical note that provides evidence expressing the SAME CLINICAL CONCEPT as this criterion.\n"
            f"CRITICAL INSTRUCTION: You must quote the note exactly. Do NOT rephrase, do NOT summarize, do NOT correct spelling. claimed_text MUST be a character-for-character exact quote from the clinical note above.\n\n"
            f"WORKED EXAMPLE:\n"
            f'Note snippet: "Patient with severe dyspnea on minimal exertion, NYHA class III functional status."\n'
            f'Criterion: "NYHA Class III or IV heart failure symptoms"\n'
            f'Correct claimed_text: "NYHA class III functional status" (exact substring from note snippet).\n'
            f'Incorrect claimed_text: "Patient has Class 3 symptoms" (rephrased - will be rejected).\n\n'
            f"Return a JSON object with this exact structure:\n"
            f"{{\n"
            f'  "proposals": [\n'
            f'    {{\n'
            f'      "claimed_text": "<exact verbatim quote from note>",\n'
            f'      "claimed_equivalence": "<canonical clinical concept from criterion>",\n'
            f'      "proposed_status": "MET" or "NOT_MET",\n'
            f'      "numeric_value": null or number,\n'
            f'      "numeric_unit": null or string,\n'
            f'      "rationale": "<brief explanation>"\n'
            f'    }}\n'
            f'  ]\n'
            f"}}\n"
            f"If no relevant text exists in the note, return {{\"proposals\": []}}.\n"
            f"Return ONLY valid JSON."
        )

    for case, crit in evaluation_pairs:
        stats_variant["calls"] += 1
        crit_dict = {
            "criterion_code": crit.criterion_code,
            "name": crit.name,
            "description": crit.description,
            "criterion_type": crit.criterion_type.value,
            "is_exclusion": crit.is_exclusion
        }
        var_prompt = prompt_variant_generator(
            case["ehr_narrative"],
            crit.criterion_code,
            crit.name,
            crit.description,
            crit.criterion_type.value,
            crit.is_exclusion
        )
        payload = {
            "model": "qwen2.5:3b",
            "messages": [
                {"role": "system", "content": "You are a specialized clinical audit engine. Respond with valid JSON only."},
                {"role": "user", "content": var_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 350
        }
        try:
            resp = agent_base._execute_network_request(payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = re.sub(r"^```[a-zA-Z]*\n", "", content)
                    content = re.sub(r"\n```$", "", content)
                parsed = json.loads(content)
                for item in parsed.get("proposals", []):
                    stats_variant["proposals"] += 1
                    claimed = str(item.get("claimed_text", "")).strip()
                    # System locates the span in the narrative identically to production
                    start, end = agent_base.locate_claimed_span(case["ehr_narrative"], claimed)
                    if start == -1:
                        start, end = 0, 0
                    prop_var = LLMProposedSpan(
                        criterion_code=crit.criterion_code,
                        proposed_status=item.get("proposed_status", "MET"),
                        claimed_text=claimed,
                        char_start=int(start),
                        char_end=int(end),
                        numeric_value=item.get("numeric_value"),
                        numeric_unit=item.get("numeric_unit"),
                        claimed_equivalence=item.get("claimed_equivalence", item.get("rationale", "")),
                        rationale=item.get("rationale", "LLM proposed evidence")
                    )
                    gate_res_var = agent_base.evaluate_proposal_through_gates(
                        proposal=prop_var,
                        sanitized_ehr=case["ehr_narrative"],
                        criterion=crit_dict
                    )
                    passed_gate_a = (gate_res_var.failing_gate != "GATE_A_EXACT_SLICE")
                    if passed_gate_a:
                        stats_variant["gate_a_pass"] += 1
                    else:
                        stats_variant["gate_a_fail"] += 1
                    if gate_res_var.passed:
                        stats_variant["accepted"] += 1
        except Exception as e:
            print(f"Error on variant: {e}")

    # Output results
    print("\n" + "=" * 60)
    print("TASK 1(b) PROMPT VARIANT RESULTS (19 SYNONYMY CASES)")
    print("=" * 60)
    pass_rate_base = (stats_base['gate_a_pass'] / max(1, stats_base['proposals'])) * 100.0
    pass_rate_var = (stats_variant['gate_a_pass'] / max(1, stats_variant['proposals'])) * 100.0

    print(f"Production Prompt: Calls={stats_base['calls']}, Proposals={stats_base['proposals']}, Gate A Pass={stats_base['gate_a_pass']}, Gate A Fail={stats_base['gate_a_fail']}, Accepted={stats_base['accepted']}, DecChanges={stats_base['decision_changes']}")
    print(f"  Production Prompt Gate A Pass Rate: {pass_rate_base:.1f}%")

    print(f"Variant Prompt:    Calls={stats_variant['calls']}, Proposals={stats_variant['proposals']}, Gate A Pass={stats_variant['gate_a_pass']}, Gate A Fail={stats_variant['gate_a_fail']}, Accepted={stats_variant['accepted']}, DecChanges={stats_variant['decision_changes']}")
    print(f"  Variant Prompt Gate A Pass Rate:    {pass_rate_var:.1f}%")
    print(f"  Difference (Margin): {pass_rate_var - pass_rate_base:+.1f}%")

    out_file = ROOT_DIR / "app" / "data" / "benchmarks" / "prompt_experiment_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "cases_evaluated": len(cases),
            "evaluation_pairs": len(evaluation_pairs),
            "production": stats_base,
            "variant": stats_variant,
            "pass_rate_production_pct": round(pass_rate_base, 2),
            "pass_rate_variant_pct": round(pass_rate_var, 2),
            "margin_pct": round(pass_rate_var - pass_rate_base, 2)
        }, f, indent=2)
    print(f"[*] Results saved to {out_file}")

if __name__ == "__main__":
    run_prompt_experiment()
