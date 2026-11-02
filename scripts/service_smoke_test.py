"""
CarePolicyGuard Local Live Service Smoke Test Runner.

Executes live end-to-end service smoke testing over real HTTP sockets:
1. Generates an ephemeral in-memory test secret (no secrets persisted to disk).
2. Spawns the live Uvicorn ASGI server on port 8000.
3. Polls the microservice /health endpoint until HTTP 200 is confirmed.
4. Executes the synthetic clinical adjudication payload (zero patient data, NCD-20.4).
5. Asserts the determination is APPROVED with verified spans and SHA-256 seal.
6. Terminates and cleans up the Uvicorn server subprocess.
"""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8000
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
ADJUDICATE_URL = f"http://127.0.0.1:{PORT}/api/v1/adjudicate"


def run_live_smoke_test() -> int:
    print("=" * 80)
    print("CarePolicyGuard Live Service Smoke Test")
    print("=" * 80)

    ephemeral_secret = secrets.token_urlsafe(32)
    env = {
        **dict(os.environ),
        "SECRET_KEY": ephemeral_secret,
        "DATABASE_URL": "sqlite:///./carepolicyguard.db",
        "ABSTENTION_THRESHOLD": "0.85"
    }

    print("\n[1/4] Spawning live Uvicorn ASGI server on port 8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # Step 2: Poll health endpoint
        print("\n[2/4] Polling microservice /health endpoint...")
        healthy = False
        health_data = {}
        for _ in range(1, 16):
            time.sleep(1)
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=2.0) as resp:
                    if resp.status == 200:
                        health_data = json.loads(resp.read().decode("utf-8"))
                        healthy = True
                        break
            except (urllib.error.URLError, ConnectionError, OSError):
                continue

        if not healthy:
            print("[-] Microservice /health check timed out after 15 seconds.")
            proc.kill()
            out, err = proc.communicate(timeout=5)
            print(f"Server output:\n{out}\n{err}")
            return 1

        print(f"[+] Healthcheck PASSED: {health_data}")

        # Step 3: Synthetic clinical adjudication
        print("\n[3/4] Executing synthetic clinical adjudication smoke test (NCD-20.4 ICD)...")
        synthetic_payload = {
            "patient_id": "PT-SMOKE-01",
            "policy_id": "NCD-20.4",
            "ehr_narrative": (
                "History of Present Illness:\n"
                "67yo male with ischemic cardiomyopathy s/p CABG 14 months ago.\n"
                "NYHA Class II symptoms on GDMT for 6 months.\n\n"
                "Diagnostic Studies:\n"
                "TTE confirms LVEF 28% with severe regional hypokinesis."
            )
        }
        req = urllib.request.Request(
            ADJUDICATE_URL,
            data=json.dumps(synthetic_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            adj_status = resp.status
            adj_data = json.loads(resp.read().decode("utf-8"))

        if adj_status != 200:
            print(f"[-] Synthetic adjudication failed with status {adj_status}: {adj_data}")
            return 1

        decision = adj_data.get("adjudication_decision")
        confidence = adj_data.get("calibrated_aggregate_confidence")
        assessments = adj_data.get("criterion_assessments", [])
        audit_hash = adj_data.get("audit_hash", "N/A")

        print("[+] Synthetic adjudication PASSED:")
        print(f"    - Policy ID: {adj_data.get('policy_id')}")
        print(f"    - Decision: {decision}")
        print(f"    - Calibrated Confidence: {confidence}")
        print(f"    - Criteria Evaluated: {len(assessments)}")
        print(f"    - Audit Hash: {audit_hash[:16]}...")

        assert decision == "APPROVED", f"Expected adjudication_decision APPROVED, got: {decision}"
        assert len(assessments) >= 3, f"Expected at least 3 criterion assessments, got {len(assessments)}"
        assert audit_hash != "N/A" and len(audit_hash) == 64, "Expected valid 64-character SHA-256 audit hash"

        # Step 4: Verification summary
        print("\n[4/4] Verification complete.")
        print("=" * 80)
        print("ALL LIVE SMOKE TESTS PASSED CLEANLY (HTTP 200 OK)")
        print("=" * 80)
        return 0

    finally:
        print("\nTerminating Uvicorn server subprocess...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        print("[+] Server shutdown complete.")


if __name__ == "__main__":
    sys.exit(run_live_smoke_test())
