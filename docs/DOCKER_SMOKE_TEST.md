# CarePolicyGuard Container Packaging & Smoke Test Protocol

## 1. Overview & Verification Scope

CarePolicyGuard packages as an enterprise-grade, HIPAA-compliant container image with the following specifications:
- **Base Image**: Multi-stage Linux build based on `python:3.12-slim`.
- **Security Hardening**: Runs as unprivileged clinical service account `appuser:appgroup` (UID/GID `1001:1001`), dropping all root capabilities.
- **Repository Metadata Isolation**: `.dockerignore` excludes `.git/`, `.github/`, `.env*`, `carepolicyguard-heldout/`, local databases, and development artifacts.
- **Fail-Fast Credential Enforcement**: Container requires runtime injection of `SECRET_KEY`; startup aborts immediately if missing or set to an insecure placeholder.

---

## 2. Environment Execution Status

| Environment | Runtime Platform | Verification Status | Verification Mechanism |
| :--- | :--- | :--- | :--- |
| **Local Review Host** | Windows 10/11 Host (No Docker / No WSL distribution) | **Unrun Locally** | Verified via static Dockerfile audit, compose syntax verification, and unit tests ([tests/test_secrets_configuration.py](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_secrets_configuration.py)). No local container execution is claimed. |
| **GitHub Actions CI** | `ubuntu-latest` (Docker Engine & Buildx) | **Automated in CI Pipeline** | Automated execution in `.github/workflows/ci.yml` (`docker-build-and-health` job): image build, `/app/.git` absence assertion, `/health` endpoint check, and synthetic clinical adjudication. |
| **Turnkey Runner** | Any host with Docker daemon | **Automated Script Available** | Executable standalone Python script ([scripts/docker_smoke_test.py](file:///e:/Class/GitHub/CarePolicyGuard/scripts/docker_smoke_test.py)). |

---

## 3. How to Run the Smoke Test

### A. Turnkey Script Execution
On any system with Docker Desktop or Docker Engine installed and running:
```bash
python scripts/docker_smoke_test.py
```
This automated script:
1. Verifies Docker CLI and daemon connectivity.
2. Builds `carepolicyguard:latest` from [Dockerfile](file:///e:/Class/GitHub/CarePolicyGuard/Dockerfile).
3. Verifies that `/app/.git` was excluded from the built image.
4. Spawns an ephemeral test container with an in-memory `SECRET_KEY`.
5. Polls the microservice `/health` endpoint until healthy (HTTP 200).
6. Executes synthetic clinical adjudication with zero patient data.
7. Automatically cleans up and removes the container.

### B. Manual CLI Execution
```bash
# 1. Build hardened multi-stage image
docker build -t carepolicyguard:latest .

# 2. Confirm .git directory was excluded from image build
docker run --rm carepolicyguard:latest sh -c "test ! -d /app/.git" && echo "PASS: .git directory successfully excluded"

# 3. Launch container with ephemeral test secret
export TEST_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
docker run -d --name cpg-smoke -p 8000:8000 \
  -e SECRET_KEY="$TEST_SECRET" \
  -e DATABASE_URL="sqlite:///./data/smoke.db" \
  -e ABSTENTION_THRESHOLD=0.85 \
  carepolicyguard:latest

# 4. Verify microservice health endpoint
curl -f http://localhost:8000/health

# 5. Execute synthetic clinical adjudication (zero patient data)
curl -f -X POST http://localhost:8000/api/v1/adjudicate \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "PT-SMOKE-CONTAINER-01",
    "policy_id": "NCD-20.4",
    "ehr_narrative": "History of Present Illness:\n67yo male with ischemic cardiomyopathy s/p CABG 14 months ago.\nNYHA Class II symptoms on GDMT for 6 months.\n\nDiagnostic Studies:\nTTE confirms LVEF 28% with severe regional hypokinesis."
  }'

# 6. Stop and remove test container
docker rm -f cpg-smoke
```

---

## 4. Synthetic Clinical Adjudication Test Case

- **Patient Identifier**: `PT-SMOKE-CONTAINER-01` (Synthetic note only; zero real patient data)
- **Medicare Policy**: `NCD-20.4` (Implantable Cardioverter Defibrillators)
- **Statutory Criteria Evaluated**:
  1. `CRIT-ICD-01` (LVEF <= 35%): Documented `28%` -> `MET`
  2. `CRIT-ICD-02` (NYHA Class II/III Heart Failure): Documented `NYHA Class II` -> `MET`
  3. `CRIT-ICD-03` (Optimal Medical Therapy >= 90 Days): Documented `6 months` (180 days) -> `MET`
  4. `CRIT-ICD-04` (Post-CABG Waiting Period > 3 Months): Documented `14 months` (420 days) -> `MET`
- **Expected Result**: `APPROVED` determination, 4 verified evidence spans, confidence score >= 0.85, and SHA-256 tamper-evident seal.

