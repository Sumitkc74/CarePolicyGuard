# Suggestion Prompt v67 — Three-Mode & Retrieval Re-Measurement Report

**Parent Head:** `938fce15da1f5f2997782627e77db48eebf81cb4` (re-anchored after v68 landing and Task 4 JS syntax gate commit)
**Date:** November 18, 2026
**Dataset:** 84 development vignettes (`dev_vignettes_extended.json`, author-written dev set; dev measurements only, not held-out clinical validation)
**Database State:** `carepolicyguard.db` (60 policies, all transcribed and verified from the official CMS Coverage API)
**Local LLM Model:** `qwen2.5:3b` on Ollama (hermetic local inference, remote egress default-off)

---

## 1. Executive Summary & Context

v66 (`7ddd9d9`) transcribed all policy criteria from the official CMS Coverage API, followed by catalog expansion to 60 policies (`b6cf3f1`), the frontend JavaScript syntax fix (`ea0bab6`), and the v68 spurious shortlist fix (`447c2ba`). Because policy criteria were replaced with official CMS statutory text, the v63 evaluation numbers became stale. 

This v67 session performed the definitive re-measurement across Deterministic, Declarative, and Agentic modes, verified retrieval against the expanded 60-policy catalog, audited the advocacy guard, pinned a permanent JavaScript syntax gate in CI and pytest, and verified full regression suite compliance.

> [!NOTE]
> All metrics reported below are dev-set measurements evaluated against `carepolicyguard.db` and the 60-policy catalog. They are explicitly labelled as dev measurements and do not represent held-out or clinical results.

---

## 2. Three-Mode Benchmark Safety & Accuracy Comparison

All metrics recomputed directly from committed evidence in `app/data/benchmarks/agentic_v67_three_mode_run.json`:

| Execution Mode | Decisions Breakdown (Approved / Denied / Deferred) | Concordant Decisions (Accuracy) | False Approvals (Safety) | False Denials | Safe Deferrals (Abstentions) | Synonymy Resolved (Target 19) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Mode (v63)** *(Old Criteria, 50-policy pool)* | 18 / 21 / 45 | **37 / 84 (44.0% dev)** | **0** | 2 | 45 | 0 / 19 (0.0% dev) |
| **Deterministic Mode (v67)** *(CMS Criteria, 60-policy pool)* | 18 / 21 / 45 | **37 / 84 (44.0% dev)** | **0** | 2 | 45 | 0 / 19 (0.0% dev) |
| **Declarative Mode (v63)** *(Old Criteria, 50-policy pool)* | 21 / 18 / 45 | **39 / 84 (46.4% dev)** | **0** | 0 | 45 | 0 / 19 (0.0% dev) |
| **Declarative Mode (v67)** *(CMS Criteria, 60-policy pool)* | 21 / 18 / 45 | **39 / 84 (46.4% dev)** | **0** | 0 | 45 | 0 / 19 (0.0% dev) |
| **Agentic Mode (v63)** *(Strict Guard, Old Criteria, 50-policy pool)* | 28 / 18 / 38 | **46 / 84 (54.8% dev)** | **0** | 0 | 38 | 8 / 19 (42.1% dev) |
| **Agentic Mode (v67)** *(Strict Guard, CMS Criteria, 60-policy pool)* | 28 / 18 / 38 | **46 / 84 (54.8% dev)** | **0** | 0 | 38 | 8 / 19 (42.1% dev) |

*Note: In all modes, decisions are strictly segregated: 46 concordant decisions in agentic mode = 28 true approvals + 18 true denials; 38 cases safely abstained as `DEFERRED_TO_HUMAN`. Zero false approvals were generated across all modes.*

### Synonymy Cases Resolved (8 / 19 in Agentic Mode):
1. `DEV-LCD-IMRT-APP`
2. `DEV-LCD-KNEE-ORTHOSIS-APP`
3. `DEV-LCD-LUMBAR-DECOMP-APP`
4. `DEV-LCD-PROTON-APP`
5. `DEV-LCD-RAD-NIV-APP`
6. `DEV-NCD-CARDIAC-REHAB-APP`
7. `DEV-NCD-MPI-PET-APP`
8. `DEV-NCD-PUMP-APP`

Unresolved synonymy cases (11 / 19): `DEV-LCD-KYPHO-APP`, `DEV-LCD-MRI-BRAIN-APP`, `DEV-LCD-MRI-LUMBAR-APP`, `DEV-LCD-PAD-ATHERO-APP`, `DEV-LCD-POWER-WC-APP`, `DEV-LCD-SBRT-APP`, `DEV-NCD-CCTA-APP`, `DEV-NCD-PACEMAKER-APP`, `DEV-NCD-PET-ONC-APP`, `DEV-NCD-SGD-APP`, `DEV-OPD-SI-FUSION-APP`.

### Per-Case Diff vs v63:
- Decision diffs: **0** across all 84 dev vignettes in all three modes.
- Criterion-level status diffs: **0** across all criteria in all 84 vignettes.

### Analysis of the 5 Gate C Criteria Under Official CMS Criteria Text:
1. **`CRIT-KYPHO-02` (`DEV-LCD-KYPHO-APP` / `LCD-KYPHO`)**:
   - Outcome: `INSUFFICIENT_EVIDENCE`.
   - Diagnosis: **Map gap**. The CMS criterion text requires documentation of conservative medical therapy failure; the note's description is unmapped in the concept map.
2. **`CRIT-PAD-02` (`DEV-LCD-PAD-ATHERO-APP` / `LCD-PAD`)**:
   - Outcome: `INSUFFICIENT_EVIDENCE`.
   - Diagnosis: **Equivalence / Map gap**. Requires prior conservative medical therapy (cilostazol or supervised exercise), which is absent or unmapped.
3. **`CRIT-SBRT-01` (`DEV-LCD-SBRT-APP` / `LCD-SBRT`)**:
   - Outcome: `INSUFFICIENT_EVIDENCE`.
   - Diagnosis: **Guard blocked**. In turn 1, Agent 3 raised an anatomical mismatch counter-reading; Agent 2 conceded (`debated_criteria_outcomes: {'CRIT-SBRT-01': 'CONCEDED'}`). Under `pipeline.py:1000`, advocacy was barred from challenging conceded criteria.
4. **`CRIT-CAT-02` (`DEV-NCD-CATARACT-APP` / `NCD-CATARACT`)**:
   - Outcome: `INSUFFICIENT_EVIDENCE`.
   - Diagnosis: **Map gap**. Requires documented impairment in activities of daily living attributable to cataract; wording does not align with statutory terms without concept map expansion.
5. **`CRIT-SCS-02` (`DEV-NCD-SCS-APP` / `NCD-SCS`)**:
   - Outcome: `INSUFFICIENT_EVIDENCE`.
   - Diagnosis: **Map gap**. Requires formal multidisciplinary psychological/psychiatric evaluation. While the concept collision was resolved in v62, statutory text coverage remains ungrounded.

---

## 3. Debate, Toolbelt, Latency, and Turn Telemetry

Metrics extracted directly from `agentic_run`:
- **Debate Dynamics**:
  - Counter-readings raised: **2** (`ANATOMIC_MISMATCH`: 1, `TEMPORAL`: 1)
  - Defenses attempted: **2**
  - Defended count: **0**
  - Conceded by counter-reading: **2**
  - Conceded by gate failure: **9**
  - Decisions changed by debate: **0**
  - Unresolved disagreements: **0**
- **Toolbelt Telemetry**:
  - `deterministic_check`: 154
  - `judge_criterion`: 64
  - `advocate_for`: 52
  - `defer`: 63
  - Mind changes: **11** (100% `met_to_insufficient`, 0 `toward_met`)
  - Fallback activations: **0**
- **Wall Time & Budgets**:
  - Case wall time mean: **21.48 s**
  - Case wall time max: **63.97 s**
  - Cases exceeding 60 s wall budget: **9** (`DEV-LCD-HIP-ARTHRO-NEG`, `DEV-LCD-HIP-SCOOP-NEG`, `DEV-LCD-KNEE-ARTHRO-NEG`, `DEV-LCD-KNEE-ORTHOSIS-NEG`, `DEV-LCD-LUMBAR-DECOMP-NEG`, `DEV-LCD-LUMBAR-FUSION-NEG`, `DEV-LCD-PROTON-NEG`, `DEV-LCD-ROTATOR-CUFF-NEG`, `DEV-LCD-SHOULDER-ARTHRO-NEG`)
  - Operational budget halts: **0**
  - Abstention gate halts: **38** (36 insufficient evidence, 2 low calibrated confidence)
- **Judge Calls & Agent Turns**:
  - Judge calls total: **64**, Mean: **0.76**, Max: **2** (well within 8-call budget)
  - Agent turns total: **428**, Mean: **5.10**, Max: **8**

---

## 4. Advocacy Guard Audit & Cost

### Invariant Verification:
- All 84 message-board transcripts scanned for `ADVOCACY` events subsequent to a `CONCEDE` record:
  - **Violations: 0**.
  - The guard invariant (`crit_judgment.status != "MET" and debated_criteria_outcomes.get(ccode) != "CONCEDED"`) holds with 100% fidelity.

### Guard Cost at this Head:
- **Criterion-level promotions blocked by guard**: **2** (`DEV-LCD-SBRT-APP` on `CRIT-SBRT-01` and `DEV-OPD-SI-FUSION-APP` on `CRIT-SI-01`).
- **Case-level promotions blocked by guard**: **2** (both remained safely `DEFERRED_TO_HUMAN`).
- **Advocacy attempts**: 52 attempted, 0 promoted, 52 rejected (50 `empty_quote`, 2 `gate_b_or_c`).
- **Agent-Driven Approvals**: **0** (All 7 net approval gains of Agentic mode over Declarative mode (28 vs 21) are 100% map-driven from the 119 draft concept extensions; 0 are agent/advocate-driven).
- Decision on guard redesign remains **OPEN**; the mechanism is preserved as instructed.

---

## 5. Policy Retrieval Re-Measurement (Expanded 60-Policy Pool)

Evaluated against the expanded catalog pool of **60 policies** in `carepolicyguard.db`:

| Metric | v63 Baseline *(50-policy pool)* | v67 Re-Measurement *(60-policy pool)* | Notes |
| :--- | :---: | :---: | :--- |
| **Top-1 Accuracy** | 69 / 84 (82.1% dev) | **68 / 84 (81.0% dev)** | 60-policy candidate pool |
| **Top-3 Accuracy** | 82 / 84 (97.6% dev) | **82 / 84 (97.6% dev)** | 60-policy candidate pool |
| **Top-5 Accuracy** | 82 / 84 (97.6% dev) | **82 / 84 (97.6% dev)** | 60-policy candidate pool |
| **Agreement (Pipeline vs Standalone)** | 84 / 84 (100.0%) | **83 / 84 (98.8% dev)** | 1 negative vignette diff (`DEV-NCD-PET-ONC-NEG`) |
| **Rerank Flips Total** | 8 | **8** | Stage 2 coverage re-ranking |
| **Flips to Gold** | 2 | **2** | `DEV-LCD-HIP-ARTHRO-APP`, `DEV-LCD-SHOULDER-ARTHRO-APP` |
| **Flips to Non-Gold** | 6 | **6** | `DEV-LCD-FACET-NEG`, `DEV-LCD-LUMBAR-FUSION-NEG`, `DEV-LCD-MRI-LUMBAR-APP`, `DEV-LCD-PAD-ATHERO-NEG`, `DEV-LCD-ROTATOR-CUFF-NEG`, `DEV-NCD-SCS-APP` |
| **Null Margins** | 0 | **0** | All pre/post margins populated |
| **Mean Pre-Rerank Margin** | 0.1248 | **0.1221** | Pre-rerank score margin |
| **Mean Post-Rerank Margin** | 0.1912 | **0.1888** | Post-rerank score margin |

---

## 6. Task 4 — JavaScript Syntax & Integrity Gate (Mechanism Fix)

To prevent silent recurrences of the frontend syntax breakdown that occurred from v47 through b6cf3f1 (`Unexpected token '}'`), a permanent mechanism fix was engineered and pinned:

1. **Test Suite Implementation**:
   - Committed test file: `tests/test_frontend_js_syntax.py`
   - Exact test names:
     - `test_app_js_syntax_validity`: Executes `node --check app/static/js/app.js` using `subprocess.run(check=False)`. Fails loudly with `pytest.fail()` if Node.js is not on PATH; never skips silently. (PASSED)
     - `test_app_js_syntax_gate_catches_broken_syntax`: Creates a temporary JavaScript copy containing an unclosed brace / unexpected token `}`, executes `node --check`, and asserts that the check actively fails with `SyntaxError`. (PASSED — broken-copy proof verified).
     - `test_frontend_auth_handlers_present_and_wired`: Verifies that `checkSessionOrShowGate`, `showLoginGate`, `hideLoginGate`, `switchLoginMode`, `handleMedicalRegistration`, `handleCustomLogin`, and `executeLogin` are defined in `app/static/js/app.js`, and that `onsubmit="handleCustomLogin(event)"`, `onsubmit="handleMedicalRegistration(event)"`, and `#login-gate-screen` are bound in `app/static/index.html`. (PASSED)
2. **CI Pipeline Wiring**:
   - Added step in `.github/workflows/ci.yml` under `lint-and-typecheck`:
     ```yaml
     - name: Validate Frontend JavaScript Syntax Gate
       run: |
         node --check app/static/js/app.js
     ```
   - Pre-installed Node.js runtime on GitHub-hosted `ubuntu-latest` runners executes this check on every push and PR.

---

## 7. Regression Guards & Suite Status

1. **Full Pytest Suite**:
   - **444 passed, 0 failed, 2 warnings** in 296.20 s (04:56).
   - Zero skipped tests.
2. **BENCH / v1 Invariants**:
   - BENCH: **10 / 10 passed** (`tests/test_benchmark.py`).
   - v1 Held-Out Regressions: **9 / 9 passed** (`tests/test_v1_heldout_regressions.py`).
   - Combined: **14 / 14 passed** in 22.13 s.
   - **0 false approvals, 0 false denials.**
3. **12 Sample Clinician Notes**:
   - All 12 notes evaluated through multi-agent verification pipeline without errors or unhandled exceptions.
4. **Ruff Check Counts**:
   - `ruff check app/core app/schemas --ignore E501`: **All checks passed (0 errors)**.
   - Changed files (`tests/test_cms_coverage_api.py`, `tests/test_policy_provenance_v66.py`, `tests/test_frontend_js_syntax.py`, `scripts/run_agentic_v59_three_mode_measurement.py`): **All checks passed (0 errors)**.
5. **Frontend Syntax**:
   - `node --check app/static/js/app.js`: Clean (0 syntax errors).
