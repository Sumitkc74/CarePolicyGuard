from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import MedicarePolicy, AdjudicationLog
from app.agents.criteria_evaluator import evaluate_patient_against_policy
from app.core.idempotency import idempotency_engine

class PASClaimItem(BaseModel):
    sequence: int = 1
    productOrService: Dict[str, Any] = Field(
        ...,
        description="Coding for procedure or device, e.g. CPT 33249 or 37215"
    )

class PASClaimRequest(BaseModel):
    resourceType: str = Field(default="Claim", description="FHIR R4 Claim")
    id: Optional[str] = None
    use: str = Field(default="preauthorization", description="Pre-authorization use")
    patient: Dict[str, str] = Field(..., description="Reference to Patient, e.g. {'reference': 'Patient/PT-101'}")
    provider: Dict[str, str] = Field(..., description="Reference to Practitioner, e.g. {'reference': 'Practitioner/NPI-1043256787'}")
    insurance: Optional[List[Dict[str, Any]]] = None
    item: Optional[List[PASClaimItem]] = None
    supportingInfo: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Clinical consultation notes, diagnostic reports, or DTR QuestionnaireResponse"
    )

class PASAdjudicationDetail(BaseModel):
    category: Dict[str, Any]
    reason: Optional[Dict[str, Any]] = None
    amount: Optional[Dict[str, Any]] = None

class PASClaimItemResponse(BaseModel):
    itemSequence: int
    adjudication: List[PASAdjudicationDetail]

class PASClaimResponse(BaseModel):
    resourceType: str = "ClaimResponse"
    id: str
    status: str = "active"
    type: Dict[str, Any]
    use: str = "preauthorization"
    patient: Dict[str, str]
    created: str
    insurer: Dict[str, str]
    requestor: Dict[str, str]
    outcome: str  # "complete", "pended", "error"
    disposition: str
    preAuthRef: Optional[str] = None
    item: Optional[List[PASClaimItemResponse]] = None
    adjudication_summary: Dict[str, Any]

def _evaluate_pas_claim(
    claim: PASClaimRequest,
    patient_id: str,
    provider_ref: str,
    combined_narrative: str,
    db: Session
) -> PASClaimResponse:
    # Identify applicable policy
    target_policy_id = "NCD-20.4"
    lower = combined_narrative.lower()
    if "carotid" in lower or "cas" in lower or ("stent" in lower and "endarterectomy" in lower):
        target_policy_id = "NCD-20.7"
    elif "mitral" in lower or "regurgitation" in lower or "teer" in lower:
        target_policy_id = "NCD-20.33"
    elif "sacral" in lower or "incontinence" in lower:
        target_policy_id = "LCD-L33829"

    # Check item CPT codes if provided
    if claim.item:
        for it in claim.item:
            code = it.productOrService.get("coding", [{}])[0].get("code", "")
            if code in ["37215", "37216"]:
                target_policy_id = "NCD-20.7"
            elif code in ["33418", "33419"]:
                target_policy_id = "NCD-20.33"
            elif code in ["33249", "33216"]:
                target_policy_id = "NCD-20.4"

    policy = db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == target_policy_id).first()
    eval_result = evaluate_patient_against_policy(combined_narrative, policy)

    is_approved = eval_result["determination"] == "APPROVED"
    auth_ref = f"AUTH-CMS-{uuid.uuid4().hex[:10].upper()}" if is_approved else None
    outcome = "complete" if is_approved else "pended"

    if is_approved:
        disposition = f"Approved: CMS Medicare Prior-Authorization cleared under {target_policy_id}. {eval_result['clinical_rationale']}"
        adj_category = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/adjudication", "code": "eligible", "display": "Eligible Amount"}]}
        adj_reason = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/adjudication-reason", "code": "cleared", "display": "Statutory Criteria Satisfied"}]}
    else:
        missing = ", ".join(eval_result.get("missing_criteria", []))
        disposition = f"Pended for Clinical Addendum: Documentation does not satisfy all statutory criteria. Missing: {missing}."
        adj_category = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/adjudication", "code": "pended", "display": "Pended for Evidence"}]}
        adj_reason = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/adjudication-reason", "code": "deficiency", "display": "Clinical Documentation Deficiency"}]}

    claim_response_id = f"cr-{uuid.uuid4().hex[:12]}"

    return PASClaimResponse(
        id=claim_response_id,
        type={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional", "display": "Professional"}]},
        patient={"reference": f"Patient/{patient_id}"},
        created=datetime.now(timezone.utc).isoformat(),
        insurer={"reference": "Organization/CMS-MEDICARE"},
        requestor={"reference": provider_ref},
        outcome=outcome,
        disposition=disposition,
        preAuthRef=auth_ref,
        item=[
            PASClaimItemResponse(
                itemSequence=1,
                adjudication=[
                    PASAdjudicationDetail(
                        category=adj_category,
                        reason=adj_reason
                    )
                ]
            )
        ],
        adjudication_summary={
            "policy_id": target_policy_id,
            "confidence_score": eval_result.get("confidence_score", 0.95),
            "missing_criteria": eval_result.get("missing_criteria", [])
        }
    )

def submit_pas_claim(
    claim: PASClaimRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    HL7 Da Vinci PAS (Prior Authorization Support) $submit Operation:
    Ingests a FHIR R4 Claim resource with preauthorization intent,
    evaluates supporting clinical narratives and draft orders against CMS policies,
    and returns an official FHIR R4 ClaimResponse.
    Supports IETF Idempotency-Key headers to prevent race conditions and duplicate claim evaluations.
    """
    patient_ref = claim.patient.get("reference", "Patient/PT-UNKNOWN")
    patient_id = patient_ref.replace("Patient/", "")
    provider_ref = claim.provider.get("reference", "Practitioner/UNKNOWN")

    # Extract clinical narrative from supportingInfo
    narrative_parts = []
    for info in (claim.supportingInfo or []):
        if "valueString" in info:
            narrative_parts.append(info["valueString"])
        elif "valueAttachment" in info and "data" in info["valueAttachment"]:
            narrative_parts.append(info["valueAttachment"]["data"])

    combined_narrative = "\n".join(narrative_parts) if narrative_parts else "Prior authorization request for high-complexity medical device."

    # Check for client-supplied idempotency key
    idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")

    if idempotency_key:
        scoped_key = f"pas:{idempotency_key}"

        def compute_action():
            claim_resp = _evaluate_pas_claim(claim, patient_id, provider_ref, combined_narrative, db)
            return claim_resp.model_dump(), 200, None

        payload, status_code, _, is_replay = idempotency_engine.execute_idempotent(
            idempotency_key=scoped_key,
            action=compute_action
        )
        if is_replay:
            response.headers["Idempotency-Replay"] = "true"
        return PASClaimResponse(**payload)

    return _evaluate_pas_claim(claim, patient_id, provider_ref, combined_narrative, db)

def register_pas_routes(api_router: APIRouter):
    api_router.add_api_route(
        "/pas/submit",
        submit_pas_claim,
        methods=["POST"],
        response_model=PASClaimResponse,
        summary="HL7 Da Vinci PAS: $submit Operation for Pre-Authorization Claim"
    )
