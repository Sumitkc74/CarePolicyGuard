# CarePolicyGuard Security & Compliance Architecture

## 1. Security Overview

CarePolicyGuard is an enterprise Clinical Decision Support (CDS) platform designed for healthcare organizations, Medicare administrative contractors (MACs), and clinical review teams. This document details the security architecture, cryptographic standards, threat mitigations, and compliance mappings implemented across the application.

---

## 2. HIPAA Technical Safeguards Mapping (45 CFR § 164.312)

| HIPAA Regulation | Regulatory Requirement | CarePolicyGuard Implementation |
| :--- | :--- | :--- |
| **§ 164.312(a)(1)** | **Unique User Identification** | Each clinician, reviewer, and auditor must authenticate with a unique credential pair, verified NPI, state license, and role. |
| **§ 164.312(a)(2)(i)** | **Multi-Factor Authentication (MFA)** | Mandatory secondary factor enforcement: RFC 6238 TOTP (Google/Microsoft/Duo Authenticator), Email OTP, and SMS OTP. |
| **§ 164.312(a)(2)(iii)** | **Automatic Logoff** | Client-side inactivity watcher automatically locks and terminates active sessions after 15 minutes of idle time. |
| **§ 164.312(a)(2)(iv)** | **Encryption at Rest & in Transit** | PBKDF2-HMAC-SHA256 (100,000 iterations) password hashing; HS256 signed stateless JWT session tokens; TLS with HSTS headers. |
| **§ 164.312(b)** | **Audit Controls** | Immutable audit logs recording all clinical evaluations; exportable as standard HL7 FHIR R4 `AuditEvent` bundles for enterprise SIEM ingestion (Splunk, Datadog). |
| **§ 164.312(c)(1)** | **Data Integrity Verification** | Deterministic SHA-256 cryptographic chain-of-custody seals binding patient ID, policy criteria, evidence spans, and confidence scores. |
| **§ 164.312(e)(1)** | **Transmission Security** | OWASP HTTP security headers (`Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`). |

---

## 3. Data Privacy & Zero-Retention Architecture (45 CFR § 164.514)

### A. HIPAA Safe Harbor De-Identification
Prior to algorithmic criteria evaluation or database logging, all clinical narratives pass through an automated de-identification engine (`sanitize_phi()`):
- Direct Identifiers Redacted:
  - Social Security Numbers (SSNs) -> `[REDACTED-SSN]`
  - Medicare Beneficiary Identifiers (MBIs) -> `[REDACTED-MBI]`
  - Patient Full Names -> `[REDACTED-NAME]`
  - Full Dates of Birth (DOBs) -> `[REDACTED-DOB]`
  - Medical Record Numbers (MRNs) -> `[REDACTED-MRN]`
  - Telephone & Mobile Numbers -> `[REDACTED-PHONE]`
  - Email Addresses -> `[REDACTED-EMAIL]`
  - Street Addresses & Zip Codes -> `[REDACTED-ADDRESS]` / `[REDACTED-ZIP]`
- Patient Identifier Masking: All stored database references use truncated representations (e.g., `PT-***8821`).

### B. Ephemeral In-Memory Processing & Right to Erasure
- **In-Memory Volatility**: Consultation notes evaluated interactively are held ephemerally in volatile memory. If an evaluation is not explicitly saved into an authorized coverage packet, raw chart text is discarded.
- **Audit Ledger Purge**: Authorized administrators can execute `DELETE /api/v1/audit/clear-ephemeral` or trigger the UI "Purge All Cached Records" action to wipe unsubmitted test records immediately.

---

## 4. Threat Model & Vulnerability Mitigations

### A. Injection Attacks (SQLi, Command Injection)
- **Parameterized Queries**: All database queries are orchestrated through the SQLAlchemy ORM using prepared statements and bound parameter markers. Raw string formatting is strictly forbidden.
- **Type-Safe Validation**: Pydantic input models enforce strict typing, rejecting non-conformant payloads prior to database query execution.

### B. Client-Side DevTools Manipulation (Zero-Trust UI)
- The web frontend is strictly a presentation layer.
- Clinical determinations, statutory waiting periods, CPT validation, and PDF packet generation execute 100% server-side.
- Modifying DOM elements, badges, or local storage values in browser DevTools has zero impact on server decisions or signed PDF packets.

### C. Brute-Force & Credential Stuffing
- Thread-safe sliding-window rate limiter enforces a threshold of 20 authentication attempts per minute per IP address.
- Exceeding the threshold returns standard HTTP `429 Too Many Requests` with a dynamic `Retry-After` header.

### D. Session Hijacking & Remote Revocation
- Active sessions track IP addresses, user-agent fingerprints, and login timestamps in the `user_sessions` table.
- Compromised or abandoned device sessions can be remotely revoked from any authenticated device, immediately terminating access regardless of remaining JWT lifespan.

### E. Container Hardening
- The production Docker image (`python:3.12-slim`) drops all root capabilities and runs under an unprivileged system account (`appuser:appgroup`, UID/GID `1001:1001`).
- Native container health checks (`urllib`) poll `/health` every 30 seconds.

---

## 5. Regulatory Interoperability Standards

CarePolicyGuard complies with the complete CMS-0057-F prior-authorization burden-reduction framework:

1. **HL7 Da Vinci CRD (Coverage Requirements Discovery)**: CDS Hooks 1.0 discovery at `/cds-services` and real-time order-signing evaluation at `/api/v1/cds-services/medicare-crd-coverage-check`.
2. **HL7 Da Vinci DTR (Documentation Templates & Rules)**: FHIR R4 Questionnaire delivery at `/api/v1/dtr/questionnaire/{policy_id}` and automated `$populate` operation at `/api/v1/dtr/populate`.
3. **HL7 Da Vinci PAS (Prior Authorization Support)**: FHIR R4 Claim `$submit` operation at `/api/v1/pas/submit` returning standard `ClaimResponse` resources.
4. **HL7 FHIR R4 AuditEvent**: Chronological audit trail export at `/api/v1/audit/trail/fhir-audit-event` for enterprise SIEM integration.

---

## 6. Cryptographic Secret Management & Key Rotation

- **Zero Hardcoded Secrets**: CarePolicyGuard requires operators to inject an authentic cryptographic secret (`SECRET_KEY`) at runtime. There are no fallback default credentials in application code or Docker Compose manifests.
- **Fail-Fast Enforcement**: Application startup and container initialization strictly validate that `SECRET_KEY` is non-empty and does not match any known placeholder string.
- **Mandatory User Action (Key Rotation Notice)**: The historical documentation default `SECRET_KEY` is permanently blocklisted. Any historical deployment that previously utilized that default key must be immediately rotated by generating a new cryptographically secure secret (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

### Mandatory Operator Action: Rotation or Deletion of Seeded Demo Accounts

Any deployment that ever ran with seeded demo accounts (specifically accounts configured for the admin, clinician, doctor, or auditor roles) must delete those accounts or rotate their passwords immediately. The historical demo passwords for these roles were published in this repository and must be treated as compromised.

Application code cannot verify whether an existing deployment has completed this rotation or deletion — this is strictly an operator and administrative action, not an automated system guarantee.

In the hardened codebase:
1. Hardcoded demo passwords have been completely purged from application configuration and source code.
2. Demo account seeding is disabled by default (`SEED_DEMO_USERS=false`).
3. When seeding is explicitly enabled for development environments, passwords must be supplied exclusively via environment variables (`DEMO_ADMIN_PASSWORD`, `DEMO_CLINICIAN_PASSWORD`, `DEMO_AUDITOR_PASSWORD`, `DEMO_DOCTOR_PASSWORD`) with no default fallback. Startup will fail immediately if any required environment variable is missing or empty.
4. Demo-seeded accounts carry `is_demo_user=True` and are strictly segregated from production: they do NOT count as production administrators and cannot close the production bootstrap gateway.

---

## 7. Clinician Verification & Account Provisioning Architecture (Separation of Duties)

### A. Separation of Authority
CarePolicyGuard enforces a strict administrative separation of duties between account provisioning and medical credential verification:

```
[System Operator / Admin] --(Provisions)--> Account Exists (UNVERIFIED, Cannot Sign)
                                                      |
[Primary Source / Credentialing] --(Verifies)--------+--> Signing Authority Unlocked
```

1. **Admins Provision, Never Self-Grant Verification**:
   - Administrators create or invite clinician accounts (`POST /api/v1/admin/users/clinicians`).
   - Accounts are created **unverified** (`is_verified_medical_pro=False`).
   - Admin provisioning never generates or invents an NPI, clinical degree, or specialty.
   - Self-registration requesting the Admin role is strictly rejected with HTTP 403 Forbidden.
2. **Primary-Source Credentialing Authority**:
   - Verification is performed exclusively via real-time primary-source lookup (`POST /api/v1/credentialing/verify/nppes`) against the CMS NPPES National Provider Identifier Registry API or manual review by a dedicated `Credentialing` role (`POST /api/v1/credentialing/verify/manual`).
   - Requires an authentic name match between the account holder and the registered NPPES provider record.
   - Fails closed on network timeout, registry unreachable, or name mismatch.
3. **Mandatory Two-Action Rule**:
   - In small deployments where the same operator holds both Administrator and Credentialing roles, the system strictly enforces two distinct recorded actions with two distinct immutable audit entries (one provisioning event, followed by an independent credentialing verification event). Single-button "provision-and-verify" bypasses are prohibited.

### B. Production Bootstrap Administrator Procedure
Production environments must initialize their initial administrator through an explicit, one-time bootstrap procedure — never through public self-registration:

1. **Operator CLI Bootstrap Command (Recommended)**:
   ```bash
   python -m app.cli bootstrap-admin --email admin@hospital.org --password "StrongInitialPassword!2026" --name "System Administrator"
   ```
2. **Deployment Environment Bootstrap**:
   Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in the deployment orchestration environment (Kubernetes secret, AWS ECS task definition). The application will bootstrap the first administrator on initial startup.
3. **Permanent Gateway Closure**:
   Once the first production administrator account is provisioned (`is_production_admin_seeded(db) == True`), the bootstrap path permanently closes itself. Any subsequent bootstrap attempts via CLI or environment variables are rejected and recorded in security audit logs. Subsequent administrators can only be created by an authenticated administrator via `POST /api/v1/admin/users/admins`.
4. **First-Login Security Enforcement**:
   The bootstrap administrator is flagged with `must_change_password=True` and `must_setup_mfa=True`. The administrator must update their password and finalize secondary-factor enrollment via `POST /api/v1/auth/bootstrap/complete-setup`.
5. **Operator Credential Recovery (No Backdoors)**:
   CarePolicyGuard contains zero backdoor endpoints, reset tokens, or hardcoded recovery keys. If all production administrator credentials are lost, recovery requires an out-of-band operator action directly on the underlying database engine:
   ```sql
   -- Direct database operator action outside application code:
   UPDATE users SET is_active = 0 WHERE role = 'Admin';
   -- Operator then restarts the service with new BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD
   -- or executes the CLI bootstrap command directly on the host.
   ```

### C. Legacy Self-Registered Admin Accounts Remediation
Historical deployments may contain administrator accounts created via the open self-registration endpoint prior to remediation.
- **Automated Startup Check**: `audit_self_registered_admins(db)` automatically executes on startup, identifying any Admin account that was not created via bootstrap, demo seed, or authorized admin provisioning.
- **Immediate Suspension**: Suspicious legacy admin accounts are immediately suspended (`is_active=False`) with an alert logged to the operator.
- **Mandatory Operator Action**: System operators must review the suspended accounts, verify identities out-of-band, and either permanently delete the accounts from the database or re-provision them through authorized admin workflows.

### D. Credential Expiry & Annual Re-verification Policy
Medical licensure and NPI registrations expire and require periodic re-credentialing:
- **Policy Choice**: Verification records track `verification_expires_at`, set by default to 365 days (`CREDENTIAL_VERIFICATION_VALIDITY_DAYS=365`) from the date of primary-source verification.
- **Hard Gate Enforcement**: If a clinician's verification has expired, `get_verified_clinician_user` immediately blocks all new clinical sign-offs with HTTP 403 Forbidden until primary-source or manual re-verification is completed.
- **Non-Retroactive Invariant**: Revocation or expiration blocks new sign-offs immediately; it never alters, invalidates, or deletes past signed determinations, which remain permanently auditable.

### E. Downgrade Migration for Legacy Accounts (No Grandfathering)
Existing accounts that were previously marked as "verified" purely via format checks (`NPPES_CMS_LUHN_VERIFIED` / `FORMAT_CHECK_ONLY`) or OAuth auto-provisioning are automatically downgraded to unverified pending status upon application upgrade. Grandfathering is strictly prohibited to eliminate legacy credentialing vulnerabilities.

---

## 8. Coordinated Vulnerability Disclosure

To report a suspected security vulnerability or compliance concern, please submit a detailed report to the clinical engineering team:
- Email: `security@carepolicyguard.med`
- Expected Response Window: Within 24 hours
- PGP Encryption: Available upon request

