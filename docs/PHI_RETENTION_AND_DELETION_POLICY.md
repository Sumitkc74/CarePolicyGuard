# PHI Data Minimization, Retention, and Deletion Policy

## 1. Statutory Context & Principles

CarePolicyGuard complies with the **HIPAA Privacy and Security Rules** (45 CFR § 164.502(b) Minimum Necessary, § 164.514 Other Requirements Relating to Uses & Disclosures of Protected Health Information, and § 164.526 Amendment of Protected Health Information).

### Core Principles
1. **Zero Raw Clinical Narrative Retention in Storage**:
   - The multi-agent pipeline ingests raw clinical narratives in-memory, executes immediate algorithmic Safe Harbor PHI de-identification via `sanitize_phi()`, and evaluates criteria against the de-identified representation.
   - All persistence layers (relational databases, SQLite, PostgreSQL, JSON blobs, and ephemeral server caches) store only the sanitized clinical narrative (`sanitized_ehr`), never unmasked clinical notes.
2. **Replay Determinism from Sanitized Text**:
   - Because `sanitize_phi()` redacts direct identifiers (names, dates, MRNs, SSNs, phone numbers, email addresses) while preserving clinical terms, measurements, dosages, and temporal relationships, re-evaluating the stored sanitized text (`pipeline.adjudicate(..., ehr_narrative=log.full_ehr_text)`) deterministically reproduces identical criteria determinations, confidence scores, and audit hashes.
3. **Cryptographic Chain of Custody**:
   - Every adjudication generates a deterministic SHA-256 audit hash binding the policy ID, sanitized evidence spans, evaluated criteria, and calibrated confidence.
   - Data minimization and sanitization preserve cryptographic audit trails without data loss.

---

## 2. Retention Horizons & Configuration

Configured via environment variables in `app/core/config.py`:

| Parameter | Default | Purpose |
| :--- | :--- | :--- |
| `RETENTION_DAYS_ADJUDICATION` | `30` | Active retention horizon (days) for adjudication log records. Records older than this threshold are eligible for archival or tombstone transition. |
| `RETENTION_DAYS_QUEUE` | `14` | Retention horizon (days) for unaddressed items in the human deferral work queue. |
| `ENABLE_PHI_MASKING` | `True` | Enforces Safe Harbor regex and named-entity masking across all ingestion pipelines. |
| `DEV_OTP_DELIVERY_ENABLED` | `False` | Development-only second-factor OTP delivery channel. **Strictly prohibited and forced off** in production environments (`ENVIRONMENT=production` or `DEBUG=False`). |

---

## 3. Right to Erasure & Deletion Operation

Under HIPAA Safe Harbor and GDPR/CCPA data privacy standards, clinical organizations must support permanent erasure of patient records upon request while maintaining audit integrity.

### Erasure Endpoint: `DELETE /api/v1/determination/{case_id}`
- **Authentication**: Requires valid Bearer JWT from an authorized user (owner, signing clinician, or IT Administrator).
- **Access Control**: Anti-enumeration oracle defense ensures unauthorized callers receive HTTP 404 rather than leaking case existence.
- **Scrubbing Action**:
  - `full_ehr_text` is replaced with `"[SCRUBBED - RIGHT TO ERASURE]"`.
  - `sanitized_ehr_preview` is replaced with `"[SCRUBBED - RIGHT TO ERASURE]"`.
  - `criterion_evaluations_json` and `evidence_spans_json` are wiped (`"[]"`).
  - `full_adjudication_json` and `full_packet_json` are cleared (`None`).
  - `submission_status` is marked as `"ERASED_TOMBSTONE"`.
  - Ephemeral in-memory caches (`_EPHEMERAL_PACKETS`, `_EPHEMERAL_EHR_TEXTS`, `_EPHEMERAL_ADJUDICATIONS`) are purged.
- **Tombstone Audit Integrity**: The case ID, policy ID, decision timestamp, and SHA-256 cryptographic seal remain preserved to satisfy CMS RAC/MAC statutory audit compliance without holding patient health data.

---

## 4. One-Time Historical Database Sanitization

For pre-existing databases or deployments initialized under earlier versions, a non-destructive sanitization script is provided:

```bash
# Dry-run inspection (reports affected records without writing changes)
python scripts/cleanup_raw_phi.py --dry-run

# Execute one-time sanitization
python scripts/cleanup_raw_phi.py
```

The script:
1. Iterates over all rows in `adjudication_logs`.
2. Applies `sanitize_phi()` to `full_ehr_text`, `sanitized_ehr_preview`, and JSON payload fields.
3. Preserves `audit_hash`, `determination_stage`, `human_sign_off_status`, `signed_by`, and case identifiers.
4. Commits changes atomically without silent auto-wipe or data destruction.

