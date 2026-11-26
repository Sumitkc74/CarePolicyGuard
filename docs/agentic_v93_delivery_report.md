# Agentic v93 Delivery Report: v91 Delivery Report Corrections, Test Isolation Fix, Validator Revert, and L36920 Re-Run

**Delivery Version**: v93  
**Starting Head (v91 Delivery)**: `45be01e` (`45be01e1b036ef91e0951c9028a0c1c46bbc357f`)  
**v93 Implementation Commit**: `0805e6a` (`0805e6a960ffd9280e0aa8710732e0de921bd4d4`)  
**v93 Delivery Head Commit**: `docs(v93): add v93 delivery report` (verified via `git rev-parse HEAD` and `git cat-file -t` after commit)  
**Date**: November 26, 2026  

---

## 0. What Did NOT Hold (Stated Plainly First)

1. **Full Test Suite & CI at `0805e6a` (Expected Consequence of Reverting `c6546f1`)**:
   - Local full suite (`python -m pytest tests/ -q`): **`553 passed, 1 skipped, 2 failed`** (`556` collected in `284.92s`).
   - CI Run `45908866701` (commit `0805e6a`): conclusion **`failure`** (`Code Quality & Type Checking`: `success`; `Unit, Integration & Fuzz Test Suite`: `failure`; `Docker Build & Health Verification`: `skipped`).
   - **Root Cause**: Reverting commit `c6546f1` in `scripts/run_agentic_v59_three_mode_measurement.py` restored the strict pre-`c6546f1` `verify_baseline_reuse_validity` check. Two pre-existing tests (`tests/test_v73_safe_optimizations.py::test_baseline_reuse_validation_mechanism` and `tests/test_v75_deferral_rescue.py::test_v73_optimizations_unchanged_and_reusable`) call `verify_baseline_reuse_validity` against `agentic_v72_three_mode_run.json` and `agentic_v73_three_mode_run.json`, which compare against `HEAD`. Because v91 (`3c6006a`) backfilled `"status": "ACTIVE"` into `app/data/policies_extended/*.json` and added `app/data/policies_extended/mcd_cache/`, the strict validator raises `RuntimeError` as designed.
2. **v91 Baseline Defects Disclosed in Corrected Report**:
   - **Provenance gap**: v91 benchmark ran at `3c6006a`; delivery head was `45be01e` (4 commits later: `19817c3`, `21ab861`, `c6546f1`, `efe20df`), though no adjudication code changed after `3c6006a`.
   - **Zero-diff bar missed**: `DEV-LCD-KYPHO-APP` flipped DEFERRED&rarr;APPROVED (agentic `56/84` vs v86 `55/84`) due to host timing (`32.37s` vs v86 `64.57s` budget halt).
   - **Judge-call bound missed**: `108` judge calls vs `&le;106` bound (missed by 2).
   - **v91 CI chain incomplete/red**: `3c6006a` and `19817c3` had NO CI run (`total_count: 0`); `21ab861` was RED (`45795148411`, `failure`).

---

## 1. Delivery Head & Commit Chain

- **Starting Head**: `45be01e1b036ef91e0951c9028a0c1c46bbc357f` (`45be01e` — v91 delivery)
- **v93 Chain**: `45be01e` &rarr; `0805e6a` (`fix(v93): correct v91 delivery report, isolate onboarding tests, and revert c6546f1 validator loosening`) &rarr; `docs(v93): add v93 delivery report`

---

## 2. Corrections Applied to `docs/agentic_v91_delivery_report.md` (Task 1)

All edits were applied in place to [`docs/agentic_v91_delivery_report.md`](file:///e:/Class/GitHub/CarePolicyGuard/docs/agentic_v91_delivery_report.md):

1. **(a) Delivery Head & Provenance (lines 9–12, 40–41, 229–234)**:
   - Added `**Delivery Head**: \`45be01e\` (\`45be01e1b036ef91e0951c9028a0c1c46bbc357f\`)`, updated lineage line 41 to `45be01e (v91 delivery)`, removed `"0-commit provenance gap"`, and stated plainly that the measurement ran at `3c6006a` while 4 commits followed before `45be01e` (with no adjudication-relevant code changes after `3c6006a`).
2. **(b) Neutrality Headline & Diff Analysis (lines 24, 249–257)**:
   - Replaced `"absolute adjudication neutrality... zero decision changes"` with: `agentic 56/84` with `1` decision diff vs v86 (`DEV-LCD-KYPHO-APP` DEFERRED&rarr;APPROVED, host-timing cause, `32.37s` vs `64.57s`, both KYPHO criteria MET with real spans `"bone edema"` 10&times; and `"STIR"` 11&times;, no HALT), and stated plainly that the zero-diff acceptance bar was **NOT met**.
3. **(c) Review Tool Description, Summary Table, & Exit Code (lines 54–76, 165–168, 219)**:
   - Rewrote from [`scripts/review_policy_queue.py`](file:///e:/Class/GitHub/CarePolicyGuard/scripts/review_policy_queue.py): removed nonexistent override/force flags, `FLAG` decision, and `VERIFIED_BY_HUMAN` status; documented real `--decision {APPROVE, REJECT, ACCEPT}`, real `--list --status {PENDING_HUMAN_REVIEW, ACCEPTED, REJECTED}`, real `FORBIDDEN_AGENT_KEYWORDS = ["agent", "llm", "antigravity", "bot", "assistant", "system", "auto"]`, strict no-exception refusal of `APPROVE` on `verbatim_check != "PASS"`, strict `DRAFT` + all-`ACCEPTED` activation gate, and corrected exit code from `2` to `1`.
   - Fixed summary output block (lines 165–168) to show only `PENDING_HUMAN_REVIEW: 182`, `ACCEPTED (Human Approved): 0`, `REJECTED (Human Rejected): 0`.
4. **(d) Test Names (lines 288–301)**:
   - Replaced `test_iii_agent_reviewer_rejection` and `test_vi_agent5_synthetic_fallback_removed` (and all 10 descriptions) with the exact 10 test names verified in [`tests/test_v91_policy_verification_workflow.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_v91_policy_verification_workflow.py): `test_i_review_tool_refuses_agent_reviewer` through `test_x_verbatim_check_logic`.
5. **(e) CI Section (lines 330–369)**:
   - Listed all 6 v91 commits with exact run IDs and conclusions (`3c6006a`: NO RUN; `19817c3`: NO RUN; `21ab861`: `45795148411` `failure`; `c6546f1`: `45796642377` `success`; `efe20df`: `45798442837` `success`; `45be01e`: `45800251443` `success`).
6. **(f) Judge Calls (line 269)**:
   - Stated plainly: `108` judge calls vs `&le;106` prompt bound — **missed by 2**.
7. **(g) Test-File Count (line 302)**:
   - Measured via `git ls-files tests/`: `104` total files / `101` `.py` files at `45be01e` (`105` total / `102` `.py` at v93 head).
8. **(h) L36920 Re-Run (lines 91–97)**:
   - Added explicit L36920 re-run results under Task 3, noting it was not reported in the original v91 report and was run and reported in v93.
9. **(i) Validator Revert Note (line 234, line 340)**:
   - Documented that `c6546f1`'s validator loosening was reverted in v93 and did not affect the v91 measurement (`baselines_reused: False`).

---

## 3. Two Code Fixes & Guard Tests (Task 2)

1. **Task 2(a) — Test Isolation Fix**:
   - Removed the stray un-isolated `PolicyOnboardingAgent(staging_dir=tmp_path)` lines in `test_viii_onboard_policy_creates_pending_human_review_queue_records` and `test_ix_freshly_onboarded_policy_draft_and_claimed_unverified` in [`tests/test_v91_policy_verification_workflow.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_v91_policy_verification_workflow.py).
   - Also passed `queue_path=tmp_path / "queue.json"` in `test_onboarding_against_known_good_source_reproduces_criteria` and `test_non_verbatim_quoted_passage_is_rejected` in [`tests/test_policy_onboarding_agent.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_policy_onboarding_agent.py) so full-suite execution never mutates [`app/data/policy_verification_records.json`](file:///e:/Class/GitHub/CarePolicyGuard/app/data/policy_verification_records.json).
   - Guard test `test_viii_onboarding_isolation_does_not_mutate_real_queue` in [`tests/test_v93_report_corrections.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_v93_report_corrections.py): verified **FAILS** when `queue_path` is omitted (`before == after` is `False`) and **PASSES** with `queue_path` isolated (`before == after` is `True`).
2. **Task 2(b) — Revert `c6546f1` Validator Loosening**:
   - Deleted the `elif "mcd_cache" in cf:` and metadata-only `policies_extended` branches in `verify_baseline_reuse_validity` ([`scripts/run_agentic_v59_three_mode_measurement.py`](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v59_three_mode_measurement.py)), restoring strict pre-`c6546f1` fallthrough to `else: unauthorized_changes.append(cf)`.
   - Guard test `test_metadata_only_policy_change_invalidates_baseline_reuse` in [`tests/test_v93_report_corrections.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_v93_report_corrections.py): **PASSES** (`RuntimeError` raised on metadata-only `"status": "ACTIVE"` diff).
3. **Task 2(c) — Report Guard Tests**:
   - `test_v91_report_cites_delivery_head_45be01e`: **PASSED**.
   - `test_v91_report_contains_no_fabricated_claims`: **PASSED**.

---

## 4. L36920 Onboarding Re-Run Result (Task 3)

Executed `PolicyOnboardingAgent(staging_dir=tmp_dir, queue_path=tmp_queue).onboard_policy("L36920", "Epidural Steroid Injections for Pain Management", save_draft=True)` without touching `app/data/policies_extended/ONBOARDING_REPORT_LCD-L36920.md` or the production queue:
- `status`: `DRAFT_ONBOARDED` (**PASS**)
- `policy.status`: `DRAFT`, `provenance_status`: `CLAIMED_UNVERIFIED` (**PASS**)
- `flagged_ambiguities`: 1 (`CRIT-ESI-01`, `flag_type="NEEDS_HUMAN_JUDGMENT"`, `"severe"` without quantitative cutoff) (**PASS**)
- `queue_records_created`: 1 (`CRIT-ESI-01`, `PENDING_HUMAN_REVIEW`, `verbatim_check="PASS"`, `policy_status="DRAFT"`) (**PASS**)

---

## 5. Verification & CI Results (Task 4)

- **Collected Tests (`pytest --collect-only -q tests/`)**: **556** (`552` baseline + `4` new v93 tests).
- **Full Suite (`python -m pytest tests/ -q`)**: **`553 passed, 1 skipped, 2 failed`** in `284.92s` (only the 2 strict-validator baseline-reuse tests noted in §0 failed; `app/data/policy_verification_records.json` remained byte-identical).
- **BENCH & v1 Guards**: **14 / 14 passed** (`tests/test_benchmark.py` 5/5 + `tests/test_v1_heldout_regressions.py` 9/9).
- **Ruff (`ruff check` on all touched files)**: `All checks passed!` (`0` errors).
- **JS Syntax (`node --check app/static/js/app.js`)**: Clean (`exit code 0`).
- **v93 CI Chain**:
  - `0805e6a`: Run `45908866701` — **`failure`** (`Code Quality & Type Checking`: `success`; `Unit, Integration & Fuzz Test Suite`: `failure` on the 2 baseline-reuse tests; `Docker Build & Health Verification`: `skipped`).
  - Delivery docs commit: Pending push.
- **v91 CI Chain (Restated)**: `3c6006a` (NO RUN), `19817c3` (NO RUN), `21ab861` (`45795148411`, `failure`), `c6546f1` (`45796642377`, `success`), `efe20df` (`45798442837`, `success`), `45be01e` (`45800251443`, `success`).
