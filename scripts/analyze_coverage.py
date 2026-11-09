"""
Coverage analysis for Task 1(c):
Examine the 43 Gate C map rejections and 2 accepted proposals from the 84 dev vignette run.
"""
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.declarative_engine import DeclarativePolicyEngine
from app.agents.llm_proposer import LLMProposalAgent

def analyze_coverage():
    report_path = ROOT_DIR / "app" / "data" / "benchmarks" / "bench_v1_llm_safety_report.json"
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print("Top-level summary from bench_v1_llm_safety_report.json:")
    print("  Total calls:", data.get("total_calls"))
    print("  Proposals generated:", data.get("proposals_generated"))
    print("  Gate A rejections:", data.get("gate_a_rejections"))
    print("  Gate B rejections:", data.get("gate_b_rejections"))
    print("  Gate C map rejections:", data.get("gate_c_map_rejections"))
    print("  Gate C vetoes:", data.get("gate_c_vetoes"))
    print("  Proposals accepted:", data.get("proposals_accepted"))
    
    # Run the dev cases with logging of each proposal and Gate evaluation
    dev_path = ROOT_DIR / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        dev_cases = json.load(f)

    # Re-evaluate the 2 accepted proposals and the Gate C rejections
    # Let's inspect which cases generated the 2 accepted proposals
    print("\nTracing which cases produced the 2 accepted proposals:")
    # We can check by running through the pipeline with detailed audit trail
    pipeline = MultiAgentVerificationPipeline()
    pipeline.llm_proposer.enabled = True
    pipeline.llm_proposer.endpoint_url = "http://127.0.0.1:11434/v1/chat/completions"
    pipeline.llm_proposer.model_name = "qwen2.5:3b"
    pipeline.llm_proposer.timeout_seconds = 20.0
    
    gate_c_cases = []
    accepted_cases = []

    for c in dev_cases:
        res = pipeline.adjudicate_sync(
            patient_id=c["vignette_id"],
            policy_id=c["policy_id"],
            ehr_narrative=c["ehr_narrative"],
            execution_mode="declarative",
            save_record=False
        )
        meta = res.llm_proposal_metadata
        if meta and meta.get("gate_c_vetoes", 0) > 0 or (res.agentic_audit_trail and any("Gate C" in str(x) for x in res.agentic_audit_trail)):
            gate_c_cases.append((c["vignette_id"], c["policy_id"]))
        if meta and meta.get("proposals_accepted", 0) > 0:
            accepted_cases.append((c["vignette_id"], c["policy_id"], res.adjudication_decision.value))

    print(f"Accepted cases found: {len(accepted_cases)} -> {accepted_cases}")
    print(f"Gate C cases found: {len(gate_c_cases)}")

if __name__ == "__main__":
    analyze_coverage()
