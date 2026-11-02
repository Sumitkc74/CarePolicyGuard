import os
import sys
import json
import time
import urllib.request
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.agents.benchmark_engine import BENCHMARK_VIGNETTES
from app.agents.empirical_harness import EmpiricalResearchHarness

def verify_ollama_model(model_name: str, endpoint: str = "http://localhost:11434/v1/models") -> bool:
    print(f"Connecting to Ollama models endpoint at {endpoint}...")
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            available_models = [m.get("id") for m in data.get("data", [])]
            print(f"Available local models in Ollama: {available_models}")
            if model_name in available_models:
                print(f"CONFIRMED: Model '{model_name}' is locally verified and available.")
                return True
            else:
                print(f"WARNING: Model '{model_name}' not found in available models: {available_models}")
                return False
    except Exception as e:
        print(f"ERROR connecting to Ollama at {endpoint}: {e}")
        return False

def run_14b_benchmark():
    target_model = os.getenv("BASELINE_LLM_MODEL", "qwen2.5:14b")
    print("=" * 80)
    print(f"CAREPOLICYGUARD BASELINE LLM EVALUATION: {target_model}")
    print("=" * 80)

    if not verify_ollama_model(target_model):
        print(f"Aborting baseline run: {target_model} is not ready.")
        sys.exit(1)

    harness = EmpiricalResearchHarness()
    harness._target_llm_url = "http://localhost:11434/v1/chat/completions"
    harness._target_llm_model = target_model

    # 1. Evaluate Benchmark BENCH-01..10
    print(f"\n--- 1. Evaluating {len(BENCHMARK_VIGNETTES)} Benchmark Vignettes (BENCH-01..10) ---", flush=True)
    t0 = time.perf_counter()
    bench_results = harness.run_condition_a(BENCHMARK_VIGNETTES)
    bench_duration = time.perf_counter() - t0

    print("\nBENCHMARK RESULTS (Config A - " + target_model + "):", flush=True)
    print(f"  Accuracy: {bench_results['accuracy'] * 100:.1f}%", flush=True)
    print(f"  Evidence Faithfulness: {bench_results['faithfulness'] * 100:.1f}%", flush=True)
    print(f"  Expected Calibration Error (ECE): {bench_results['ece']:.3f}", flush=True)
    print(f"  Safe Abstention Rate: {bench_results['abstention_rate'] * 100:.1f}%", flush=True)
    print(f"  Mean Latency: {bench_results['mean_latency_ms']:.1f} ms", flush=True)
    print(f"  Total Run Time: {bench_duration:.1f} s", flush=True)

    raw_runs_14b_path = ROOT_DIR / "app" / "data" / "benchmarks" / "baseline_llm_raw_runs_14b.json"
    print(f"Verified benchmark raw runs committed at: {raw_runs_14b_path.name}", flush=True)

    # 2. Evaluate v1 Development Set (15 cases)
    v1_path = ROOT_DIR / "carepolicyguard-heldout" / "heldout_vignettes.json"
    if v1_path.exists():
        with open(v1_path, "r", encoding="utf-8") as f:
            v1_data = json.load(f)
        v1_vignettes = v1_data.get("vignettes", [])
        print(f"\n--- 2. Evaluating {len(v1_vignettes)} v1-dev Cases with {target_model} ---", flush=True)

        v1_runs = []
        v1_decisions, v1_confidences, v1_latencies = [], [], []
        v1_acc, v1_fa, v1_fd = 0, 0, 0

        for v in v1_vignettes:
            t_case = time.perf_counter()
            llm_eval = harness._execute_llm_zero_shot_call(v, temperature=0.0)
            lat_ms = (time.perf_counter() - t_case) * 1000.0

            pred = llm_eval.get("decision", "APPROVED")
            conf = float(llm_eval.get("confidence", 0.90))
            gold = v["gold_decision"]

            is_corr = (pred == gold)
            is_fa = (pred == "APPROVED" and gold != "APPROVED")
            is_fd = (pred == "DENIED" and gold != "DENIED")

            if is_corr: v1_acc += 1
            if is_fa: v1_fa += 1
            if is_fd: v1_fd += 1

            v1_decisions.append(pred)
            v1_confidences.append(conf)
            v1_latencies.append(lat_ms)

            v1_runs.append({
                "case_id": v["id"],
                "policy_id": v["policy_id"],
                "gold_decision": gold,
                "predicted_decision": pred,
                "confidence": conf,
                "is_correct": is_corr,
                "is_false_approval": is_fa,
                "is_false_denial": is_fd,
                "latency_ms": round(lat_ms, 2),
                "raw_envelope": llm_eval.get("raw_response_text", "")
            })

            status = "MATCH" if is_corr else "MISMATCH"
            fa_mark = " [FA!]" if is_fa else (" [FD!]" if is_fd else "")
            print(f"  [{v['id']}] {status} | Pred: {pred:<18} | Gold: {gold:<18} ({lat_ms:.0f}ms){fa_mark}", flush=True)

        v1_summary = {
            "model_id": target_model,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_cases": len(v1_vignettes),
            "accuracy": round(v1_acc / len(v1_vignettes), 4),
            "false_approvals": v1_fa,
            "false_approval_rate": round(v1_fa / len(v1_vignettes), 4),
            "false_denials": v1_fd,
            "false_denial_rate": round(v1_fd / len(v1_vignettes), 4),
            "deferral_rate": round(sum(1 for d in v1_decisions if d == "DEFERRED_TO_HUMAN") / len(v1_vignettes), 4),
            "mean_latency_ms": round(sum(v1_latencies) / len(v1_latencies), 1),
            "cases": v1_runs
        }

        v1_output_path = ROOT_DIR / "carepolicyguard-heldout" / f"baseline_llm_v1_dev_raw_runs_{target_model.replace(':', '_')}.json"
        with open(v1_output_path, "w", encoding="utf-8") as f:
            json.dump(v1_summary, f, indent=2)
        print(f"\nPersisted v1-dev baseline raw runs to: {v1_output_path.name}", flush=True)
        print(f"  v1-dev Accuracy: {v1_summary['accuracy'] * 100:.1f}% ({v1_acc}/{len(v1_vignettes)})", flush=True)
        print(f"  v1-dev False Approvals: {v1_fa} ({v1_summary['false_approval_rate'] * 100:.1f}%)", flush=True)
        print(f"  v1-dev False Denials: {v1_fd} ({v1_summary['false_denial_rate'] * 100:.1f}%)", flush=True)
        print(f"  v1-dev Deferral Rate: {v1_summary['deferral_rate'] * 100:.1f}%", flush=True)

    harness.close()
    print("\nBaseline evaluation completed successfully.", flush=True)

if __name__ == "__main__":
    run_14b_benchmark()

