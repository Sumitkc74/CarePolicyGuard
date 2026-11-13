# Durable Audit Record: `NCD-20.4` Silent Default Inventory

**Audit Head Hash**: `7ac838a18ddbffe0a65d8a4b13514f0d79a49efe`  
**Audit Verification Command**: `git grep -n "NCD-20.4" -- "app/**/*.py"`  
**Audit Date**: November 13, 2026  
**Scope**: Complete census of every reference to `NCD-20.4` in the application source tree to verify elimination of silent default fallbacks, record legitimate policy-specific code paths, and track open issues.

---

## 1. Audit Summary & Verdict Criteria

Each appearance of `NCD-20.4` is evaluated against strict architectural and clinical safety standards:
- **ELIMINATED**: Previously operated as an unselected fallback or silent default; now completely removed and replaced with explicit `"AUTO"` handling, shortlist pre-selection, or documentation alert deferrals.
- **LEGITIMATE**: Grounded in application logic where `NCD-20.4` is explicitly specified by the caller, serves as a mock fixture for unit tests, or represents policy-specific clinical knowledge (e.g., CPT 33249 defibrillator billing codes, 40-day waiting periods). A descriptive label of what the code does is not acceptable as a justification.
- **OPEN**: Operates as a silent default or unprompted fallback that bypasses clinician review or the shortlist service, not yet resolved.

---

## 2. Complete Codebase Census Table

| File & Line | Code Context | Verdict | Code-Grounded Justification |
| :--- | :--- | :---: | :--- |
| `app/agents/benchmark_engine.py:16` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Fixture configuration: explicit benchmark policy for ischemic cardiomyopathy ICD test vignettes. |
| `app/agents/benchmark_engine.py:60` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Fixture configuration: explicit benchmark policy for non-ischemic cardiomyopathy test vignettes. |
| `app/agents/benchmark_engine.py:96` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Fixture configuration: explicit benchmark policy for primary prevention ICD test vignettes. |
| `app/agents/benchmark_engine.py:198` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Benchmark condition B runner fixture: assigns known policy target to benchmark case. |
| `app/agents/benchmark_engine.py:307` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Benchmark condition C runner fixture: assigns known policy target to benchmark case. |
| `app/agents/criteria_evaluator.py:1011` | `policy_id = getattr(policy, "policy_id", str(policy)) if policy else "NCD-20.4"` | **OPEN** | Fallback policy object mock when `policy` parameter is omitted in `evaluate_patient_against_policy()`. Used by CDS hooks path. |
| `app/agents/packet_generator.py:20` | `if policy_id == "NCD-20.4":` | **LEGITIMATE** | Policy-specific billing metadata: returns CPT codes `33249`, `93641` and ICD-10 `I50.22`, `I25.10` strictly when caller explicitly evaluates NCD-20.4. |
| `app/agents/packet_generator.py:103` | `if adjudication.policy_id == "NCD-20.4":` | **LEGITIMATE** | Form generation branch: attaches shared decision-making (SDM) encounter and 90-day validity attestations specific to CMS NCD-20.4 regulations. |
| `app/agents/pipeline.py:176` | `# Delete fallback to NCD-20.4. When AUTO has no pre-selected policy...` | **LEGITIMATE** | Documentation comment explaining the architectural elimination of silent defaults in the multi-agent pipeline. |
| `app/agents/pipeline.py:1126` | `MockPolicy("NCD-20.4", "Implantable Automatic Defibrillators", "Cardiology")` | **LEGITIMATE** | In-memory policy catalog seed fixture used solely during initial SQLite cold-start when policy table is unpopulated. |
| `app/agents/pipeline.py:1266` | `if policy_id == "NCD-20.4":` | **LEGITIMATE** | Cold-start mock criteria fixture: returns statutory LVEF and NYHA criteria definitions when database policy table is empty. |
| `app/agents/policy_retriever.py:11` | `"NCD-20.4": ["implantable cardioverter defibrillator", ...]` | **LEGITIMATE** | Retrieval index seed data: domain-specific lexical synonyms and keyword anchors for NCD-20.4. |
| `app/agents/policy_retriever.py:199` | `"NCD-20.4": {"title": "Implantable Automatic Defibrillators", ...}` | **LEGITIMATE** | In-memory policy dictionary definition containing CMS statutory titles and categories. |
| `app/api/batch_routes.py:154` | `row_lower.get("policy_id") or ... or "NCD-20.4"` | **OPEN** | Batch CSV ingestion: silently assigns NCD-20.4 to any batch CSV row omitting a policy column, rather than routing through AUTO shortlist. |
| `app/api/batch_routes.py:203` | `row_lower.get("policy_id") or ... or "NCD-20.4"` | **OPEN** | Batch Excel (.xlsx) ingestion: silently assigns NCD-20.4 to spreadsheet rows omitting a policy column. |
| `app/api/batch_routes.py:237` | `"policy_id": item.get("policy_id") or "NCD-20.4"` | **OPEN** | Batch JSON ingestion: assigns NCD-20.4 if JSON item omits `policy_id`. |
| `app/api/batch_routes.py:252` | `policy_id = candidates[0]["policy_id"] if candidates and ... > 0.05 else "AUTO"` | **ELIMINATED** | Fixed in commit `7ac838a18ddbffe0a65d8a4b13514f0d79a49efe` (v48). Changed silent fallback from `"NCD-20.4"` to `"AUTO"`, routing unstructured batch notes through shortlist pre-selection. |
| `app/api/cds_hooks_routes.py:100-101` | `target_policy_id = "NCD-20.4"` (plus lines 110-112 `db.query(MedicarePolicy).first()`) | **OPEN** | **OPEN — silent default, not fixed in this session, owned by v41** (cds_hooks_routes.py:100-101 default + keyword guessing, and the db.query(MedicarePolicy).first() fallback a few lines below). |
| `app/api/dtr_routes.py:13` | `policy_id: str = Field(..., description="CMS Policy Identifier, e.g. 'NCD-20.4'...")` | **LEGITIMATE** | OpenAPI schema contract documentation example; `policy_id` is a strictly required field from the API caller (`Field(...)`). |
| `app/api/dtr_routes.py:58` | `if pid == "NCD-20.4":` | **LEGITIMATE** | Deterministic questionnaire generator: builds DTR Questionnaires for NCD-20.4 only when explicitly requested by caller via required `policy_id` parameter. |
| `app/api/dtr_routes.py:162` | `if pid == "NCD-20.4":` | **LEGITIMATE** | Deterministic response builder: evaluates pre-population answers for NCD-20.4 only when requested under explicit caller-supplied `policy_id`. |
| `app/api/pas_routes.py:66` | `target_policy_id = "NCD-20.4"` | **OPEN** | FHIR Prior Authorization Support (PAS): default initial assignment for `$submit` when clinical narrative lacks recognized keywords and claim lacks CPT codes. |
| `app/api/pas_routes.py:84` | `elif code in ["33249", "33216"]: target_policy_id = "NCD-20.4"` | **LEGITIMATE** | Code-driven mapping: CPT codes 33249 and 33216 are statutory procedure codes for transvenous pacemaker/defibrillator insertion under NCD-20.4. |
| `app/api/routes.py:454` | `Retrieves a specific Medicare policy by ID (e.g. NCD-20.4, LCD-L33829).` | **LEGITIMATE** | Docstring documentation for `GET /api/v1/policies/{policy_id}` endpoint. |
| `app/api/routes.py:871` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Practice case preset PT-101: explicit educational demo fixture for cardiology clinic cohort. |
| `app/api/routes.py:882` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Practice case preset PT-102: explicit educational demo fixture for cardiology clinic cohort. |
| `app/api/routes.py:893` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | Practice case preset PT-103: explicit educational demo fixture for cardiology clinic cohort. |
| `app/api/routes.py:1087` | `suggested_policy = "NCD-20.4"` | **ELIMINATED** | Fixed in commit `7ac838a18ddbffe0a65d8a4b13514f0d79a49efe` (v48) and hardened in this session. Replaced with `PolicyShortlistService.compute_shortlist()`. Suggested policy is `None` unless pre-selected under margin rule. |
| `app/api/routes.py:1151` | `policy_id = "NCD-20.4"` | **ELIMINATED** | Fixed in commit `7ac838a18ddbffe0a65d8a4b13514f0d79a49efe` (v48). Unselected notes pass `"AUTO"` to pipeline, triggering shortlist evaluation and returning `DEFERRED_TO_HUMAN` (`policy_id="NONE"`) for off-topic or ambiguous records. |
| `app/db/models.py:106` | `policy_id = Column(...) # e.g., 'NCD-20.4'` | **LEGITIMATE** | ORM model schema comment illustrating Medicare policy primary key format. |
| `app/schemas/contracts.py:120, 211, 298, 699` | `description="... e.g., NCD-20.4"` | **LEGITIMATE** | Pydantic schema field documentation examples. |
| `app/schemas/declarative_policy.py:60` | `description="... e.g. NCD-20.4"` | **LEGITIMATE** | Declarative policy schema field documentation example. |
| `app/services/appeal_generator.py:19` | `"NCD-20.4": [...]` | **LEGITIMATE** | Appeal template repository: statutory Medicare appeal citations specific to ICD denials. |
| `app/services/billing_validator.py:40, 120` | `"NCD-20.4": {...}` | **LEGITIMATE** | Billing validator rule table: CPT/ICD-10 crosswalk rules specific to defibrillator procedures. |
| `app/services/cms_sync.py:28` | `"policy_id": "NCD-20.4"` | **LEGITIMATE** | CMS sync registry mock fixture for local offline testing. |
| `app/services/timeline_analyzer.py:97` | `if policy_id == "NCD-20.4":` | **LEGITIMATE** | Clinical waiting period engine: implements the mandatory CMS 40-day post-myocardial infarction / 90-day post-revascularization waiting period required under NCD-20.4 Section A. |

---

## 3. Explicit Ownership of Open Items

1. **CDS Hooks (`app/api/cds_hooks_routes.py:100-113`)**:
   - Status: **OPEN — silent default, not fixed in this session, owned by v41** (cds_hooks_routes.py:100-101 default + keyword guessing, and the db.query(MedicarePolicy).first() fallback a few lines below).
   - Architectural resolution belongs to the dedicated CRD & DTR overhaul session (v41), which specifies introducing a proper policy picker, CDS card warning indicator, and `NOT_DETERMINED` documentation alert rather than an ad-hoc patch.
2. **Batch File Uploads (`app/api/batch_routes.py:154, 203, 237`)**:
   - Status: **OPEN**. Batch tabular rows (CSV, Excel, JSON) currently default missing policy identifiers to `NCD-20.4`. In a future batch hardening session, these should be updated to default to `"AUTO"` so each row invokes the shortlist service individually.
3. **FHIR PAS (`app/api/pas_routes.py:66`)**:
   - Status: **OPEN**. FHIR Prior Authorization claim submissions with unmapped narratives default to `NCD-20.4` before checking CPT codes. Belongs to PAS FHIR compliance roadmap.
