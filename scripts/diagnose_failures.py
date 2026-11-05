import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
DEV_VIGNETTES_FILE = POLICIES_DIR / "dev_vignettes_extended.json"

from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.hybrid_retriever import HybridPolicyRetriever

retriever = HybridPolicyRetriever(db=None)
pipeline = MultiAgentVerificationPipeline(db=None)

with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
    vignettes = json.load(f)

print("=== RETRIEVAL FAILURES (Top-1 != Intended) ===")
for v in vignettes:
    pid = v["policy_id"]
    narrative = v["ehr_narrative"]
    cands = retriever.retrieve_hybrid(narrative, top_k=5)
    top1 = cands[0]["policy_id"] if cands else "NONE"
    top3 = [c["policy_id"] for c in cands[:3]]
    if top1 != pid:
        print(f"[{v['vignette_id']}] Intended: {pid} | Top-1: {top1} (score={cands[0]['hybrid_score']:.3f}) | In Top-3: {pid in top3}")
        for c in cands[:3]:
            print(f"    cand: {c['policy_id']} bm25={c.get('bm25_score', 0):.3f} dense={c.get('dense_score', 0):.3f} hybrid={c.get('hybrid_score', 0):.3f}")

print("\n=== ADJUDICATION FAILURES (Sample of 10) ===")
count = 0
for v in vignettes:
    pid = v["policy_id"]
    exp = v["expected_decision"]
    narrative = v["ehr_narrative"]
    adj = pipeline.adjudicate_sync(patient_id="PT-TEST", policy_id=pid, ehr_narrative=narrative, execution_mode="declarative", save_record=False)
    act = adj.adjudication_decision.value
    if act != exp and count < 10:
        count += 1
        print(f"[{v['vignette_id']}] Exp: {exp} | Act: {act} | Status: {adj.abstention_status} | Reason: {adj.abstention_reason}")
        print(f"    Sufficiency: {adj.criteria_sufficiency_score:.2f} | Met: {adj.met_criteria_count} | Unmet: {adj.unmet_criteria_count}")
        for ev in adj.extracted_evidence:
            print(f"      Crit: {ev.criterion_id} | Status: {ev.evidence_status} | Found: {ev.extracted_value} | Conf: {ev.confidence_score}")
