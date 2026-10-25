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

## 6. Coordinated Vulnerability Disclosure

To report a suspected security vulnerability or compliance concern, please submit a detailed report to the clinical engineering team:
- Email: `security@carepolicyguard.med`
- Expected Response Window: Within 24 hours
- PGP Encryption: Available upon request

