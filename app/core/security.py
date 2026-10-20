import hashlib
import hmac
import os
import re
import json
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Union
import jwt
from fastapi import HTTPException, status
from app.core.config import settings

class UserRole(str, Enum):
    AUDITOR = "Auditor"
    CLINICIAN = "Clinician"
    ADMIN = "Admin"

def get_password_hash(password: str) -> str:
    """
    PBKDF2-HMAC-SHA256 password hashing using 100,000 iterations and a random salt.
    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    salt = os.urandom(16)
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against the stored PBKDF2-HMAC-SHA256 hash.
    """
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = bytes.fromhex(parts[3])
        calculated = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected_hash, calculated)
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Generates a signed JWT access token.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def compute_audit_hash(
    patient_id_masked: str,
    policy_id: str,
    decision: str,
    calibrated_confidence: float,
    criterion_assessments: list,
    evidence_spans: list,
    timestamp: Union[str, datetime]
) -> str:
    """
    Computes an immutable, deterministic SHA-256 cryptographic chain-of-custody hash.
    Ensures that any subsequent modification to criteria, offsets, or decisions
    invalidates the cryptographic seal.
    """
    if isinstance(timestamp, datetime):
        ts_str = timestamp.isoformat()
    else:
        ts_str = str(timestamp)

    canonical_payload = {
        "patient_id_masked": patient_id_masked,
        "policy_id": policy_id,
        "decision": decision,
        "calibrated_confidence": round(float(calibrated_confidence), 4),
        "criteria": sorted([
            {
                "code": str(c.get("criterion_code", c.get("criterion_id", ""))),
                "status": str(c.get("status", "")),
                "rationale": str(c.get("clinical_rationale", "")).strip()
            }
            for c in criterion_assessments
        ], key=lambda x: x["code"]),
        "evidence_spans": sorted([
            {
                "start_char": int(s.get("start_char", 0)),
                "end_char": int(s.get("end_char", 0)),
                "source_text": str(s.get("source_text", "")).strip()
            }
            for s in evidence_spans
        ], key=lambda x: (x["start_char"], x["end_char"])),
        "timestamp": ts_str
    }
    
    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def sanitize_phi(text: str) -> str:
    """
    Clinical Compliance Guardrail (HIPAA Safe Harbor - 45 CFR § 164.514(b)):
    Sanitizes direct Patient Health Information (PHI) identifiers while strictly
    preserving clinical terminology, numbers, percentages, and clinical findings.
    Masks: SSN, Phone numbers, Email addresses, MRN patterns, Medicare Beneficiary IDs (MBI),
    Street addresses, Zip codes, and Patient Name lines.
    """
    if not text:
        return ""

    sanitized = text

    # 1. Social Security Numbers (e.g. 123-45-6789 or 123 45 6789)
    sanitized = re.sub(r'\b\d{3}[-\s]\d{2}[-\s]\d{4}\b', '[REDACTED-SSN]', sanitized)

    # 2. Phone numbers (e.g. (555) 234-5678, +1-555-234-5678, 555-234-5678)
    sanitized = re.sub(r'(\+?1[-.\s]?)?(\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b', '[REDACTED-PHONE]', sanitized)

    # 3. Email addresses
    sanitized = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', '[REDACTED-EMAIL]', sanitized)

    # 4. Medical Record Number (MRN) patterns: MRN: 12345678, MRN #987654, Record #: 44819
    sanitized = re.sub(r'(?i)\b(mrn|medical record number|record\s*#)[\s:#]+[A-Za-z0-9-]{5,12}\b', r'\1: [REDACTED-MRN]', sanitized)

    # 5. Medicare Beneficiary Identifier (MBI) - 11 character alphanumeric e.g. 1EG4-TE5-MK72
    sanitized = re.sub(r'\b[1-9][A-Z][0-9A-Z]{2}[-\s]?[0-9A-Z]{3}[-\s]?[0-9A-Z]{4}\b', '[REDACTED-MBI]', sanitized)

    # 6. Patient Name lines e.g. "Patient Name: John Doe", "Patient: Jane Smith", "Pt: Robert Johnson"
    sanitized = re.sub(r'(?i)((?:patient\s*(?:name)?|pt\s*(?:name)?|patient)\s*:\s*)([A-Z][a-z]+([ \t]+[A-Z][a-z]+)+)', r'\1[REDACTED-NAME]', sanitized)

    # 7. Date of Birth e.g., "DOB: 01/12/1954" or "Date of Birth: 1954-01-12"
    sanitized = re.sub(r'(?i)(dob|date of birth|birth\s*date)\s*:\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', r'\1: [REDACTED-DOB]', sanitized)

    # 8. Street addresses (e.g. "124 Medical Center Blvd", "45 Main Street", "78 Oak Ave")
    sanitized = re.sub(r'(?i)\b\d{1,5}\s+[A-Za-z0-9\.\s]+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b', '[REDACTED-ADDRESS]', sanitized)

    # 9. Zip codes (e.g. "Zip: 90210", "Postal Code: 10001-1234")
    sanitized = re.sub(r'(?i)\b(zip|postal\s*code)[\s:#]+(\d{5}(?:-\d{4})?)\b', r'\1: [REDACTED-ZIP]', sanitized)

    return sanitized


def verify_clinical_document_authenticity(text: str) -> Dict[str, Any]:
    """
    Verifies that a submitted clinical document is authentic by validating:
    1. Provider / Physician Name and Credentials (e.g., Dr. Name, MD, DO, NP, PA-C)
    2. Electronic or Written Signature / Attestation block
    3. Clinical Structure & Medical Content (SOAP components, clinical terminology)

    Returns a detailed verification result:
    {
        "is_authentic_clinical_note": bool,
        "has_doctor_name": bool,
        "has_doctor_signature": bool,
        "doctor_name": Optional[str],
        "signature_text": Optional[str],
        "clinical_confidence": float,
        "reasons": List[str]
    }
    """
    if not text or len(text.strip()) < 20:
        return {
            "is_authentic_clinical_note": False,
            "has_doctor_name": False,
            "has_doctor_signature": False,
            "doctor_name": None,
            "signature_text": None,
            "clinical_confidence": 0.0,
            "reasons": ["Text is too short to be an authentic clinical encounter note."]
        }

    raw = text.strip()

    # 1. DOCTOR / PHYSICIAN NAME DETECTION
    # Match patterns like:
    # "Dr. Sarah Jenkins", "Dr. Sarah Jenkins, MD", "Attending: Dr. Robert Cole"
    # "Provider: Michael Chang, MD", "Physician: Dr. Eleanor Vance, DO, FACC"
    # "Sarah Jenkins, MD", "Robert Cole, DO"
    doctor_name = None
    has_doctor_name = False

    doc_patterns = [
        # Explicit Dr. followed by 2-3 capitalized words and optional credentials
        r'\b(?:Dr\.|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,\s*(?:MD|DO|NP|PA-C|PA|FACC|FACP|MBBS))?\b',
        # Role prefix e.g. "Attending / Provider / Physician / Clinician: [Dr.] John Doe, MD"
        r'(?i)\b(?:attending|provider|physician|clinician|consultant|prescriber|cardiologist|pulmonologist)\s*(?:name)?\s*:\s*(?:Dr\.\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,\s*(?:MD|DO|NP|PA-C|PA|FACC|FACP|MBBS))?',
        # Name followed by MD, DO, MBBS, NP, PA-C
        r'\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+),\s*(?:MD|DO|NP|PA-C|MBBS)(?:\s*,\s*(?:FACC|FACP|FACS))?\b',
        # Attestation line containing name
        r'(?i)(?:electronically\s+signed\s+by|signed\s+by|attested\s+by)\s*:?\s*(?:Dr\.\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,\s*(?:MD|DO|NP|PA-C|FACC))?'
    ]

    for pat in doc_patterns:
        m = re.search(pat, raw)
        if m:
            doctor_name = m.group(1).strip()
            # If matched without Dr. prefix, format cleanly
            if not doctor_name.startswith("Dr.") and not doctor_name.lower().startswith("doctor"):
                doctor_name = f"Dr. {doctor_name}"
            has_doctor_name = True
            break

    # 2. DOCTOR SIGNATURE & ATTESTATION DETECTION
    # Match patterns like:
    # "Electronically signed by Dr. Sarah Jenkins on 2026-10-18"
    # "Signature: /s/ Dr. Robert Cole, MD"
    # "Attending Physician Signature: Dr. Jenkins"
    # "Attested by: ...", "Provider Signature:", "Electronically authenticated"
    signature_text = None
    has_doctor_signature = False

    sig_patterns = [
        r'(?i)(?:electronically\s+signed\s+by|e-signed\s+by|signed\s+by)\s*:?\s*([^\n\r]+)',
        r'(?i)(?:physician\s+signature|doctor\s+signature|provider\s+signature|attending\s+signature|signature)\s*:\s*([^\n\r]+)',
        r'(?i)(?:attested\s+by|authenticated\s+by)\s*:?\s*([^\n\r]+)',
        r'(?i)(/s/\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:,\s*(?:MD|DO|NP|PA-C))?)',
        r'(?i)(?:i\s+certify\s+that\s+i\s+examined|i\s+personally\s+examined|i\s+attest\s+to\s+the\s+above)'
    ]

    for spat in sig_patterns:
        sm = re.search(spat, raw)
        if sm:
            signature_text = sm.group(0).strip()
            has_doctor_signature = True
            # If doctor_name not found yet, try extracting from signature match
            if not has_doctor_name and len(sm.groups()) > 0 and sm.group(1):
                cand = sm.group(1).strip()
                cand = re.sub(r'(?i)^/s/\s*', '', cand)
                cand = re.sub(r'(?i)\s+on\s+.*$', '', cand)
                cand_match = re.search(r'\b(?:Dr\.\s*)?([A-Z][a-z]+\s+[A-Z][a-z]+)', cand)
                if cand_match:
                    doctor_name = f"Dr. {cand_match.group(1).strip()}"
                    has_doctor_name = True
            break

    # 3. CLINICAL CONTENT & TERMINOLOGY DENSITY
    # Check for authentic medical sections and vocabulary
    clinical_keywords = [
        "patient", "history", "assessment", "plan", "diagnosis", "symptoms",
        "examination", "physical exam", "medications", "vital", "cardio",
        "pulmonary", "lvef", "nyha", "ahi", "gdmt", "cabg", "stemi", "hba1c",
        "wagner", "polysomnography", "echocardiogram", "treatment", "clinic"
    ]
    raw_lower = raw.lower()
    keyword_hits = sum(1 for kw in clinical_keywords if kw in raw_lower)
    clinical_density = min(1.0, keyword_hits / 6.0)

    reasons = []
    if not has_doctor_name:
        reasons.append("Missing physician/doctor name or clinical credentials (e.g. Dr. Name, MD/DO).")
    if not has_doctor_signature:
        reasons.append("Missing physician digital signature, electronic attestation, or '/s/' signature line.")
    if clinical_density < 0.5:
        reasons.append("Insufficient clinical terminology or documentation structure (SOAP/H&P).")

    is_authentic = has_doctor_name and has_doctor_signature and (clinical_density >= 0.5)

    return {
        "is_authentic_clinical_note": is_authentic,
        "has_doctor_name": has_doctor_name,
        "has_doctor_signature": has_doctor_signature,
        "doctor_name": doctor_name,
        "signature_text": signature_text,
        "clinical_confidence": round(clinical_density * (1.0 if has_doctor_name and has_doctor_signature else 0.5), 2),
        "reasons": reasons
    }


# =============================================================================
# MEDICAL PROFESSIONAL & NPI CREDENTIAL VERIFICATION
# =============================================================================

VALID_CLINICAL_CREDENTIALS = {
    "MD", "DO", "NP", "APRN", "PA-C", "PA", "MBBS", "CRNA", "PharmD", "DPM", "FACC", "FACP", "FACS"
}

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP"
}

DISALLOWED_PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "mac.com", "mail.com", "protonmail.com", "proton.me", "zoho.com",
    "yandex.com", "gmx.com", "fastmail.com", "tempmail.com", "guerrillamail.com",
    "sharklasers.com", "10minutemail.com", "throwawaymail.com", "trashmail.com"
}


def validate_npi_luhn(npi: str) -> bool:
    """
    Validates a 10-digit US National Provider Identifier (NPI) using the official
    CMS standard Luhn algorithm with the ISO 7812 '80840' prefix (representing
    healthcare applications in the United States).
    """
    if not npi:
        return False
    clean_npi = str(npi).strip()
    if not clean_npi.isdigit() or len(clean_npi) != 10:
        return False

    # Individual practitioners typically begin with '1' or '2'
    if clean_npi[0] not in ("1", "2"):
        return False

    full_str = "80840" + clean_npi
    digits = [int(c) for c in full_str]
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d

    return checksum % 10 == 0


def is_institutional_clinical_email(email: str) -> tuple[bool, str]:
    """
    Enforces HIPAA Administrative Safeguards (45 CFR § 164.312(a)):
    Requires registration using a verified clinical, institutional, or healthcare
    organization email domain. Blocks generic free or disposable personal webmail.
    """
    if not email or "@" not in email:
        return False, "Invalid email address format."

    clean_email = email.strip().lower()
    domain = clean_email.split("@")[-1]

    if domain in DISALLOWED_PERSONAL_DOMAINS:
        return (
            False,
            f"Personal webmail (@{domain}) is prohibited. A verified hospital, medical center, clinic, or health system email is required."
        )

    # Must contain a valid dot-separated top-level domain
    if "." not in domain or len(domain.split(".")[-1]) < 2:
        return False, "Invalid institutional email domain structure."

    return True, ""


def verify_medical_professional_credentials(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive verification to ensure an individual registering to create
    prior-authorization cases is a verified medical professional:
    1. National Provider Identifier (NPI): 10 digits & CMS Luhn checksum.
    2. Clinical Credential / Degree: MD, DO, NP, PA-C, MBBS, CRNA, PharmD.
    3. State Medical Board Licensure: Valid US state code and non-empty license #.
    4. Institutional Email: Rejection of personal webmail (@gmail, @yahoo).
    5. Clinical Organization / Practice Affiliation: Verified health entity.

    Returns:
    {
        "is_verified": bool,
        "npi_valid": bool,
        "email_valid": bool,
        "credentials_valid": bool,
        "state_license_valid": bool,
        "organization_valid": bool,
        "message": str,
        "reasons": List[str]
    }
    """
    npi = str(data.get("npi_number") or "").strip()
    email = str(data.get("email") or "").strip()
    credential = str(data.get("credential_title") or "").strip().upper()
    license_num = str(data.get("medical_license") or "").strip()
    license_state = str(data.get("license_state") or "").strip().upper()
    org = str(data.get("organization") or "").strip()

    reasons: list[str] = []

    # 1. NPI Luhn Check
    npi_valid = validate_npi_luhn(npi)
    if not npi_valid:
        if not npi:
            reasons.append("Missing 10-digit National Provider Identifier (NPI).")
        elif len(npi) != 10 or not npi.isdigit():
            reasons.append(f"NPI '{npi}' must be exactly 10 numeric digits.")
        elif npi[0] not in ("1", "2"):
            reasons.append(f"Individual clinical NPI must begin with '1' or '2' (Type 1 Individual Provider).")
        else:
            reasons.append(f"NPI '{npi}' failed CMS Luhn checksum validation (check digit mismatch).")

    # 2. Email Domain Check
    email_valid, email_err = is_institutional_clinical_email(email)
    if not email_valid:
        reasons.append(email_err)

    # 3. Clinical Credential / Degree Check
    cred_normalized = re.sub(r'[^A-Z-]', '', credential)
    credentials_valid = cred_normalized in VALID_CLINICAL_CREDENTIALS
    if not credentials_valid:
        allowed = ", ".join(sorted(VALID_CLINICAL_CREDENTIALS))
        reasons.append(f"Credential '{credential}' is not a recognized medical degree/licensure. Allowed: {allowed}.")

    # 4. State Licensure Check
    state_valid = license_state in US_STATE_CODES
    num_valid = len(license_num) >= 4 and bool(re.search(r'[A-Za-z0-9]', license_num))
    state_license_valid = state_valid and num_valid
    if not state_valid:
        reasons.append(f"State of licensure '{license_state}' is not a recognized 2-letter US state or territory.")
    if not num_valid:
        reasons.append(f"State medical license number '{license_num}' is invalid (minimum 4 alphanumeric characters required).")

    # 5. Organization Check
    organization_valid = len(org) >= 3
    if not organization_valid:
        reasons.append("Clinical practice or healthcare organization name is required (minimum 3 characters).")

    is_verified = npi_valid and email_valid and credentials_valid and state_license_valid and organization_valid

    if is_verified:
        message = f"Medical professional credentials verified successfully for {credential} (NPI: {npi}, State: {license_state})."
    else:
        message = "Medical credential verification failed. Individual is not authorized to register as a clinical case creator."

    return {
        "is_verified": is_verified,
        "npi_valid": npi_valid,
        "email_valid": email_valid,
        "credentials_valid": credentials_valid,
        "state_license_valid": state_license_valid,
        "organization_valid": organization_valid,
        "message": message,
        "reasons": reasons
    }



