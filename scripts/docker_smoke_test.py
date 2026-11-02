"""
CarePolicyGuard Containerized Deployment & Smoke Test Runner.

Executes end-to-end container verification on any host with Docker:
1. Validates Docker CLI and daemon availability.
2. Builds the multi-stage production container image.
3. Asserts .git repository metadata was excluded from the container image.
4. Starts container with ephemeral in-memory test secrets (no secrets persisted to disk).
5. Tests microservice /health endpoint.
6. Executes synthetic clinical adjudication with zero patient data.
7. Tears down and cleans up the container.
"""

import json
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

CONTAINER_NAME = "cpg-smoke-container"
IMAGE_TAG = "carepolicyguard:latest"
PORT = 8000
HEALTH_URL = f"http://localhost:{PORT}/health"
ADJUDICATE_URL = f"http://localhost:{PORT}/api/v1/adjudicate"


def run_cmd(cmd: list[str], timeout: int = 180) -> tuple[int, str, str]:
    """Runs a subprocess command and returns exit code, stdout, stderr."""
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout
    )
    return res.returncode, res.stdout, res.stderr


def check_docker_available() -> bool:
    """Checks whether the docker CLI exists and daemon is reachable."""
    if not shutil.which("docker"):
        print("[-] Docker CLI ('docker') not found in PATH.")
        return False
    ret, _, _ = run_cmd(["docker", "info"])
    if ret != 0:
        print("[-] Docker CLI found, but Docker daemon is not running or accessible.")
        return False
    print("[+] Docker daemon is available and responding.")
    return True


def execute_smoke_test() -> int:
    print("=" * 80)
    print("CarePolicyGuard Automated Container Smoke Test")
    print("=" * 80)

    if not check_docker_available():
        print("\nNotice: Container runtime is not available in this host environment.")
        print("To run this test live, execute on a machine or CI environment with Docker installed.")
        return 2

    # Step 1: Clean up any leftover test containers
    print("\n[1/6] Cleaning up pre-existing test containers...")
    run_cmd(["docker", "rm", "-f", CONTAINER_NAME])

    # Step 2: Build container image
    print("\n[2/6] Building container image (Dockerfile multi-stage build)...")
    t0 = time.perf_counter()
    ret, out, err = run_cmd(["docker", "build", "-t", IMAGE_TAG, "."])
    if ret != 0:
        print(f"[-] Image build failed with exit code {ret}:\n{err}\n{out}")
        return 1
    build_time = time.perf_counter() - t0
    print(f"[+] Container image built successfully ({build_time:.2f}s).")

    # Step 3: Assert .git exclusion
    print("\n[3/6] Verifying .dockerignore excludes repository metadata (.git)...")
    ret, out, err = run_cmd([
        "docker", "run", "--rm", IMAGE_TAG,
        "sh", "-c", "test ! -d /app/.git"
    ])
    if ret != 0:
        print("[-] Security check FAILED: /app/.git was found inside the container image!")
        return 1
    print("[+] Security check PASSED: /app/.git is confirmed absent from the container image.")

    # Step 4: Start container with ephemeral test secret
    print("\n[4/6] Launching container with ephemeral test secret...")
    ephemeral_secret = secrets.token_urlsafe(32)
    ret, out, err = run_cmd([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{PORT}:8000",
        "-e", f"SECRET_KEY={ephemeral_secret}",
        "-e", "DATABASE_URL=sqlite:///./data/smoke_test.db",
        "-e", "ABSTENTION_THRESHOLD=0.85",
        IMAGE_TAG
    ])
    if ret != 0:
        print(f"[-] Container start failed:\n{err}")
        return 1

    try:
        # Step 5: Poll health endpoint
        print("\n[5/6] Polling /health microservice healthcheck...")
        healthy = False
        health_data: dict[str, Any] = {}
        for attempt in range(1, 16):
            time.sleep(1)
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=3.0) as resp:
                    if resp.status == 200:
                        health_data = json.loads(resp.read().decode("utf-8"))
                        healthy = True
                        break
            except (urllib.error.URLError, ConnectionError, OSError):
                continue

        if not healthy:
            print("[-] Container /health check timed out after 15 seconds.")
            _, logs, _ = run_cmd(["docker", "logs", CONTAINER_NAME])
            print(f"Container logs:\n{logs}")
            return 1
        print(f"[+] Healthcheck PASSED: {health_data}")

        # Step 6: Synthetic clinical adjudication (zero patient data)
        print("\n[6/6] Executing synthetic clinical adjudication smoke test (NCD-20.4 ICD)...")
        synthetic_payload = {
            "patient_id": "PT-SMOKE-CONTAINER-01",
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

        print("[+] Synthetic adjudication PASSED:")
        print(f"    - Policy ID: {adj_data.get('policy_id')}")
        print(f"    - Determination: {adj_data.get('determination')}")
        print(f"    - Verified Spans: {len(adj_data.get('evidence_spans', []))}")
        print(f"    - Audit Hash: {adj_data.get('audit_trail', {}).get('audit_hash', 'N/A')[:16]}...")

        print("\n" + "=" * 80)
        print("ALL CONTAINER SMOKE TESTS PASSED CLEANLY")
        print("=" * 80)
        return 0

    finally:
        print("\nCleaning up test container...")
        run_cmd(["docker", "rm", "-f", CONTAINER_NAME])
        print("[+] Cleanup complete.")


if __name__ == "__main__":
    sys.exit(execute_smoke_test())
