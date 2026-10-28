# CarePolicyGuard Architecture and Design Specification

This document provides visual architectural, relational, sequence, state, and interoperability diagrams for the **CarePolicyGuard** clinical adjudication and prior authorization attestation platform.

Standalone image files are saved directly in `docs/images/` as both **PNG** and **SVG** formats for use in presentations, reports, and documentation.

---

## 1. High-Level System Architecture

CarePolicyGuard is structured as a tiered, HIPAA-compliant prior authorization adjudication platform. It decouples interface concerns, API orchestration, deterministic clinical inference, cryptographic integrity auditing, and external healthcare integrations.

![1. High-Level System Architecture](images/01_system_architecture.png)

*Direct image files: [PNG](images/01_system_architecture.png) | [SVG](images/01_system_architecture.svg)*

```mermaid
flowchart TB
    subgraph UI ["User Interfaces"]
        Clinician["Clinician Workspace"]
        Batch["Batch Roster Engine"]
        Auditor["Auditor Portal"]
        EHR["EHR CDS Hooks"]
    end

    subgraph Gateway ["API Gateway & Security"]
        API["FastAPI Gateway"]
        Auth["Auth & MFA Service"]
        HIPAA["HIPAA PHI Masker"]
    end

    subgraph Pipeline ["Multi-Agent Clinical Pipeline"]
        Agent1["Agent 1: Policy Retrieval"]
        Agent2["Agent 2: Criteria Evaluation"]
        Agent3["Agent 3: Adversarial Verifier"]
        Gate{"Agent 4: Abstention Gate<br/>(tau >= 0.85)"}
        
        Approved["Approved"]
        Denied["Denied"]
        Deferred["Deferred to MD"]
        
        Agent5["Agent 5: Defense Packet Generator"]
    end

    subgraph Storage ["Data & Audit Layer"]
        DB[("Relational Database")]
        Ledger["SHA-256 Audit Ledger"]
    end

    subgraph External ["External Systems"]
        CMS["CMS MAC Clearinghouse"]
        SMTP["Google SMTP Server"]
    end

    UI --> API
    API --> Auth
    API --> HIPAA
    API --> Agent1

    Agent1 --> Agent2
    Agent2 --> Agent3
    Agent3 --> Gate

    Gate -- "Pass" --> Approved
    Gate -- "Exclusion" --> Denied
    Gate -- "Low Conf" --> Deferred

    Approved --> Agent5
    Denied --> Agent5
    Deferred --> Agent5

    Agent5 --> DB
    Agent5 --> Ledger
    Agent5 --> CMS
    Auth -. "Email OTP" .-> SMTP
```

---

## 2. Entity-Relationship Data Model (ERD)

The data model enforces relational integrity across users, sessions, national/local Medicare coverage determinations, individual criteria, and immutable adjudication ledgers.

![2. Entity-Relationship Data Model](images/02_entity_relationship_erd.png)

*Direct image files: [PNG](images/02_entity_relationship_erd.png) | [SVG](images/02_entity_relationship_erd.svg)*

```mermaid
erDiagram
    User ||--o{ UserSession : "establishes"
    User ||--o{ AdjudicationLog : "signs and attests"
    MedicarePolicy ||--|{ PolicyCriterion : "defines"
    MedicarePolicy ||--o{ AdjudicationLog : "governs"

    User {
        int id PK
        string username UK
        string email UK
        string hashed_password
        string role "Clinician | Auditor | Admin"
        boolean is_active
        string npi_number "Indexed"
        string medical_license
        string credential_title "MD | DO | NP | PA-C"
        string specialty
        string organization
        boolean is_verified_medical_pro
        string mfa_method "email_otp | totp_app | sms_otp"
        string totp_secret
        string active_otp_code
        datetime otp_expires_at
        datetime created_at "Indexed"
        datetime updated_at
    }

    UserSession {
        int id PK
        string session_id UK "Indexed"
        int user_id FK
        string device_name
        string ip_address
        boolean is_revoked
        datetime revoked_at
        datetime created_at "Indexed"
        datetime last_active_at
    }

    MedicarePolicy {
        int id PK
        string policy_id UK "Indexed"
        string title
        string jurisdiction
        string effective_date
        string category
        text description
        datetime created_at "Indexed"
    }

    PolicyCriterion {
        int id PK
        int policy_id FK "Indexed"
        string criterion_code "Indexed"
        string name
        text description
        text clinical_intent
        boolean is_exclusion
        string required_temporal_window
        text keywords
        float min_score
        datetime created_at "Indexed"
    }

    AdjudicationLog {
        int id PK
        string case_id UK "Indexed"
        string patient_id_masked "Indexed"
        string policy_id "Indexed"
        string decision "APPROVED | DENIED | DEFERRED_TO_HUMAN"
        string idempotency_key UK
        boolean abstention_status
        text abstention_reason
        float calibrated_confidence
        float raw_confidence
        text criterion_evaluations_json
        text evidence_spans_json
        text adversarial_audits_json
        string audit_hash "SHA-256 Indexed"
        string submission_status "PENDING_REVIEW | SUBMITTED"
        string signed_by
        datetime signed_at
        string payer_transaction_id
        int user_id FK
        datetime created_at "Indexed"
    }
```

---

## 3. Sequence Diagram: Prior Authorization Adjudication and Signing Flow

This sequence traces the clinical adjudication pipeline from initial note ingestion through deterministic rule evaluation, clinician review, 4-digit PIN verification, cryptographic hashing, and clearinghouse transmission.

![3. Prior Authorization Adjudication Sequence](images/03_adjudication_sequence.png)

*Direct image files: [PNG](images/03_adjudication_sequence.png) | [SVG](images/03_adjudication_sequence.svg)*

```mermaid
sequenceDiagram
    autonumber
    actor Clinician as Attesting Clinician
    participant UI as CarePolicyGuard Frontend
    participant API as FastAPI Gateway
    participant NLP as Clinical NLP Engine
    participant Rules as CMS Policy Matcher
    participant DB as Relational Database
    participant Audit as Cryptographic Ledger Engine
    participant MAC as CMS Medicare MAC Gateway

    Clinician->>UI: Selects patient case or triggers CDS Hooks order-sign
    UI->>API: POST /api/v1/adjudicate (EHR notes, policy_id, patient_id)
    API->>DB: Query MedicarePolicy and criteria (eager selectin batch)
    DB-->>API: Policy criteria definitions
    API->>NLP: Extract clinical entities, biomarkers, and temporal spans
    NLP-->>API: Extracted structured clinical facts
    API->>Rules: Evaluate criteria (inclusions, exclusions, thresholds)
    Rules-->>API: Decision (APPROVED / DENIED / DEFERRED), confidence, and citations
    API-->>UI: Return adjudication recommendation with evidence highlights
    Clinician->>UI: Reviews clinical justification and clicks "Sign and Authorize"
    UI->>Clinician: Prompts 4-Digit Clinician Signing PIN modal
    Clinician->>UI: Enters 4-Digit Signing PIN
    UI->>API: POST /api/v1/adjudicate/sign (case_id, PIN, attestation)
    API->>Audit: Compute SHA-256 cryptographic hash and link previous block
    Audit->>DB: Store immutable AdjudicationLog entry
    API->>MAC: Transmit 278 Prior Authorization claim via PAS
    MAC-->>API: Return Payer Transaction ID (CMS-MAC-ACK)
    API->>DB: Update submission_status = SUBMITTED, payer_transaction_id
    API-->>UI: Return signed confirmation with verification seal
    UI-->>Clinician: Display transmission receipt and cryptographic hash
```

---

## 4. Sequence Diagram: Multi-Factor Authentication and Live Email OTP Delivery

This sequence illustrates the authentication flow, including live Google SMTP email dispatch for two-factor verification.

![4. MFA and Email OTP Delivery Sequence](images/04_mfa_email_otp_sequence.png)

*Direct image files: [PNG](images/04_mfa_email_otp_sequence.png) | [SVG](images/04_mfa_email_otp_sequence.svg)*

```mermaid
sequenceDiagram
    autonumber
    actor User as Healthcare User
    participant Browser as Browser Client
    participant AuthAPI as Auth Controller
    participant DB as User Database
    participant SMTP as Google SMTP Server
    participant Inbox as Clinician Email Inbox

    User->>Browser: Enters email and password
    Browser->>AuthAPI: POST /api/v1/auth/login
    AuthAPI->>DB: Fetch user record and verify Argon2 / PBKDF2 hash
    DB-->>AuthAPI: User record validated (MFA enabled: email_otp)
    AuthAPI->>AuthAPI: Generate cryptographically secure 6-digit OTP and 5-min expiry
    AuthAPI->>DB: Persist active_otp_code and otp_expires_at
    AuthAPI->>SMTP: Dispatch TLS MIME email with one-time verification passcode
    SMTP->>Inbox: Deliver CarePolicyGuard Security Passcode
    AuthAPI-->>Browser: HTTP 200 (require_otp: true, mfa_method: email_otp)
    Browser->>User: Display 6-digit OTP verification prompt
    User->>Inbox: Retrieves OTP code
    User->>Browser: Enters 6-digit code
    Browser->>AuthAPI: POST /api/v1/auth/verify-otp (email, otp_code)
    AuthAPI->>DB: Verify active_otp_code matches and now < otp_expires_at
    AuthAPI->>DB: Clear active_otp_code, generate UserSession
    AuthAPI-->>Browser: Issue secure session cookie / bearer token
    Browser->>User: Route to role-specific dashboard (Clinician / Auditor / Admin)
```

---

## 5. State Diagram: Adjudication Case Lifecycle and Audit Immutability

This state chart outlines the progression of an adjudication case from raw EHR clinical input to an immutable, cryptographically sealed record.

![5. Case Lifecycle State Machine](images/05_case_lifecycle_state_machine.png)

*Direct image files: [PNG](images/05_case_lifecycle_state_machine.png) | [SVG](images/05_case_lifecycle_state_machine.svg)*

```mermaid
stateDiagram-v2
    [*] --> Ingested: EHR Case Ingested via CDS Hooks or Manual Entry
    Ingested --> ExtractingEvidence: Trigger Clinical NLP
    ExtractingEvidence --> EvaluatingCriteria: Entities and Temporal Spans Extracted
    
    state EvaluatingCriteria {
        [*] --> CheckInclusions
        CheckInclusions --> CheckExclusions: Inclusions Satisfied
        CheckExclusions --> CalcConfidence: No Disqualifying Exclusions
    }

    EvaluatingCriteria --> Approved: All Criteria Met (Confidence >= Threshold)
    EvaluatingCriteria --> Denied: Unmet Criteria or Active Exclusion
    EvaluatingCriteria --> DeferredToHuman: Low Confidence or Ambiguous Evidence

    Approved --> PendingAttestation: Clinician Review Required
    Denied --> PendingAttestation: Clinician Review or Peer-to-Peer
    DeferredToHuman --> ManualCorrection: Clinician Overrides or Amends Notes
    ManualCorrection --> EvaluatingCriteria: Re-evaluate

    PendingAttestation --> AuthenticatingSigner: Clinician Clicks Authorize
    AuthenticatingSigner --> SignedAndSealed: Correct 4-Digit Signing PIN Entered
    AuthenticatingSigner --> PendingAttestation: Invalid PIN (Retry Allowed)

    SignedAndSealed --> TransmittedToClearinghouse: PAS 278 Claim Generated
    TransmittedToClearinghouse --> ArchivedInLedger: Payer Acknowledgment Received
    ArchivedInLedger --> [*]: Cryptographically Locked (SHA-256)
```

---

## 6. DaVinci FHIR Standards Interoperability Flow

CarePolicyGuard complies with HL7 DaVinci prior authorization implementation guides:

1. **CRD (Coverage Requirements Discovery)**: Informs clinicians of prior authorization requirements at the point of order sign.
2. **DTR (Documentation Templates and Rules)**: Pre-populates clinical documentation forms with EHR data.
3. **PAS (Prior Authorization Support)**: Submits 278 prior authorization requests and receives immediate clearinghouse adjudication responses.

![6. DaVinci FHIR Standards Interoperability Flow](images/06_davinci_fhir_interoperability.png)

*Direct image files: [PNG](images/06_davinci_fhir_interoperability.png) | [SVG](images/06_davinci_fhir_interoperability.svg)*

```mermaid
flowchart LR
    subgraph EHR ["EHR Environment"]
        EHRApp["EHR Ordering System"]
    end

    subgraph CarePolicyGuardEngine ["CarePolicyGuard Platform"]
        CRD["CDS Hooks Service (Coverage Requirements Discovery)"]
        DTR["DTR Service (Documentation Templates and Rules)"]
        PAS["PAS Service (Prior Authorization Support)"]
        AuditEngine["Cryptographic Ledger Engine"]
    end

    subgraph PayerClearinghouse ["Payer / CMS Clearinghouse"]
        CMSGateway["CMS Medicare Part B MAC Gateway"]
    end

    EHRApp -- "1. order-sign CDS Hook trigger" --> CRD
    CRD -- "2. Return CDS Card with policy requirements" --> EHRApp
    EHRApp -- "3. Fetch SMART on FHIR questionnaire" --> DTR
    DTR -- "4. Return prepopulated clinical questionnaire" --> EHRApp
    EHRApp -- "5. Submit completed FHIR Bundle" --> PAS
    PAS -- "6. Cryptographic attestation and verification" --> AuditEngine
    PAS -- "7. Forward X12 278 / FHIR Claim" --> CMSGateway
    CMSGateway -- "8. Return 278 ClaimResponse" --> PAS
    PAS -- "9. Update prior auth status" --> EHRApp
```
