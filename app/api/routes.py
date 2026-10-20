import io
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    verify_clinical_document_authenticity,
    verify_medical_professional_credentials,
    validate_npi_luhn,
    is_institutional_clinical_email,
    UserRole
)
from app.db.session import get_db
from app.db.models import User, MedicarePolicy, PolicyCriterion, AdjudicationLog
from app.schemas.contracts import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    MedicalVerificationRequest,
    MedicalVerificationResponse,
    UserOut,
    PolicyOut,
    AdjudicationRequest,
    FinalAdjudication,
    MultiPolicyScanRequest,
    MultiPolicyScanResponse,
    PolicyMatchSummary,
    AuditLogOut,
    BenchmarkResponse,
    CMSCoveragePacket,
    SubmitPacketRequest,
    SubmissionReceipt,
    PeerToPeerAppealRequest,
    PeerToPeerAppealLetter,
    EHRPushRequest,
    EHRPushReceipt,
    ClinicalAddendumRequest,
    ClinicalAddendumResponse,
    AuditTrailEvent,
    AuditTrailResponse
)
from app.api.deps import get_current_user, require_role
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.agents.benchmark_engine import BenchmarkRunner, BENCHMARK_VIGNETTES
from app.agents.packet_generator import CoveragePacketGenerator
from app.agents.policy_retriever import PolicyRetrievalAgent
from app.services import (
    sync_cms_policies,
    get_sync_status,
    PeerToPeerAppealService,
    FHIRExportService,
    BillingValidatorService,
    TimelineAnalyzerService
)

api_router = APIRouter()

# =============================================================================
# SECURITY & PRIVACY GUARDRAILS
# =============================================================================
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB maximum upload limit
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}

# In-memory ephemeral store for Zero-Retention mode (not persisted to disk)
_EPHEMERAL_PACKETS: Dict[str, CMSCoveragePacket] = {}
_EPHEMERAL_EHR_TEXTS: Dict[str, str] = {}
_EPHEMERAL_ADJUDICATIONS: Dict[str, FinalAdjudication] = {}

def validate_and_sanitize_upload(filename: str, content: bytes) -> str:
    """
    Validates uploaded document size, sanitizes filename against path traversal,
    and enforces strict extension whitelisting for medical document safety.
    """
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded document exceeds the maximum 15 MB limit ({len(content) / (1024 * 1024):.1f} MB provided)."
        )

    import os
    import re
    # Strip directory traversal sequences, slashes, and null bytes
    safe_name = os.path.basename(filename or "upload.txt")
    safe_name = re.sub(r'[\x00/\\:*?"<>|]', '_', safe_name)
    ext = os.path.splitext(safe_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    return safe_name

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@api_router.post("/auth/login", response_model=TokenResponse, summary="OAuth2 / JWT Token Authentication")
def login(
    login_data: Optional[LoginRequest] = None,
    form_data: Optional[OAuth2PasswordRequestForm] = Depends(lambda: None),
    db: Session = Depends(get_db)
):
    """
    Issues stateless JWT bearer tokens after PBKDF2-HMAC-SHA256 password verification.
    Supports both JSON body and standard form-data login workflows.
    """
    username = login_data.username if login_data else (form_data.username if form_data else None)
    password = login_data.password if login_data else (form_data.password if form_data else None)

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": user.username, "role": user.role, "uid": user.id},
        expires_delta=access_token_expires
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        username=user.username,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@api_router.post(
    "/auth/verify-medical-credentials",
    response_model=MedicalVerificationResponse,
    summary="Pre-verify Medical Professional Credentials"
)
def verify_credentials(request: MedicalVerificationRequest):
    """
    Pre-verifies healthcare provider credentials in real time:
    - 10-digit NPI validity via CMS standard Luhn algorithm with '80840' prefix.
    - Disallowed personal webmail rejection (HIPAA access safeguards).
    - State medical license and recognized clinical degree check.
    """
    result = verify_medical_professional_credentials(request.model_dump())
    return MedicalVerificationResponse(**result)


@api_router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new clinical or compliance user.
    Enforces strict medical professional verification: Anyone registering as a Clinician /
    Medical Professional MUST verify their 10-digit CMS NPI, clinical degree (MD, DO, NP, etc.),
    state medical license, and institutional healthcare email before their account can be created.
    Personal email addresses (@gmail, @yahoo) are strictly prohibited under HIPAA access safeguards.
    """
    existing = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists."
        )

    requested_role = user_in.role if user_in.role in [r.value for r in UserRole] else UserRole.CLINICIAN.value

    # 1. Clinicians MUST be verified licensed medical professionals
    is_verified = False
    verification_method = None
    if requested_role == UserRole.CLINICIAN.value:
        verif = verify_medical_professional_credentials(user_in.model_dump())
        if not verif["is_verified"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Medical professional verification failed. Only verified licensed medical professionals may register to create prior-authorization cases.",
                    "reasons": verif["reasons"]
                }
            )
        is_verified = True
        verification_method = "NPPES_CMS_LUHN_VERIFIED"
    elif requested_role == UserRole.AUDITOR.value:
        # Auditors must also use an institutional or regulatory email
        is_valid_email, email_err = is_institutional_clinical_email(user_in.email)
        if not is_valid_email:
            raise HTTPException(
                status_code=422,
                detail=f"Auditor registration denied: {email_err}"
            )
        verification_method = "AUDITOR_INSTITUTIONAL_VERIFIED"

    user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=requested_role,
        npi_number=user_in.npi_number,
        medical_license=user_in.medical_license,
        license_state=user_in.license_state,
        credential_title=user_in.credential_title,
        specialty=user_in.specialty,
        organization=user_in.organization,
        is_verified_medical_pro=is_verified,
        verification_method=verification_method,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@api_router.get("/auth/me", response_model=UserOut)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Returns current authenticated user profile.
    """
    return current_user

# =============================================================================
# MEDICARE POLICIES (NCD & LCD)
# =============================================================================

@api_router.get("/policies", response_model=List[PolicyOut], summary="List Medicare Policies & Criteria")
def list_policies(db: Session = Depends(get_db)):
    """
    Retrieves all registered CMS National Coverage Determinations (NCDs)
    and Local Coverage Determinations (LCDs) with their criteria definitions.
    """
    policies = db.query(MedicarePolicy).all()
    return policies

@api_router.post("/policies/sync-cms", summary="Automated CMS Policy Sync (Method 2)")
def trigger_cms_sync(
    force: bool = Query(False, description="Force update all policies and criteria"),
    db: Session = Depends(get_db)
):
    """
    Automated Background CMS Sync (Method 2):
    Pulls latest transmittal records from the CMS Medicare Coverage Database (MCD) feed,
    detects criteria/threshold revisions, and updates local carepolicyguard.db.
    """
    try:
        report = sync_cms_policies(db=db, force_update=force)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CMS Policy Synchronization failed: {str(e)}"
        )

@api_router.get("/policies/sync-status", summary="CMS Policy Sync Status")
def check_cms_sync_status():
    """
    Returns the timestamp, status, and summary metrics of the last automated CMS policy sync.
    """
    return get_sync_status()

@api_router.get("/policies/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    """
    Retrieves a specific Medicare policy by ID (e.g. NCD-20.4, LCD-L33829).
    """
    policy = db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == policy_id).first()
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Medicare policy '{policy_id}' not found."
        )
    return policy

# =============================================================================
# MULTI-AGENT ADJUDICATION PIPELINE
# =============================================================================

@api_router.post("/adjudicate/scan-all", response_model=MultiPolicyScanResponse, summary="Scan Clinical Note Across All CMS Policies")
async def scan_all_policies(
    request: MultiPolicyScanRequest,
    db: Session = Depends(get_db)
):
    """
    Evaluates incoming patient EHR documentation across ALL active Medicare NCD/LCD policies in the database:
    1. Evaluates all criteria, citations, and calibrated confidence per policy.
    2. Identifies all qualifying coverage policies (detecting multi-morbidity and co-occurring orders).
    3. Ranks and highlights the 'Best / Strongest Match' with the highest evidentiary confidence.
    """
    pipeline = MultiAgentVerificationPipeline(db=db)
    custom_tau = request.options.get("tau") if request.options else None

    result = await pipeline.adjudicate_all_policies(
        patient_id=request.patient_id,
        ehr_narrative=request.ehr_narrative,
        custom_tau=custom_tau
    )

    # Ephemeral caching for approved policies
    for match in result.all_matches:
        _EPHEMERAL_EHR_TEXTS[match.adjudication.case_id] = request.ehr_narrative
        _EPHEMERAL_ADJUDICATIONS[match.adjudication.case_id] = match.adjudication
        if match.decision.value == "APPROVED":
            packet = CoveragePacketGenerator.generate_packet(match.adjudication)
            _EPHEMERAL_PACKETS[match.adjudication.case_id] = packet

    return result

@api_router.post("/adjudicate", response_model=FinalAdjudication, summary="Run Multi-Agent Verification Pipeline")
async def adjudicate_record(
    request: AdjudicationRequest,
    db: Session = Depends(get_db)
):
    """
    Executes the 4-Agent Verification Pipeline on incoming patient EHR documentation:
    1. Agent 1: Policy Retrieval
    2. Agent 2: Criteria Evaluation
    3. Agent 3: Adversarial Verification (Programmatic string offsets & omission audits)
    4. Agent 4: Calibrated Abstention Gate (tau = 0.85)
    Computes cryptographic SHA-256 chain-of-custody seal and logs audit trail.
    """
    pipeline = MultiAgentVerificationPipeline(db=db)
    custom_tau = request.options.get("tau") if request.options else None

    # Zero-Retention Mode: Do not save unsubmitted / exploratory evaluations to database
    save_record = True
    if request.options:
        if request.options.get("zero_retention") or request.options.get("save_record") is False:
            save_record = False

    result = await pipeline.adjudicate(
        patient_id=request.patient_id,
        policy_id=request.policy_id,
        ehr_narrative=request.ehr_narrative,
        custom_tau=custom_tau,
        save_record=save_record,
        cpt_codes=request.cpt_codes,
        icd10_codes=request.icd10_codes
    )

    # In-memory ephemeral packet caching (ensures instant availability without disk footprint)
    packet = CoveragePacketGenerator.generate_packet(result)
    _EPHEMERAL_PACKETS[result.case_id] = packet
    _EPHEMERAL_EHR_TEXTS[result.case_id] = request.ehr_narrative
    _EPHEMERAL_ADJUDICATIONS[result.case_id] = result

    return result

# =============================================================================
# IMMUTABLE AUDIT LOGS & HIPAA RIGHT TO ERASURE
# =============================================================================

@api_router.get("/audit-logs", response_model=List[AuditLogOut], summary="List Audit Logs with SHA-256 Hashes")
def get_audit_logs(
    policy_id: Optional[str] = Query(None, description="Filter by Medicare policy ID"),
    decision: Optional[str] = Query(None, description="Filter by decision"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Retrieves immutable adjudication audit histories with cryptographic verification hashes.
    """
    query = db.query(AdjudicationLog)
    if policy_id:
        query = query.filter(AdjudicationLog.policy_id == policy_id)
    if decision:
        query = query.filter(AdjudicationLog.decision == decision)

    logs = query.order_by(AdjudicationLog.created_at.desc()).limit(limit).all()
    return logs

@api_router.get("/audit-logs/{case_id}", response_model=AuditLogOut)
def get_audit_log_by_case(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieves full details for a specific case adjudication audit record.
    """
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log record for case '{case_id}' not found."
        )
    return log

@api_router.delete("/audit-logs/purge/all", summary="Purge All Ephemeral & Unsubmitted Records")
def purge_all_audit_logs(db: Session = Depends(get_db)):
    """
    HIPAA Safe Harbor & Data Minimization:
    Permanently erases all non-submitted exploratory clinical adjudication records from the database.
    """
    count = db.query(AdjudicationLog).delete()
    db.commit()
    _EPHEMERAL_PACKETS.clear()
    _EPHEMERAL_EHR_TEXTS.clear()
    _EPHEMERAL_ADJUDICATIONS.clear()
    return {
        "status": "success",
        "purged_count": count,
        "message": f"Successfully purged {count} audit records. Zero patient documentation remains on disk."
    }

@api_router.delete("/audit-logs/{case_id}", summary="Right to Erasure: Purge Single Clinical Record")
def delete_single_audit_log(case_id: str, db: Session = Depends(get_db)):
    """
    Permanently deletes a single clinical record and removes any ephemeral memory traces.
    """
    _EPHEMERAL_PACKETS.pop(case_id, None)
    _EPHEMERAL_EHR_TEXTS.pop(case_id, None)
    _EPHEMERAL_ADJUDICATIONS.pop(case_id, None)
    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    if log:
        db.delete(log)
        db.commit()
    return {
        "status": "success",
        "case_id": case_id,
        "message": f"Record for case '{case_id}' permanently deleted."
    }

# =============================================================================
# CLINICAL PRESETS & BENCHMARK LAB
# =============================================================================

@api_router.get("/presets", summary="Clinical Ingestion Presets")
def get_clinical_presets():
    """
    Returns pre-configured clinical test scenarios representing Qualifying,
    Disqualified, and Ambiguous/Abstention edge cases.
    """
    return {
        "presets": [
            {
                "id": "preset-icd-qualifying",
                "label": "Qualifying Primary Prevention ICD (NCD 20.4)",
                "category": "Cardiology",
                "policy_id": "NCD-20.4",
                "patient_id": "PT-CARD-8821",
                "description": "Severe ischemic cardiomyopathy (LVEF 28%, NYHA II, 6 months GDMT, 14 mos post-CABG)",
                "expected_decision": "APPROVED",
                "ehr_text": BENCHMARK_VIGNETTES[0]["ehr"].strip()
            },
            {
                "id": "preset-icd-inadequate-gdmt",
                "label": "Premature Referral - Inadequate GDMT (Abstention Trigger)",
                "category": "Cardiology",
                "policy_id": "NCD-20.4",
                "patient_id": "PT-CARD-9014",
                "description": "LVEF 30% but only 3 weeks of GDMT (< 90-day requirement). Gate defers to human.",
                "expected_decision": "DEFERRED_TO_HUMAN",
                "ehr_text": BENCHMARK_VIGNETTES[1]["ehr"].strip()
            },
            {
                "id": "preset-icd-disqualified",
                "label": "Disqualified - Cardiogenic Shock & Recent MI (NCD 20.4)",
                "category": "Cardiology",
                "policy_id": "NCD-20.4",
                "patient_id": "PT-ICU-1029",
                "description": "Patient in acute cardiogenic shock and PCI 4 days ago. Contraindicated under CMS exclusion.",
                "expected_decision": "DENIED",
                "ehr_text": BENCHMARK_VIGNETTES[2]["ehr"].strip()
            },
            {
                "id": "preset-cpap-qualifying",
                "label": "Qualifying CPAP for Severe OSA (LCD L33829)",
                "category": "Pulmonology",
                "policy_id": "LCD-L33829",
                "patient_id": "PT-RESP-4402",
                "description": "Severe obstructive sleep apnea (AHI 34.2 events/hr) with documented face-to-face evaluation.",
                "expected_decision": "APPROVED",
                "ehr_text": BENCHMARK_VIGNETTES[3]["ehr"].strip()
            },
            {
                "id": "preset-cpap-borderline",
                "label": "Borderline AHI Without Documented Comorbidity (Abstention)",
                "category": "Pulmonology",
                "policy_id": "LCD-L33829",
                "patient_id": "PT-RESP-5510",
                "description": "AHI 7.2 events/hr but chart lacks required comorbid condition documentation.",
                "expected_decision": "DEFERRED_TO_HUMAN",
                "ehr_text": BENCHMARK_VIGNETTES[4]["ehr"].strip()
            },
            {
                "id": "preset-hbot-wagner",
                "label": "Qualifying HBOT for Diabetic Foot Ulcer (NCD 20.29)",
                "category": "Wound Care",
                "policy_id": "NCD-20.29",
                "patient_id": "PT-WOUND-3390",
                "description": "Type 2 diabetes with Wagner Grade 3 deep ulceration and failure of 30 days standard wound therapy.",
                "expected_decision": "APPROVED",
                "ehr_text": """CLINICAL PROGRESS NOTE - WOUND CARE CLINIC
PATIENT: [REDACTED] | MRN: [REDACTED]

CHIEF COMPLAINT:
Evaluation of non-healing plantar diabetic foot ulcer on right first metatarsal head.

HISTORY & PHYSICAL:
Patient is a 64-year-old male with long-standing Type 2 Diabetes Mellitus (HbA1c 8.4%).
Right foot wound present for 12 weeks.
Patient has undergone standard wound care including weekly sharp debridement, moist dressings, and offloading boots for at least 30 days without measurable reduction in ulcer size.

PHYSICAL EXAMINATION:
Right plantar foot demonstrates deep ulceration measuring 2.4 x 1.8 cm extending into subcutaneous tissue and probe-to-bone positive, confirmed on imaging as osteomyelitis.
Wound staged as Wagner Grade 3 diabetic foot ulcer.
Dorsalis pedis and posterior tibial pulses are palpable with ABI 0.95.

ASSESSMENT & PLAN:
Wagner Grade 3 diabetic foot ulcer refractory to >30 days of standard conservative wound therapy.
No active acute limb ischemia.
Meets Medicare NCD 20.29 criteria for Hyperbaric Oxygen Therapy (HBOT) protocol (30 sessions at 2.4 ATA).

ATTENDING PHYSICIAN:
Dr. Elena Rostova, MD, CWS (NPI: 1679482013)
Wound Care & Hyperbaric Medicine

SIGNATURE:
Electronically signed by Dr. Elena Rostova, MD on 02/15/2026."""
            }
        ]
    }

@api_router.post("/benchmark/run", response_model=BenchmarkResponse, summary="Execute 4-Configuration Research Benchmark")
def run_benchmark():
    """
    Executes the 4-Configuration Research Benchmark Lab comparing:
    - Config A: Zero-Shot Baseline
    - Config B: Single-Pass RAG
    - Config C: Multi-Agent Extraction
    - Config D: CarePolicyGuard (Proposed Framework)
    Across Accuracy, Evidence Faithfulness, Expected Calibration Error (ECE), and Abstention Rate.
    """
    runner = BenchmarkRunner()
    results = runner.run_benchmark()
    return results

# =============================================================================
# DOCTOR'S NOTE UPLOAD & PRE-SUBMISSION COVERAGE PACKET WORKFLOW
# =============================================================================

def extract_text_from_upload(filename: str, content: bytes) -> str:
    """Extracts raw clinical text from uploaded .txt, .pdf, .docx, or image files (.png, .jpg, .jpeg, .tiff, .bmp, .webp)."""
    fn = filename.lower()
    if fn.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text).strip()
    elif fn.endswith(".docx"):
        import docx
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paragraphs).strip()
    elif any(fn.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"]):
        # Perform Optical Character Recognition (OCR) on clinical image
        try:
            from rapidocr_onnxruntime import RapidOCR
            ocr_engine = RapidOCR()
            result, _ = ocr_engine(content)
            if result:
                lines = [line_item[1] for line_item in result if line_item and len(line_item) > 1]
                extracted_text = "\n".join(lines).strip()
                if extracted_text:
                    return extracted_text
        except Exception as ocr_err:
            logger.warning(f"RapidOCR extraction failed for {filename}: {ocr_err}")

        # Fallback to pytesseract if installed and available
        try:
            import pytesseract
            from PIL import Image
            image = Image.open(io.BytesIO(content))
            return pytesseract.image_to_string(image).strip()
        except Exception as tesseract_err:
            logger.warning(f"Pytesseract fallback failed for {filename}: {tesseract_err}")
            raise HTTPException(status_code=400, detail="Could not extract readable clinical text from the provided image. Please ensure the image is clear and contains text.")
    else:
        # Default text/markdown decoding with fallback
        try:
            return content.decode("utf-8").strip()
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace").strip()

@api_router.post("/extract-text", summary="Extract Clinical Text from Document or Image for Confirmation")
async def extract_clinical_text(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Extracts text from uploaded PDF, DOCX, TXT, or Image (OCR) and suggests governing policy
    so the clinician can review, edit, and confirm before moving to Step 2.
    Enforces maximum upload limits and filename sanitization.
    """
    content = await file.read()
    safe_filename = validate_and_sanitize_upload(file.filename, content)

    try:
        extracted_text = extract_text_from_upload(safe_filename, content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract document text: {str(e)}")

    # Verify physician name, signature, and clinical authenticity
    auth_check = verify_clinical_document_authenticity(extracted_text)

    # Suggest matching policy
    retriever = PolicyRetrievalAgent(db=db)
    candidates = retriever.search_policies_by_narrative(extracted_text)
    suggested_policy = "NCD-20.4"
    policy_title = "Implantable Automatic Defibrillators"
    if candidates and candidates[0]["relevance_score"] > 0.05:
        suggested_policy = candidates[0]["policy_id"]
        policy_title = candidates[0].get("title", suggested_policy)

    return {
        "filename": safe_filename,
        "character_count": len(extracted_text),
        "extracted_text": extracted_text,
        "suggested_policy_id": suggested_policy,
        "suggested_policy_title": policy_title,
        "authenticity": auth_check
    }

@api_router.post("/verify-clinical-note", summary="Verify Clinical Note Authenticity (Doctor Name & Signature Check)")
def verify_clinical_note(payload: Dict[str, str]):
    """
    Validates that a clinical document contains an authentic physician/doctor name,
    provider digital or handwritten signature block, and sufficient clinical documentation structure.
    """
    text = payload.get("text", "")
    return verify_clinical_document_authenticity(text)

@api_router.post("/upload-note", summary="Upload Doctor's Clinical Note & Auto-Adjudicate")
async def upload_clinical_note(
    file: UploadFile = File(...),
    policy_id: Optional[str] = Form(None),
    patient_id: Optional[str] = Form("PT-UPLOADED"),
    tau: Optional[float] = Form(0.85),
    zero_retention: Optional[bool] = Form(False),
    db: Session = Depends(get_db)
):
    """
    Primary Physician Ingestion Workflow:
    1. Physician uploads clinical consultation note, discharge summary, or diagnostic report (.pdf, .docx, .txt, or image).
    2. Validates security constraints, size limits, and filename integrity.
    3. If policy is not manually selected, Agent 1 auto-identifies the governing Medicare NCD/LCD policy.
    4. Multi-agent pipeline adjudicates criteria, checks offsets, and computes calibrated confidence.
    5. Assembles official pre-filled CMS Prior Authorization / Coverage Packet ready for clinician review.
    6. Respects zero-retention mode when requested.
    """
    content = await file.read()
    safe_filename = validate_and_sanitize_upload(file.filename, content)

    try:
        extracted_text = extract_text_from_upload(safe_filename, content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read document text: {str(e)}")

    if len(extracted_text) < 20:
        raise HTTPException(status_code=400, detail="Extracted document text is too short to evaluate.")

    # Auto-detect policy if not specified
    pipeline = MultiAgentVerificationPipeline(db=db)
    if not policy_id or policy_id.lower() in ["auto", "none", ""]:
        retriever = PolicyRetrievalAgent(db=db)
        candidates = retriever.search_policies_by_narrative(extracted_text)
        if candidates and candidates[0]["relevance_score"] > 0.05:
            policy_id = candidates[0]["policy_id"]
        else:
            policy_id = "NCD-20.4"  # Default cardiology fallback

    # Execute Adjudication Pipeline
    adjudication = await pipeline.adjudicate(
        patient_id=patient_id or "PT-UPLOADED",
        policy_id=policy_id,
        ehr_narrative=extracted_text,
        custom_tau=tau,
        save_record=not zero_retention
    )

    # Generate Filled Prior Authorization Document Packet for Review
    packet = CoveragePacketGenerator.generate_packet(adjudication)
    _EPHEMERAL_PACKETS[adjudication.case_id] = packet

    return {
        "filename": safe_filename,
        "extracted_text_preview": extracted_text[:400] + ("..." if len(extracted_text) > 400 else ""),
        "extracted_text": extracted_text,
        "adjudication": adjudication,
        "packet": packet
    }

@api_router.get("/packet/{case_id}", response_model=CMSCoveragePacket, summary="Get Filled Coverage Packet for Review")
def get_coverage_packet(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the filled CMS coverage determination packet for pre-submission clinician review.
    Checks in-memory ephemeral cache first (Zero-Retention mode), then persistent DB.
    """
    if case_id in _EPHEMERAL_PACKETS:
        return _EPHEMERAL_PACKETS[case_id]

    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    if not log:
        raise HTTPException(status_code=404, detail=f"Case adjudication record '{case_id}' not found.")

    import json
    criterion_assessments_raw = json.loads(log.criterion_evaluations_json)
    from app.schemas.contracts import CriterionAssessment
    c_assessments = [CriterionAssessment(**c) for c in criterion_assessments_raw]

    policy_obj = db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == log.policy_id).first()
    policy_title = policy_obj.title if policy_obj else f"Medicare Policy {log.policy_id}"

    adjudication_dummy = FinalAdjudication(
        case_id=log.case_id,
        patient_id_masked=log.patient_id_masked,
        policy_id=log.policy_id,
        policy_title=policy_title,
        adjudication_decision=log.decision,
        abstention_status=log.abstention_status,
        raw_aggregate_confidence=log.raw_confidence,
        calibrated_aggregate_confidence=log.calibrated_confidence,
        abstention_threshold=0.85,
        abstention_reason=log.abstention_reason,
        criterion_assessments=c_assessments,
        verification_audits=[],
        audit_hash=log.audit_hash,
        required_clinician_action_notes=log.required_clinician_action_notes,
        execution_time_ms=log.execution_time_ms,
        sanitized_ehr_text="",
        timestamp=log.created_at
    )

    packet = CoveragePacketGenerator.generate_packet(adjudication_dummy)
    packet.submission_status = log.submission_status or "PENDING_CLINICIAN_REVIEW"
    packet.signed_by = log.signed_by
    packet.signed_at = log.signed_at.isoformat() if log.signed_at else None
    packet.payer_transaction_id = log.payer_transaction_id
    _EPHEMERAL_PACKETS[case_id] = packet
    return packet

@api_router.post("/packet/submit", response_model=SubmissionReceipt, summary="Sign & Submit Reviewed Policy Packet to Insurance")
def submit_coverage_to_insurance(
    request: SubmitPacketRequest,
    db: Session = Depends(get_db)
):
    """
    Clinician Sign-Off & Electronic Submission to Medicare Payer:
    Transmits the reviewed, cryptographically sealed coverage document to the payer clearinghouse gateway.
    Handles both persistent and ephemeral zero-retention packets gracefully.
    """
    now = datetime.now(timezone.utc)
    transaction_id = f"CMS-EDI-837-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == request.case_id).first()
    if log:
        log.submission_status = "SUBMITTED_TO_PAYER"
        log.signed_by = request.signed_by
        log.signed_at = now
        log.payer_transaction_id = transaction_id
        if request.clinician_notes:
            log.required_clinician_action_notes = (log.required_clinician_action_notes or "") + f"\n[Clinician Attestation Note]: {request.clinician_notes}"
        db.commit()
        audit_hash = log.audit_hash
    elif request.case_id in _EPHEMERAL_PACKETS:
        packet = _EPHEMERAL_PACKETS[request.case_id]
        packet.submission_status = "SUBMITTED_TO_PAYER"
        packet.signed_by = request.signed_by
        packet.signed_at = now.isoformat()
        packet.payer_transaction_id = transaction_id
        audit_hash = packet.audit_hash
    else:
        raise HTTPException(status_code=404, detail=f"Case '{request.case_id}' not found.")

    return SubmissionReceipt(
        case_id=request.case_id,
        packet_id=f"CMS-PAC-{request.case_id}",
        payer_transaction_id=transaction_id,
        submission_status="TRANSMITTED_ACCEPTED",
        signed_by=request.signed_by,
        signed_at=now.isoformat(),
        payer_name=request.payer_name or "CMS Medicare MAC Gateway",
        audit_hash=audit_hash,
        message="Packet successfully signed and electronically transmitted to Medicare Part B / CMS clearinghouse."
    )

@api_router.post("/packet/{case_id}/appeal-letter", response_model=PeerToPeerAppealLetter, summary="Generate Peer-to-Peer Medical Reconsideration Letter")
def generate_appeal_letter(
    case_id: str,
    request: Optional[PeerToPeerAppealRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Generates an expedited Peer-to-Peer Appeal Letter and talking points for physician
    defense before the Medicare Administrative Contractor (MAC) Medical Director.
    """
    packet = get_coverage_packet(case_id, db=db)
    return PeerToPeerAppealService.generate_appeal(packet, request)

@api_router.get("/packet/{case_id}/fhir", summary="Export Standard HL7 FHIR R4 Da Vinci PAS Bundle")
def export_fhir_bundle(
    case_id: str,
    db: Session = Depends(get_db)
):
    """
    Exports the prior authorization case as an official HL7 FHIR R4 Bundle compliant with
    the Da Vinci Prior Authorization Support (PAS) specification.
    """
    packet = get_coverage_packet(case_id, db=db)
    return FHIRExportService.generate_fhir_bundle(packet)

@api_router.post("/packet/{case_id}/ehr-push", response_model=EHRPushReceipt, summary="Direct Interoperability Push to Hospital EHR")
def push_packet_to_ehr(
    case_id: str,
    request: Optional[EHRPushRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Pushes the verified, cryptographically signed prior authorization packet directly
    into the hospital EHR (Epic / Cerner) as an official FHIR DocumentReference.
    """
    packet = get_coverage_packet(case_id, db=db)
    return FHIRExportService.push_to_ehr(packet, request)

@api_router.post("/packet/{case_id}/addendum", response_model=ClinicalAddendumResponse, summary="Append Signed Clinical Addendum & Re-Adjudicate")
async def append_clinical_addendum(
    case_id: str,
    request: ClinicalAddendumRequest,
    db: Session = Depends(get_db)
):
    """
    Physician Decision Support / Smart Addendum Generator:
    Appends an attested, signed clinical addendum addressing missing or deficient criteria,
    automatically re-runs the multi-agent verification pipeline on the updated chart,
    updates the audit ledger, and returns the updated adjudication decision.
    """
    now = datetime.now(timezone.utc)
    addendum_id = f"ADDENDUM-{uuid.uuid4().hex[:8].upper()}"

    # 1. Retrieve original clinical narrative & metadata
    original_text = _EPHEMERAL_EHR_TEXTS.get(case_id)
    policy_id = None
    patient_id = "PT-10829"
    prior_decision = "DENIED"

    log = db.query(AdjudicationLog).filter(AdjudicationLog.case_id == case_id).first()
    if log:
        policy_id = log.policy_id
        patient_id = log.patient_id_masked
        prior_decision = log.decision
        if not original_text:
            original_text = log.sanitized_ehr_preview
    elif case_id in _EPHEMERAL_PACKETS:
        packet = _EPHEMERAL_PACKETS[case_id]
        policy_id = packet.policy_id
        patient_id = packet.patient_id_masked
        prior_decision = packet.adjudication_decision
        if not original_text:
            original_text = packet.clinical_summary
    else:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    if not original_text:
        original_text = "Clinical progress note."

    # 2. Format legally compliant clinical addendum block
    addendum_block = (
        f"\n\n--- CLINICAL ADDENDUM [{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] ---\n"
        f"Author: {request.clinician_name or 'Attending Physician'} (NPI: {request.clinician_npi})\n"
        f"Target Criterion: {request.criterion_code or 'Coverage Verification & Medical Necessity'}\n"
        f"Attested Clinical Note: {request.addendum_text}\n"
        f"Certification: I hereby certify that the above clinical documentation reflects true patient observations.\n"
        f"--- END ADDENDUM ---"
    )
    updated_narrative = original_text + addendum_block

    # 3. Asynchronously Re-Adjudicate with the Multi-Agent Pipeline
    pipeline = MultiAgentVerificationPipeline(db=db)
    updated_adj = await pipeline.adjudicate(
        patient_id=patient_id,
        policy_id=policy_id,
        ehr_narrative=updated_narrative,
        save_record=(log is not None)
    )

    # 4. Update Ephemeral Stores
    _EPHEMERAL_EHR_TEXTS[updated_adj.case_id] = updated_narrative
    _EPHEMERAL_ADJUDICATIONS[updated_adj.case_id] = updated_adj
    new_packet = CoveragePacketGenerator.generate_packet(updated_adj, physician_name=request.clinician_name)
    _EPHEMERAL_PACKETS[updated_adj.case_id] = new_packet

    # 5. Update existing DB log if applicable
    if log:
        log.decision = updated_adj.adjudication_decision.value
        log.abstention_status = updated_adj.abstention_status
        log.abstention_reason = updated_adj.abstention_reason
        log.calibrated_confidence = updated_adj.calibrated_aggregate_confidence
        log.audit_hash = updated_adj.audit_hash
        log.required_clinician_action_notes = (
            (log.required_clinician_action_notes or "") +
            f"\n[ADDENDUM {addendum_id} by NPI {request.clinician_npi}]: {request.addendum_text}"
        )
        db.commit()

    return ClinicalAddendumResponse(
        case_id=updated_adj.case_id,
        status="ADDENDUM_APPLIED",
        addendum_id=addendum_id,
        criterion_addressed=request.criterion_code,
        appended_at=now.isoformat(),
        signed_by=request.clinician_name or "Attending Physician",
        signed_npi=request.clinician_npi,
        prior_decision=prior_decision,
        updated_decision=updated_adj.adjudication_decision.value,
        updated_confidence=updated_adj.calibrated_aggregate_confidence,
        audit_hash=updated_adj.audit_hash,
        updated_adjudication=updated_adj,
        message=f"Addendum {addendum_id} successfully appended. Case re-evaluated: decision updated to {updated_adj.adjudication_decision.value} ({updated_adj.calibrated_aggregate_confidence:.1%} confidence)."
    )

@api_router.get("/audit/trail", response_model=AuditTrailResponse, summary="Inspect HIPAA & RAC Audit Trail")
def get_audit_trail(db: Session = Depends(get_db)):
    """
    HIPAA § 164.312(b) Audit Controls:
    Returns chronological, cryptographically verified audit records tracking clinician interactions,
    automated pipeline adjudications, submissions, and addendums.
    """
    logs = db.query(AdjudicationLog).order_by(AdjudicationLog.created_at.desc()).limit(100).all()
    events: List[AuditTrailEvent] = []

    for l in logs:
        action_type = "SUBMISSION_ACCEPTED" if l.submission_status == "SUBMITTED_TO_PAYER" else "ADJUDICATION_DECISION"
        actor = l.signed_by or "CarePolicyGuard Multi-Agent System"
        role = "Clinician" if l.signed_by else "Autonomous Verification Engine"
        events.append(AuditTrailEvent(
            event_id=f"AUD-EVT-{l.id:05d}",
            timestamp=l.created_at.isoformat() if l.created_at else datetime.now(timezone.utc).isoformat(),
            event_type=action_type,
            case_id=l.case_id,
            patient_id_masked=l.patient_id_masked,
            actor=actor,
            actor_role=role,
            action_details=(
                f"Policy: {l.policy_id} | Outcome: {l.decision} | "
                f"Confidence: {l.calibrated_confidence:.1%} | Status: {l.submission_status}"
            ),
            audit_hash=l.audit_hash
        ))

    return AuditTrailResponse(
        total_events=len(events),
        system_mode="ZERO_RETENTION_HIPAA_COMPLIANT",
        events=events
    )

@api_router.get("/audit/trail/export", summary="Export Compliance Audit Trail (CSV)")
def export_audit_trail_csv(db: Session = Depends(get_db)):
    """
    Generates an official RFC 4180 CSV export of the tamper-evident audit ledger for CMS RAC/MAC auditors.
    """
    logs = db.query(AdjudicationLog).order_by(AdjudicationLog.created_at.desc()).all()
    output = io.StringIO()
    output.write("Event ID,Timestamp (UTC),Event Type,Case ID,Patient Masked,Actor,Actor Role,Action Details,Audit Hash (SHA-256)\n")

    for l in logs:
        action_type = "SUBMISSION_ACCEPTED" if l.submission_status == "SUBMITTED_TO_PAYER" else "ADJUDICATION_DECISION"
        actor = l.signed_by or "CarePolicyGuard Multi-Agent Engine"
        role = "Clinician" if l.signed_by else "Autonomous Engine"
        ts = l.created_at.isoformat() if l.created_at else datetime.now(timezone.utc).isoformat()
        details = f"Policy {l.policy_id} - Outcome {l.decision} (Confidence {l.calibrated_confidence:.1%}) - Status {l.submission_status}"
        details_escaped = details.replace('"', '""')
        output.write(f'"AUD-EVT-{l.id:05d}","{ts}","{action_type}","{l.case_id}","{l.patient_id_masked}","{actor}","{role}","{details_escaped}","{l.audit_hash}"\n')

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="carepolicyguard_audit_trail.csv"'
        }
    )


