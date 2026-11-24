# Agentic v87 Delivery Report: UMLS Integration & Authority Hierarchy

**Delivery Date**: 2026-11-23  
**Head Anchor**: `934c6d1` (`934c6d1fc64e206dcab6a0850609f516ec2c7122`, parent `88de623`)  
> [!NOTE] **Provenance Correction (Prompt v88)**: The v87 measurement (`app/data/benchmarks/agentic_v87_three_mode_run.json`) ran on uncommitted v87 code before landing; its `metadata.git_head` records `934c6d1` (the parent anchor head), NOT the delivery head `6ecf756`. The measured code landed across commits `f6563bf` (implementation) + `7d42e76` (harness baseline-reuse fix) + `6ecf756` (docs delivery).
**Sequencing Context**: Suggestion Prompt v87 is a **BUILD** prompt delivering the National Library of Medicine (NLM) Unified Medical Language System (UMLS) UTS REST API integration. This capability serves as the scalable, authoritative foundation to resolve clinical synonymy and replace manual hand-attestation of draft concept-map entries (12 committed concepts vs 119 draft entries).

---

## 1. Executive Summary & Baseline Re-Anchoring

### Baseline Head & Verified Metrics
Prompt v87 re-anchored at `934c6d1` (v85 delivery head, as v86 had not landed). Baseline numbers recomputed from `app/data/benchmarks/agentic_v85_three_mode_run.json`:

| Mode | Map Used | Accuracy (Concordant / 84) | False Approvals | False Denials | Safe Deferrals | Synonymy Resolved |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Deterministic** | Committed (12) | **37 / 84 (44.0%)** | 0 | 2 | 45 | 0 / 19 |
| **Declarative (12)** | Committed (12) | **39 / 84 (46.4%)** | 0 | 0 | 45 | 0 / 19 |
| **Declarative (131)** | Merged (131) | **48 / 84 (57.1%)** | 0 | 0 | 36 | 10 / 19 |
| **Agentic (131)** | Merged (131) | **54 / 84 (64.3%)** | 0 | 0 | 30 | 14 / 19 |

*Baseline Efficiency (v85 Agentic)*:
- Judge Calls: 109
- Mean Wall-Clock Seconds: 27.70 s
- Cases Exceeding 60 s: 29
- Operational Budget Halts: 2

---

## 2. UMLS UTS Client Architecture

The UMLS integration is implemented in [`app/services/umls_client.py`](file:///e:/Class/GitHub/CarePolicyGuard/app/services/umls_client.py) with the following architectural specifications:

### 2.1 API Endpoint & Version Pinning
- **Endpoint**: Connects to the official NLM UTS REST API: `https://uts-ws.nlm.nih.gov/rest/search/{version}`
- **Pinned Version**: Set to `2024AB` by default (`UMLS_VERSION` in [`app/core/config.py`](file:///e:/Class/GitHub/CarePolicyGuard/app/core/config.py)), ensuring pinned, reproducible vocabulary releases.

### 2.2 Security & Authentication (Environment Only, Fail-Closed)
- **API Key**: Read strictly from the environment variable `UMLS_API_KEY` via [`app/core/config.py`](file:///e:/Class/GitHub/CarePolicyGuard/app/core/config.py).
- **Never Committed / Never Logged**: The API key is never written to repo files, test fixtures, artifacts, or emitted in log messages.
- **Fail-Closed**: If `UMLS_API_KEY` is empty, missing, or whitespace, the client logs a warning once and disables itself. All queries return `None` immediately without crashing or egressing network traffic.

### 2.3 Strict No-Note-Egress Boundary
A strict egress filter is enforced in `validate_term_egress_boundary()`:
1. **Length Limit**: Terms must be $\le 100$ characters.
2. **Whitespace**: No newlines (`\n`, `\r`) or tabs (`\t`).
3. **Sentence Punctuation & Delimiters**: The boundary regex in `app/services/umls_client.py:49` originally rejected sentence punctuation followed by whitespace or linebreaks (`r"[\n\r]|(?:\.\s+)|(?:\?\s+)|(?:\!\s+)|(?:\;\s+)"`). In Prompt v88, this regex was tightened to `r"[\n\r]|(?:\.\s+)|(?:\?\s+)|(?:\!\s+)|(?:\;\s+)|(?:[\.\?\!\;]$)"` to strictly reject any term that also ends in sentence punctuation (`.`, `?`, `!`, `;`). In practice, clinical notes are blocked from egress; terms sent by `llm_judge.py` are isolated clinical n-grams (≤ 4 words).
4. **Failure Behavior**: Any attempt to query a phrase violating these bounds is refused (returns `False`), ensuring patient clinical notes and narrative paragraphs never leave the boundary. *(Correction note: Original draft asserted that boundary violations raise a dedicated egress violation exception class; no such exception class exists in `app/services/umls_client.py` — `validate_term_egress_boundary()` returns a `bool` (`False` on violation), and `get_cui()` returns `None` on refusal).*

### 2.4 Caching Architecture
- **In-Memory Cache**: LRU/dictionary cache for immediate repeated queries within the same process.
- **Disk Cache**: Local file at `app/data/umls_cui_cache.json` (explicitly ignored in `.gitignore`), persisted atomically on writes to prevent repeated UTS round-trips.

---

## 3. Synonymy Check Order & Hierarchy Integration

UMLS is wired into the equivalence verification hierarchy in two distinct pipeline stages:

```
1. Exact Verbatim String Match
   └── Match -> EQUIVALENT (Confidence 1.0)
2. Committed Concept Map (12 human-attested concepts)
   └── Match -> EQUIVALENT (Confidence 1.0)
3. UMLS CUI Lookup (Authoritative NLM Ontological Equivalence)
   └── Same Concept Unique Identifier (CUI) -> EQUIVALENT (Confidence 0.98)
4. Local LLM Judge (Clinical Context & Paraphrase Disambiguation)
   └── Contextual check with adversarial cross-examination
5. Unproven / Deferral to Human Clinician
```

### 3.1 Integration in `app/core/concept_map.py:verify_equivalence`
When two clinical terms are evaluated:
1. Prohibited near-misses are checked first (`PROHIBITED_NEAR_MISSES`); any match strictly blocks equivalence.
2. Committed concept map is consulted.
3. If no committed concept matches, `_check_umls_equivalence(term_a, term_b)` is invoked. If both terms resolve to the same CUI in UMLS UTS, equivalence is confirmed with status code `EQUIVALENCE_CONFIRMED_VIA_UMLS: Both terms share CUI <cui>.`.

### 3.2 Integration in `app/core/llm_judge.py:judge_equivalence_sync`
Before calling the local LLM (`qwen2.5:3b`):
1. Evaluates clinical context for negation or contraindications.
2. If context is affirmative/unambiguous, queries the UMLS client for both terms.
3. If both share the same CUI, returns `JudgeEvaluation(verdict="EQUIVALENT", status_code="EQUIVALENCE_CONFIRMED_VIA_UMLS", confidence=0.98)` **without executing an LLM call**, reducing latency and saving local compute.

### 3.3 Committed Concept Map Invariant
- The 12 human-attested committed concepts remain **strictly unchanged**.
- The 119 draft concept map entries are **not** auto-approved; UMLS provides an independent authoritative ground truth rather than modifying draft YAML files.

---

## 4. Benchmark Measurement Results (84 Cases)

The full 84-case benchmark measurement was executed and saved to [`app/data/benchmarks/agentic_v87_three_mode_run.json`](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v87_three_mode_run.json).

### 4.1 Four-Mode Safety & Accuracy Comparison

| Mode | v85 Accuracy | v87 Accuracy | v85 FA | v87 FA | v85 FD | v87 FD | v85 Deferrals | v87 Deferrals | v85 Synonymy | v87 Synonymy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Deterministic** | 37/84 (44.0%) | **37/84 (44.0%)** | 0 | **0** | 2 | **2** | 45 | **45** | 0/19 | **0/19** |
| **Declarative (12)** | 39/84 (46.4%) | **39/84 (46.4%)** | 0 | **0** | 0 | **0** | 45 | **45** | 0/19 | **0/19** |
| **Declarative (131)** | 48/84 (57.1%) | **48/84 (57.1%)** | 0 | **0** | 0 | **0** | 36 | **36** | 10/19 | **10/19** |
| **Agentic (131)** | 54/84 (64.3%) | **54/84 (64.3%)** | 0 | **0** | 0 | **0** | 30 | **30** | 14/19 | **14/19** |

### 4.2 Agentic Efficiency & Performance Metrics

| Metric | v85 Baseline | v87 Delivery | Delta / Impact |
| :--- | :--- | :--- | :--- |
| **Total Judge Calls** | 109 | **107** | **-2 calls saved** (pre-judge short circuit) *(Correction note below)* |
| **Mean Wall-Clock Time** | 27.70 s | **27.67 s** | -0.03 s |
| **Mean Judge Latency** | 15,920.41 ms | **16,106.95 ms** | Stable ($\pm 1\%$) |
| **Cases Exceeding 60 s** | 29 | **29** | Exact parity |
| **Operational Budget Halts** | 2 | **2** | Exact parity |
| **Per-Case Decision Diff** | 0 | **0** | **100% decision concordance vs v85** |

> [!NOTE] **Efficiency Attribution Correction (Prompt v88)**: While total judge calls indeed dropped from 109 to 107 in the benchmark run, the parenthesized attribution *"pre-judge short circuit"* is **unsupported by artifact telemetry**. Grepping `app/data/benchmarks/agentic_v87_three_mode_run.json` confirms:
> - Occurrences of `"CUI"`: **0**
> - Occurrences of `"EQUIVALENCE_CONFIRMED_VIA_UMLS"`: **0**
> - Occurrences of `"umls"` (case-insensitive): **1** (solely `metadata.umls_version = "2024AB"`)
> 
> Because `UMLS_API_KEY` was not configured in the host environment during the measurement, the UMLS client failed closed as designed and resolved zero equivalences on the dev set. The -2 judge call variation is fully consistent with host-level Ollama sampling / timing nondeterminism and must not be claimed as an empirical UMLS efficiency win. The UMLS integration is validated by its test suite (8 mocked tests in `tests/test_v87_umls_integration.py`).

### 4.3 Key Vignette & Safety Audits
- **Target Cases (Revert Status at 0.65)**:
  - `DEV-LCD-KYPHO-APP`: `DEFERRED_TO_HUMAN` (expected, awaiting v86 span-normalization fix)
  - `DEV-NCD-CATARACT-APP`: `DEFERRED_TO_HUMAN` (expected, awaiting v86 span-normalization fix)
  - `DEV-NCD-PET-ONC-APP`: `DEFERRED_TO_HUMAN` (expected, awaiting v86 span-normalization fix)
- **v77 Rescues (All Preserved)**:
  - `DEV-LCD-PAD-ATHERO-APP`: `APPROVED`
  - `DEV-NCD-PACEMAKER-APP`: `APPROVED`
  - `DEV-NCD-SCS-APP`: `APPROVED`
  - `DEV-NCD-SGD-APP`: `APPROVED`
  - `DEV-OPD-SI-FUSION-APP`: `APPROVED`
- **SBRT and SI-Fusion Deliberation**:
  - `DEV-LCD-SBRT-APP`: `APPROVED` (41.13s, defense conceded: 0, CRIT-SBRT-01: `DEFENDED`)
  - `DEV-OPD-SI-FUSION-APP`: `APPROVED` (39.63s, defense conceded: 0, CRIT-SI-01: `DEFENDED`)
- **Guard Cost Audit**:
  - Exactly 2 promotions blocked by guard (`DEV-NCD-CATARACT-APP` on `CRIT-CAT-01`, `DEV-NCD-PET-ONC-APP` on `CRIT-PTONC-01`).

---

## 5. Test Suite Verification

A dedicated unit test suite was authored in [`tests/test_v87_umls_integration.py`](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_v87_umls_integration.py). Across all 10 release and delivery test suites, all 58 tests passed cleanly:

| Test Suite File | Tests | Status |
| :--- | :--- | :--- |
| `tests/test_v76_release_workflow.py` | 8 | **PASSED** |
| `tests/test_v77_concession_fix.py` | 6 | **PASSED** |
| `tests/test_v78_judge_in_loop.py` | 5 | **PASSED** |
| `tests/test_v79_app_release_fixes.py` | 8 | **PASSED** |
| `tests/test_v80_reviewer_workflow.py` | 6 | **PASSED** |
| `tests/test_v81_build_completion.py` | 4 | **PASSED** |
| `tests/test_v82_build_fixes.py` | 4 | **PASSED** |
| `tests/test_v84_concession_defense.py` | 5 | **PASSED** |
| `tests/test_v85_threshold_revert.py` | 4 | **PASSED** |
| `tests/test_v87_umls_integration.py` | 8 | **PASSED** |
| **Delivery Modules Total** | **58** | **58 / 58 PASSED (100%)** |

### Regression Suites:
- `tests/test_benchmark.py`: **5 / 5 PASSED**
- `tests/test_cross_mode_agreement.py`: **9 / 9 PASSED**
- `tests/test_pipeline_wiring.py`: **6 / 6 PASSED**
- **Combined Regression Suite Total**: **20 / 20 PASSED**

---

## 6. Code Quality & Ruff Audit

### Changed Files in v87:
```
app/core/config.py: 0 errors
app/core/concept_map.py: 0 errors
app/core/llm_judge.py: 0 errors
app/services/umls_client.py: 0 errors
tests/test_v87_umls_integration.py: 0 errors
```

### Tracked 11 Files Audit:
| File | Error Count | Bound | Status |
| :--- | :--- | :--- | :--- |
| `app/api/deps.py` | 15 | 17 | PASSED |
| `app/api/pas_routes.py` | 33 | 35 | PASSED |
| `app/services/deferral_queue.py` | 56 | 56 | PASSED |
| `app/api/routes.py` | 145 | 147 | PASSED |
| `app/api/pdf_routes.py` | 4 | 9 | PASSED |
| `app/api/release.py` | 0 | 0 | PASSED |
| `app/db/models.py` | 4 | 4 | PASSED |
| `app/schemas/contracts.py` | 0 | 0 | PASSED |
| `app/services/trace_service.py` | 0 | 0 | PASSED |
| `app/services/pdf_generator.py` | 15 | 15 | PASSED |
| `app/agents/packet_generator.py` | 9 | 9 | PASSED |
| **Total Across 11 Files** | **281** | **$\le 292$** | **PASSED** |

### Frontend JavaScript Audit:
- `node --check app/static/js/app.js`: Exit Code 0 (clean syntax).

---

## 7. CI & Build Verification

- **GitHub Actions Workflow Run**: [45342033973](https://github.com/Sumitkc74/CarePolicyGuard/actions/runs/45342033973) (also verified parent run [45340814580](https://github.com/Sumitkc74/CarePolicyGuard/actions/runs/45340814580))
- **Commit Head**: `6ecf756` (`6ecf7568df9c37554748026b405f417f552e0847`, delivery head; parent `7d42e76`, base `934c6d1`)
  *(Original report draft stated parent commit head `7d42e76`; corrected in place to delivery head `6ecf756`).*
- **Status**: **ALL GREEN / SUCCESS**
  - `Code Quality & Type Checking`: **SUCCESS**
  - `Unit, Integration & Fuzz Test Suite`: **SUCCESS** (519 tests passed, 0 failures)
  - `Docker Build & Health Verification`: **SUCCESS**

