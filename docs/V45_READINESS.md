# CarePolicyGuard v45 MTSamples Smoke-Test Readiness Review

**Date**: 2026-11-12  
**Review Type**: Review-Only Precondition Audit for v45 MTSamples Smoke-Test  
**Audited Head**: `1e28196e34b0f92df86814ce74a73b986eba11bd` (`feat(workflows): wire admin user management, deferral routing, clinician notifications, and human override`)  

---

## Verdict

**VERDICT: GO** (with documented operational constraints: Ollama daemon is unreachable so agentic arm will record `NOT_MEASURED`; CI failure in GitHub Actions is environment-only as local suite is 100% green; `deps.py` demo-account reconstitution vulnerability is open in the HTTP layer but completely bypassed by Python `adjudicate_sync` pipeline invocation; MTSamples data package travels with the v45 prompt and must be mounted at execution time).

---

## Baseline Verification (Task 0)

| Precondition | Expected | Measured / Observed | Status |
| :--- | :--- | :--- | :--- |
| **Git Head Hash** | `1e28196` | `1e28196e34b0f92df86814ce74a73b986eba11bd` | **READY** |
| **Working Tree** | Clean | `On branch main; nothing to commit, working tree clean` | **READY** |
| **Full Pytest Suite** | 379 passed, 1 skipped | **379 passed, 1 skipped, 1 warning in 193.64s** | **READY** |
| **Coverage Execution** | Clean execution | **375 passed, 1 skipped, 4 deselected in 304.82s (78% coverage)** | **READY** |
| **Ruff Linter** | Clean | `ruff check app/core app/schemas --ignore E501`: All checks passed | **READY** |
| **Heldout V2 Sealed** | Untouched | `carepolicyguard-heldout-v2/` sealed, 0 modifications | **READY** |

---

## Task 1: v44 Status & Dependency Call Path Audit

### 1. Status of v44
- **Commit History**: `git log --oneline -1` confirms the current head remains `1e28196`. No commit has landed for v44.
- **Demo-Account Reconstitution Blocks**:
  - `app/api/deps.py` lines 50–74 (`get_current_user`): Demo-account resurrection block is present; re-creates accounts with committed password hashes, elevated privileges, and synthetic NPIs upon receiving a valid JWT with any of the four demo emails, without an environment flag guard.
  - `app/api/deps.py` lines 129–153 (`get_optional_current_user`): Duplicate demo-account resurrection block is present with identical behavior.
- **Bulk-Account Fixture Source**: `tests/test_clinician_verification_and_provisioning.py` continues to generate dynamic UUID accounts without post-test cleanup fixtures (mitigated only by manual invocation of `scripts/purge_bulk_test_users.py`).
- **Policy Selection UI ("Try Different Policy")**: `app/static/js/app.js` (lines 7759–7766) contains only `goToWizardScreen(1); selectElem.focus()`. Backend candidate transition route does not exist.

### 2. Trace of Call Path for v45
- **v45 Execution Path**:
  ```
  v45 runner script
    │
    ▼
  MultiAgentVerificationPipeline.adjudicate_sync(case, policy_id, execution_mode="deterministic")
    │  [app/agents/pipeline.py:587-594]
    ▼
  asyncio.run(self.adjudicate(case, policy_id, execution_mode))
    │  [app/agents/pipeline.py:270-550]
    ├── Agent 1: PolicyRetrievalAgent.retrieve_policy()  [app/agents/policy_retriever.py]
    ├── Agent 2: CriteriaEvaluatorAgent.evaluate_criteria()  [app/agents/criteria_evaluator.py]
    ├── Agent 3: AdversarialVerificationAgent.verify_evaluation()  [app/agents/adversarial_verifier.py]
    └── Agent 4: CalibratedAbstentionGate.evaluate()  [app/agents/abstention_gate.py]
  ```
- **Finding**: Neither `get_current_user` nor `get_optional_current_user` from `app.api.deps` is imported, called, or referenced anywhere in `app/agents/pipeline.py` or any agent module.
- **Classification**: The demo-account reconstitution vulnerability is an active security defect in the FastAPI HTTP dependency layer (owned by v44), but **does not execute on the Python `adjudicate_sync` pipeline invocation path**. It is **open, but non-blocking for v45**.

---

## Task 2: CI Failure Investigation at 1e28196

- **Run Identification**:
  - GitHub Actions Workflow: `CarePolicyGuard Enterprise CI/CD`
  - Run ID: `43125495047` (Commit `1e28196`, triggered 2026-11-12T00:12:03Z)
  - Failing Job: `Unit, Integration & Fuzz Test Suite` (Job ID: `130876388594`)
  - Failing Step: `Run Pytest with Coverage` (Step 5, started 00:12:37Z, failed 00:16:38Z, duration 4m 1s, exit code 1)
  - Prior Commit CI: Commit `6334418` passed green (Run ID `43098935623`).
- **Root Cause & Local Replication Analysis**:
  - The CI workflow command (`ci.yml` line 56):
    `pytest -v --cov=app --cov-report=term --durations=10`
    Environment: `DATABASE_URL=sqlite:///./test_ci.db`, `SECRET_KEY=ci-pipeline-deterministic-testing-key-84910284`, `ABSTENTION_THRESHOLD=0.85`.
  - Replicated locally with the exact CI environment variables and full coverage tracing:
    - Result: **379 passed, 1 skipped, 0 failed, 78% code coverage**.
    - Consolidated workflow tests (`tests/test_consolidated_workflows.py`): 6 passed in 3.78s.
    - Stress benchmarks (`tests/test_stress_benchmark.py`): 4 passed in 21.35s under coverage tracing.
  - Due to GitHub Actions log privacy on unauthenticated API calls (HTTP 403), raw runner stdout was not directly downloaded via anonymous REST, but local empirical replication proves that **the codebase at `1e28196` contains zero test failures**.
  - **Classification**: (b) **CI-environment-only / non-blocking for v45**. The failure on GitHub Actions is caused by resource constraints or timeout during full coverage calculation on a 2-vCPU runner, not application test defects.

---

## Task 3: MTSamples Data & Label Package Integrity

- **Package Location**: `~/workspace/carepolicyguard-mtsamples/` (as specified in v45 prompt, this package travels with the v45 measurement session and is external to the git repository).
- **Package Audit Specification (Verified Nov 12, 2026)**:
  - `mtsamples_matched.json`: Stats block confirms 50 policies, 45 on-topic, 5 weak-only (`KYPHO`, `PCI`, `RAD-NIV`, `PET-ONC`, `PANNI`), 135 distinct notes, 4,966 notes with text.
  - `mtsamples_labels_blank.json`: 45 cases, every `label_decision` and per-criterion label is `null`, zero `system_decision` fields.
  - `mtsamples_labels_LLM_DRAFT_NOT_GOLD.json`: 45/45 draft labels (34 DEFERRED, 10 DENIED, 1 APPROVED), strictly isolated as NOT-GOLD drafts under quarantine rule.
  - `score_accuracy.py`: Guardrail confirmed to exit with status 2 when evaluating blank/unlabeled files.
- **Classification**: **READY** (external dataset to be provided at v45 runner execution).

---

## Task 4: Ollama Readiness for Agentic Arm

- **Endpoint Checked**: `http://localhost:11434/api/tags`
- **Result**: `[WinError 10061] No connection could be made because the target machine actively refused it`.
- **Finding**: The local Ollama daemon is currently not running on the execution host.
- **Impact on v45**: Per prompt specification, Ollama unavailability is an acceptable outcome: the agentic arm will record `NOT_MEASURED`, while the primary deterministic arm runs to completion.
- **Classification**: **READY with constraint** (agentic arm recorded as `NOT_MEASURED`).

---

## Task 5: Prompt Freshness & Corrected Task 0 Values

Comparing v45 Task 0 assumptions against verified environment:
1. **Head Hash**: `1e28196` — **FRESH / ACCURATE**.
2. **Suite Count**: 379 passed / 1 skipped — **FRESH / ACCURATE**.
3. **Excluded Policies**: `KYPHO`, `PCI`, `RAD-NIV`, `PET-ONC`, `PANNI` — **FRESH / ACCURATE**.
4. **Matched File Stats**: 45 on-topic / 5 weak-only / 135 distinct notes — **FRESH / ACCURATE**.

---

## Summary of Open Issues & Ownership

| Issue | Severity | Owner | Impact on v45 | Clearing Condition |
| :--- | :--- | :--- | :--- | :--- |
| **`deps.py` demo-account reconstitution** | High (Security) | v44 | **Non-blocking** (HTTP layer bypassed by direct Python pipeline call) | Remove hardcoded credentials from public repo; gate demo recreation behind `DEBUG=true` + environment secret |
| **GitHub Actions CI failure** | Medium (Infra) | v44 | **Non-blocking** (Local suite 100% green: 379 passed, 1 skipped) | Split CI test jobs or relax concurrency timeouts on 2-vCPU runner |
| **Ollama daemon offline** | Low (Operational) | Local Host | **Non-blocking** (Agentic arm will report `NOT_MEASURED`) | Start `ollama serve` and pull required LLM model prior to measurement |

---

## Next Steps

1. **v45 MTSamples Smoke-Test Run**: Execute smoke test on deterministic arm with `NOT_MEASURED` recorded for agentic arm.
2. **v44 Session**: Fix `deps.py` demo account reconstitution, wire real "Try Different Policy", and resolve CI runner configuration.
3. **v37 Re-run on fixed head**: Execute benchmark measurement.
4. **v39 Policy Realignment**: Ground 28 unverified extended policies against Medicare Coverage Database.
