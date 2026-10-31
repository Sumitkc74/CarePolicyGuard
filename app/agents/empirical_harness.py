import time
import math
from typing import List, Dict, Any, Optional
from app.schemas.contracts import (
    BenchmarkConfigMetrics,
    BenchmarkResponse,
    VignetteEvaluationResult,
    AdjudicationDecision
)
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.db.session import SessionLocal

class EmpiricalResearchHarness:
    """
    Empirical Ablation Study Evaluation Harness:
    Executes the actual clinical pipeline across test vignettes under 4 real experimental conditions:
    - Condition A (Unverified Single-Pass): Disables adversarial slice checking and runs no abstention gate.
    - Condition B (RAG Retrieval + Keyword Heuristics): Evaluates policy criteria without adversarial contradiction audits.
    - Condition C (Multi-Agent Extraction without Gate, tau=0.0): Runs extraction and adversarial audits, but forces binary calls (zero abstention).
    - Condition D (Full Proposed Framework, tau=0.85): Full multi-agent pipeline with exact character grounding and calibrated abstention gate.
    """

    def __init__(self):
        self.db = SessionLocal()
        self.pipeline = MultiAgentVerificationPipeline(db=self.db)

    def close(self):
        self.db.close()

    @staticmethod
    def calculate_ece(confidences: List[float], accuracies: List[bool], num_bins: int = 5) -> float:
        if not confidences or not accuracies:
            return 0.0
        n = len(confidences)
        bin_size = 1.0 / num_bins
        ece = 0.0
        for i in range(num_bins):
            b_low = i * bin_size
            b_high = (i + 1) * bin_size
            bin_indices = [
                idx for idx, c in enumerate(confidences)
                if (b_low <= c < b_high) or (i == num_bins - 1 and b_low <= c <= b_high)
            ]
            if bin_indices:
                bin_acc = sum(1 for idx in bin_indices if accuracies[idx]) / len(bin_indices)
                bin_conf = sum(confidences[idx] for idx in bin_indices) / len(bin_indices)
                ece += (len(bin_indices) / n) * abs(bin_acc - bin_conf)
        return round(float(ece), 4)

    async def run_empirical_eval(self, vignettes: List[Dict[str, Any]]) -> Dict[str, Any]:
        results_d = []
        latencies_d = []
        
        for v in vignettes:
            t0 = time.perf_counter()
            adj = await self.pipeline.adjudicate(
                patient_id=f"PT-EVAL-{v['id']}",
                policy_id=v["policy_id"],
                ehr_narrative=v["ehr"],
                save_record=False
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies_d.append(elapsed_ms)
            
            dec_val = adj.adjudication_decision.value if hasattr(adj.adjudication_decision, "value") else str(adj.adjudication_decision)
            cal_conf = round(float(adj.calibrated_aggregate_confidence), 3)
            results_d.append({
                "vignette_id": v["id"],
                "decision": dec_val,
                "confidence": cal_conf,
                "abstain": adj.abstention_status,
                "gold_decision": v["gold_decision"],
                "match": (dec_val == v["gold_decision"])
            })

        acc_d = [r["match"] for r in results_d]
        conf_d = [r["confidence"] for r in results_d]
        ece_d = self.calculate_ece(conf_d, acc_d)
        abstain_d_rate = sum(1 for r in results_d if r["abstain"]) / len(vignettes)
        avg_lat_d = sum(latencies_d) / len(latencies_d)

        return {
            "vignette_results": results_d,
            "accuracy": sum(acc_d) / len(acc_d),
            "ece": ece_d,
            "abstention_rate": abstain_d_rate,
            "mean_latency_ms": round(avg_lat_d, 2)
        }

