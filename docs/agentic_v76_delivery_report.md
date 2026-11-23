# Agentic v76 Delivery Report: One Shared Authorization and Release Workflow

**Date**: November 22, 2026  
**Re-Anchored Head**: `fd33da2` (v77 Delivery Head)  
**Task Scope**: Build & Verification (No Re-Measurement Required — Zero Adjudication Code Changed)  
**Status**: COMPLETE — ALL ACCEPTANCE CRITERIA MET

---

## 1. Commit and Provenance

- **Preceding Head at Re-Anchor**: `fd33da2` (full `fd33da2380e9e5e0aeb52752b5e2ceeacd159494`)
- **Parent Acceptance Commit**: `76ade68` (v74 Acceptance)
- **Status of Adjudication Code**: Zero changes to pipeline, judge, debate, advocate, concept map, policies, or vignettes.

---

## 2. The Shared Release Gate

A single shared gate function, `require_releasable_determination`, was created in `app/api/release.py` (and re-exported via `app/api/deps.py`).

### Gate Definition
```python
def require_releasable_determination(
    target: Any,
    log: Any | None = None,
    adjudication: Any | None = None,
) -> None:
    """
    Enforces the single shared release gate across all release paths:
    determination_stage == 'FINAL' AND is_releasable is True AND human_sign_off_status in ('SIGNED_OFF', 'OVERRIDDEN_FINAL').
    Raises HTTP 412 Precondition Failed naming the missing condition(s) if not satisfied.
    """
    ...
```

If any condition is missing, it raises `HTTP 412 Precondition Failed` with a clear message:
`"Determination is PROVISIONAL and cannot be released or exported as final without recorded human sign-off. Missing release conditions: ..."`

### Release Paths Wired to the Shared Gate
Every release path in the system now strictly enforces the shared gate:
1. `POST /api/v1/packet/submit`: Checks `require_releasable_determination(packet or log, log=log)` in addition to requiring `get_verified_clinician_user`.
2. `GET /api/v1/packet/{case_id}/pdf`: When `require_final` is set, calls `require_releasable_determination(packet)` instead of inline local checks.
3. `GET /api/v1/packet/{case_id}/fhir`: When `require_final` is set, calls `require_releasable_determination(packet)` instead of inline local checks.
4. `POST /api/v1/packet/{case_id}/ehr-push`: Calls `require_releasable_determination(packet)` instead of inline local checks.
5. `POST /api/v1/packet/{case_id}/appeal-letter`: Calls `require_releasable_determination(packet)` when `require_final` is set.
6. `GET /api/v1/packet/{case_id}/appeal-letter/pdf`: Calls `require_releasable_determination(packet)` when `require_final` is set.
7. `GET /api/v1/determination/{case_id}/final`: Calls `require_releasable_determination(adj)` instead of inline local checks.

All disparate local inline checks (`determination_stage != "FINAL"` or `is_releasable`) across release routes have been eliminated.

---

## 3. The Submit Endpoint Fix (`POST /packet/submit`)

`submit_coverage_to_insurance` in `app/api/routes.py` was rewritten to close all three findings:

1. **Authentication Elevation**:
   - Changed authentication dependency from `Depends(get_current_user)` to `Depends(get_verified_clinician_user)`.
   - Callers without the `Clinician` role or whose credentials are unverified (e.g. `Auditor`, `Admin`) receive `HTTP 403 Forbidden`.
2. **Already-FINAL Enforcement & Finalization Removal**:
   - The handler strictly verifies that the determination is **ALREADY FINAL** via `require_releasable_determination(packet or log, log=log)`. Provisional determinations receive `HTTP 412 Precondition Failed`.
   - All finalization code (`determination_stage = "FINAL"`, `is_releasable = True`, `human_sign_off_status = "SIGNED_OFF"`, and `HumanSignOffService.sign_off()`) has been removed from the submit handler. Finalization happens exclusively via the sign-off (`/sign-off`) or override (`/override`) endpoints.
3. **Honest Submission Receipt**:
   - Removed fabricated payer transmission and acceptance (`TRANSMITTED_ACCEPTED` is eliminated).
   - Generates an honest local submission reference labeled `LOCAL-SUBMISSION-REF-CMS-EDI-837-{date}-{hex}`.
   - Verbatim receipt fields:
     - `submission_status`: `"SUBMITTED_TO_PAYER"`
     - `local_submission_reference`: `"LOCAL-SUBMISSION-REF-CMS-EDI-837-..."`
     - `message`: `"Packet recorded as submitted for transmission; no payer response has been received (payer electronic gateway integration is not implemented)."`
4. **Signer Identity Validation**:
   - Validates that `request.signed_by` matches the authenticated clinician's username and credential title. Mismatches are rejected with `HTTP 400 Bad Request`. If omitted, the authenticated clinician's verified identity is automatically used.

---

## 4. The Stale Export Fix (Rebuild Packet on Change)

### Implementation
1. **Rebuild Helper (`app/api/release.py`)**:
   Created `rebuild_coverage_packet(adjudication, existing_packet)` to generate a fresh `CMSCoveragePacket` using `CoveragePacketGenerator.generate_packet(adjudication)`, synchronizing:
   - `adjudication_decision` (reflecting `override_decision` when an override is present)
   - `determination_stage` (`FINAL`)
   - `is_releasable` (`True`)
   - `human_sign_off_status` (`OVERRIDDEN_FINAL` or `SIGNED_OFF`)
   - `signed_by` and `signed_at`
   - `clinician_action_notes`
2. **Override Endpoint Integration**:
   After `HumanOverrideService.record_override`, the override handler:
   - Sets `overridden_adj.adjudication_decision = override_enum`
   - Rebuilds the packet via `rebuild_coverage_packet`
   - Updates `_EPHEMERAL_PACKETS[case_id] = rebuilt_packet`
   - Updates `log.full_packet_json = rebuilt_packet.model_dump_json()` and `log.decision = dec_upper`
   - Preserves original system output identically in `log.original_system_output_json`.
3. **Defense-in-Depth in `get_coverage_packet`**:
   If a cached packet in `_EPHEMERAL_PACKETS` has a decision or stage mismatch with `log`, it is automatically detected and rebuilt from the authoritative adjudication record before being returned.
4. **Sign-Off Endpoint Alignment**:
   `sign_off_clinical_determination` uses the same `rebuild_coverage_packet` helper to maintain complete consistency.

### Proof of Synchronization
- **Override to APPROVED**:
  - Case: `PT-***` on `NCD-20.4` with LVEF 45% (initially `DEFERRED_TO_HUMAN` / `DENIED`).
  - Clinician executes override to `APPROVED`.
  - `GET /packet/{case_id}` returns `adjudication_decision="APPROVED"`, `determination_stage="FINAL"`.
  - `GET /packet/{case_id}/pdf` generates PDF containing `"APPROVED"` bytes.
- **Override to DENIED**:
  - Case: `PT-***` on `LCD-L33829` (initially `APPROVED`).
  - Clinician executes override to `DENIED`.
  - `GET /packet/{case_id}` returns `adjudication_decision="DENIED"`, `determination_stage="FINAL"`.
  - `GET /packet/{case_id}/fhir?require_final=true` returns FHIR Bundle whose embedded `DocumentReference` decodes to `adjudication_decision="DENIED"`.

---

## 5. End-to-End Tests (`tests/test_v76_release_workflow.py`)

A dedicated test suite was created in `tests/test_v76_release_workflow.py`. The database setup fixture cleanly initializes SQLite test sessions without deadlock or hanging, completing in **3.55 seconds**.

### Exact Test Names & Results
```
tests/test_v76_release_workflow.py::test_v76_provisional_determination_cannot_be_submitted PASSED
tests/test_v76_release_workflow.py::test_v76_non_clinician_cannot_submit_even_for_final_determination PASSED
tests/test_v76_release_workflow.py::test_v76_verified_clinician_can_submit_final_determination_with_honest_receipt PASSED
tests/test_v76_release_workflow.py::test_v76_override_to_approved_rebuilds_packet_and_pdf_export_reflects_approved PASSED
tests/test_v76_release_workflow.py::test_v76_override_to_denied_rebuilds_packet_and_fhir_export_reflects_denied PASSED
tests/test_v76_release_workflow.py::test_v76_sign_off_and_override_lifecycle_preserves_audit_trail PASSED
tests/test_v76_release_workflow.py::test_v76_ehr_push_enforces_shared_gate_rejects_provisional PASSED
tests/test_v76_release_workflow.py::test_v76_submit_rejects_signer_identity_mismatch PASSED
```
**Test Command**: `pytest tests/test_v76_release_workflow.py -v`  
**Result**: **8 passed in 3.55s**

---

## 6. Verification and Regression Guard

### 1. Full Pytest Suite
- **Command**: `pytest -q`
- **Result**: **476 passed, 2 warnings in 291.56s (0:04:51)**
- Zero failures, zero regressions across all 476 tests.

### 2. Specialized Regression Test Suites
- **BENCH Tests**: `pytest tests/test_benchmark.py -v` -> **5 passed in 2.94s**
- **V1 Held-Out & Smart FHIR Tests**: `pytest tests/test_smart_fhir.py tests/test_v1_heldout_regressions.py -v` -> **11 passed in 19.96s**
- **API Test Suite**: `pytest tests/test_api.py -v` -> **18 passed in 35.59s**
- **Workflow & Override Tests**: `pytest tests/test_workflow_deferral_and_override.py tests/test_pdf_export.py -v` -> **8 passed in 2.87s**

### 3. Code Quality & Linting
- `ruff check app/core app/schemas --ignore E501`: **All checks passed!**
- `ruff check app/api/release.py --ignore E501`: **All checks passed!**
- `node --check app/static/js/app.js`: **Clean (Code 0)**

### 4. Git Diff Stat Verification
`git diff --stat` confirms that all modifications are strictly confined to release, schemas, routes, and test files:
```
 app/api/deps.py          |   3 +
 app/api/pdf_routes.py    |  11 ++--
 app/api/routes.py        | 162 ++++++++++++++++++++++++++++-------------------
 app/schemas/contracts.py |   1 +
 tests/test_api.py        |  48 ++++++++++++--
 app/api/release.py       |  92 ++++++++++++++++++++++++++++
 tests/test_v76_release_workflow.py | 303 +++++++++++++++++++++++++++++++++++++++
```
Zero changes were made to adjudication logic, judges, debates, advocate agents, concept maps, policies, or benchmark files.

---

## 7. Honest Status on Remaining Unproven Functionality

- **Payer Electronic Gateway Integration**: Direct electronic transmission to CMS EDI 837 clearinghouses remains unimplemented. As designed in this release, the `/packet/submit` endpoint now honestly records the internal submission record (`submission_status="SUBMITTED_TO_PAYER"`) and explicitly discloses that no external clearinghouse response was received.
