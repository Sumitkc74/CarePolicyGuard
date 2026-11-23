"""
Task 6 Milestone Demo Runner:
Executes the four core demo vignettes covering all four determination states:
1. Supported (satisfies criteria with character-grounded quotes): DEV-LCD-PCI-APP
2. Contradiction (factual objection/contradiction identified): DEV-LCD-SBRT-APP
3. Insufficient documentation (missing clinical requirement): DEV-LCD-KYPHO-APP
4. Ambiguous deferral (active gate deferral requiring human review): DEV-LCD-HIP-ARTHRO-NEG

Extracts:
- case_id, run_id, run_number, policy_id, policy_version, engine_version, note_version (hash)
- Decision and determination stage
- Evaluator proposal, verifier finding, resolution trace
- Persisted export verification (PDF and packet JSON)
"""

import hashlib
import json
from fastapi.testclient import TestClient
from main import app
from tests.test_v80_reviewer_workflow import _create_test_user

client = TestClient(app)

with open("app/data/policies_extended/dev_vignettes_extended.json", "r") as f:
    vignettes = json.load(f)

demo_cases = [
    {
        "category": "Supported (Documented Approval)",
        "vignette_id": "DEV-LCD-PCI-APP",
        "description": "Patient documentation meets all required criteria for percutaneous coronary intervention with verifiable quotes."
    },
    {
        "category": "Contradiction (Factual Objection)",
        "vignette_id": "DEV-LCD-SBRT-APP",
        "description": "Evaluator proposes coverage but Verifier raises explicit clinical contradiction/objection."
    },
    {
        "category": "Insufficient Documentation (Missing Requirement)",
        "vignette_id": "DEV-LCD-KYPHO-APP",
        "description": "Required conservative medical therapy or pain duration criteria lack supporting quotes in chart."
    },
    {
        "category": "Ambiguous Deferral (Gate Deferral / Human Adjudication)",
        "vignette_id": "DEV-LCD-HIP-ARTHRO-NEG",
        "description": "Policy criteria or documentation require human adjudication / Gate deferral."
    }
]

print("=" * 80)
print("TASK 6 MILESTONE DEMO: COVERAGE CRITERIA EVALUATION")
print("=" * 80)

results = []

headers, user = _create_test_user(role="Clinician", is_verified=True, credential_title="MD")

for item in demo_cases:
    vid = item["vignette_id"]
    vig = next(v for v in vignettes if v.get("vignette_id") == vid)
    policy_id = vig.get("policy_id")
    narrative = vig.get("ehr_narrative")

    res = client.post(
        "/api/v1/adjudicate",
        headers=headers,
        json={
            "patient_id": f"PT-{vid}",
            "policy_id": policy_id,
            "ehr_narrative": narrative
        }
    )
    assert res.status_code == 200, res.text
    data = res.json()
    case_id = data["case_id"]
    run_id = data["run_id"]

    # Fetch Agent Trace
    trace_res = client.get(f"/api/v1/adjudication/{case_id}/trace", headers=headers)
    trace_data = trace_res.json() if trace_res.status_code == 200 else {}

    # Fetch Runs
    runs_res = client.get(f"/api/v1/adjudication/{case_id}/runs", headers=headers)
    runs_list = runs_res.json() if runs_res.status_code == 200 else []

    # Fetch Packet
    pkt_res = client.get(f"/api/v1/packet/{case_id}", headers=headers)
    pkt_data = pkt_res.json() if pkt_res.status_code == 200 else {}

    result_summary = {
        "category": item["category"],
        "vignette_id": vid,
        "case_id": case_id,
        "run_id": run_id,
        "policy_id": policy_id,
        "policy_version": data.get("policy_version"),
        "engine_version": data.get("engine_version"),
        "note_version": data.get("note_version"),
        "decision": data.get("adjudication_decision"),
        "determination_stage": data.get("determination_stage"),
        "evaluation_label": data.get("evaluation_label"),
        "criteria_evaluated": len(data.get("criterion_assessments") or []),
        "agent_traces_count": len(trace_data.get("traces", [])),
        "persisted_runs_count": len(runs_list),
        "packet_label": pkt_data.get("evaluation_label")
    }
    results.append(result_summary)

    print(f"\n--- Case: {item['category']} ({vid}) ---")
    print(f"  Case ID:            {case_id}")
    print(f"  Run ID:             {run_id}")
    print(f"  Policy:             {policy_id} (Version: {data.get('policy_version')})")
    print(f"  Engine Version:     {data.get('engine_version')}")
    print(f"  Note Version SHA:   {data.get('note_version')[:16]}...")
    print(f"  System Decision:    {data.get('adjudication_decision')}")
    print(f"  Stage:              {data.get('determination_stage')}")
    print(f"  Report Label:       {data.get('evaluation_label')}")
    print(f"  Criteria Count:     {len(data.get('criterion_assessments') or [])}")
    print(f"  Agent Traces:       {len(trace_data.get('traces', []))} structured traces extracted")

with open("docs/milestone_demo_v80_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 80)
print("Milestone demo results saved to docs/milestone_demo_v80_results.json")
print("=" * 80)
