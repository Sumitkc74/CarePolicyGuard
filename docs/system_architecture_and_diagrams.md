# CarePolicyGuard Architecture and Design Specification

This document provides visual architectural, relational, sequence, state, and interoperability diagrams for the **CarePolicyGuard** clinical adjudication and prior authorization attestation platform.

Standalone image files are saved directly in `docs/images/` as both **PNG** and **SVG** formats for use in presentations, reports, and documentation.

---

## 1. High-Level System Architecture

CarePolicyGuard is structured as a tiered, HIPAA-compliant prior authorization adjudication platform. It decouples interface concerns, API orchestration, deterministic clinical inference, cryptographic integrity auditing, and external healthcare integrations.

![1. High-Level System Architecture](images/01_system_architecture.png)

*Direct image files: [PNG](images/01_system_architecture.png) | [SVG](images/01_system_architecture.svg)*

```mermaid
flowchart LR
    %% -------------------------------------------------------------
    %% STYLES & THEMING FOR MAXIMUM READABILITY
    %% -------------------------------------------------------------
    classDef clientStyle fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC,font-size:14px,font-weight:bold;
    classDef gatewayStyle fill:#0F172A,stroke:#818CF8,stroke-width:2px,color:#F8FAFC,font-size:14px,font-weight:bold;
    classDef ragStyle fill:#2E1065,stroke:#E879F9,stroke-width:2px,color:#FDF4FF,font-size:14px,font-weight:bold;
    classDef agentStyle fill:#1E1B4B,stroke:#A855F7,stroke-width:2px,color:#F8FAFC,font-size:14px,font-weight:bold;
    classDef gateStyle fill:#312E81,stroke:#C084FC,stroke-width:3px,color:#FFFFFF,font-size:14px,font-weight:bold;
    classDef approveStyle fill:#064E3B,stroke:#10B981,stroke-width:2px,color:#ECFDF5,font-size:14px,font-weight:bold;
    classDef denyStyle fill:#7F1D1D,stroke:#F43F5E,stroke-width:2px,color:#FFF1F2,font-size:14px,font-weight:bold;
    classDef deferStyle fill:#78350F,stroke:#F59E0B,stroke-width:2px,color:#FEF3C7,font-size:14px,font-weight:bold;
    classDef dataStyle fill:#0F172A,stroke:#06B6D4,stroke-width:2px,color:#F8FAFC,font-size:14px,font-weight:bold;

    subgraph C1 ["1. CLINICAL CLIENTS"]
        Clinician["Clinician Workspace"]:::clientStyle
        Batch["Batch Roster Engine"]:::clientStyle
        Auditor["Auditor Portal"]:::clientStyle
    end

    subgraph C2 ["2. SECURE API GATEWAY"]
        API["FastAPI Gateway"]:::gatewayStyle
        Auth["Auth & MFA Guard"]:::gatewayStyle
        HIPAA["HIPAA PHI Masker"]:::gatewayStyle
    end

    subgraph C3 ["3. HYBRID RAG & MULTI-AGENT PIPELINE"]
        CMS_DB[("CMS Policy Rules<br/>(NCDs & LCDs)")]:::ragStyle
        RAG["1. Hybrid RAG Engine<br/>(Lexical-Semantic Search)"]:::ragStyle
        Agent2["2. Criteria Evaluator"]:::agentStyle
        Agent3["3. Adversarial Verifier"]:::agentStyle
        Gate{"4. Abstention Gate<br/>(tau >= 0.85)"}:::gateStyle
        Agent5["5. Defense Packet Generator"]:::agentStyle
    end

    subgraph C4 ["4. ADJUDICATION OUTCOMES"]
        Approved["APPROVED"]:::approveStyle
        Denied["DENIED"]:::denyStyle
        Deferred["DEFERRED TO MD"]:::deferStyle
    end

    subgraph C5 ["5. AUDIT & CLEARINGHOUSE"]
        DB[("Relational Database")]:::dataStyle
        Ledger["SHA-256 Audit Ledger"]:::dataStyle
        CMS["CMS MAC Clearinghouse"]:::dataStyle
    end

    C1 --> API
    API --> Auth
    Auth --> HIPAA
    HIPAA --> RAG

    CMS_DB --> RAG
    RAG --> Agent2
    Agent2 --> Agent3
    Agent3 --> Gate

    Gate -->|"Pass (>= 0.85)"| Approved
    Gate -->|"Exclusion Flag"| Denied
    Gate -->|"Low Conf (< 0.85)"| Deferred

    Approved --> Agent5
    Denied --> Agent5
    Deferred --> Agent5

    Agent5 --> DB
    Agent5 --> Ledger
    Agent5 --> CMS
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
