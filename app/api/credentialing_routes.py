import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.core.config import settings
from app.core.security import compute_audit_hash, UserRole
from app.db.models import CredentialingAuditLog, User
from app.schemas.contracts import (
    CredentialingAuditLogOut,
    ManualCredentialingRequest,
    NppesVerificationRequest,
    NppesVerificationResponse,
    RevokeVerificationRequest,
    UserOut,
)
from app.services.nppes_verifier import verify_npi_with_nppes

logger = logging.getLogger("app.api.credentialing")


def register_credentialing_routes(api_router: APIRouter):
    """
    Registers primary-source and credentialing authority verification endpoints.
    Enforces separation of duties: Credentialing authority / Primary-source check.
    """

    @api_router.post(
        "/credentialing/verify/nppes",
        response_model=NppesVerificationResponse,
        summary="Primary Source CMS NPPES NPI Registry Verification"
    )
    def verify_npi_nppes(
        req: NppesVerificationRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Primary-source credentialing verification against CMS NPPES NPI Registry API:
        1. Queries public CMS NPPES Registry API with submitted 10-digit NPI.
        2. Requires authentic provider name match against account holder.
        3. Never stores full registry payload.
        4. Fails closed (stays unverified) on network failure, timeout, or name mismatch.
        5. On success: unlocks clinical sign-off, records method NPPES_VERIFIED, registry ref,
           and expiration date based on operator policy.
        """
        # Determine target clinician
        if req.clinician_id is not None:
            if current_user.role != UserRole.CREDENTIALING.value and current_user.id != req.clinician_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Cannot verify credentials for other clinicians without Credentialing role."
                )
            target = db.query(User).filter(User.id == req.clinician_id).first()
            if not target:
                raise HTTPException(status_code=404, detail=f"Clinician with ID {req.clinician_id} not found.")

            if current_user.id != target.id:
                if target.provisioned_by and (
                    target.provisioned_by == current_user.username
                    or target.provisioned_by == current_user.email
                    or target.provisioned_by == str(current_user.id)
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Separation of duties violation: An account cannot verify a clinician it provisioned."
                    )
        else:
            target = current_user

        if target.role != UserRole.CLINICIAN.value:
            raise HTTPException(status_code=400, detail="Only clinician accounts may undergo medical credential verification.")

        account_name = req.full_name or target.full_name or target.username

        # Execute primary-source lookup
        result = verify_npi_with_nppes(req.npi_number, account_name)

        now = datetime.now(UTC)
        if not result["is_verified"]:
            # Audit failed verification attempt
            audit_event = CredentialingAuditLog(
                event_id=f"NPPES-FAIL-{uuid.uuid4().hex[:12].upper()}",
                clinician_id=target.id,
                clinician_email=target.email,
                actor_id=current_user.id,
                actor_username=current_user.username,
                actor_role=current_user.role,
                action="NPPES_VERIFICATION_FAILED",
                verification_method="NPPES_REGISTRY_CHECK",
                evidence_reference=f"NPI-{req.npi_number}",
                previous_state="UNVERIFIED" if not target.is_verified_medical_pro else "VERIFIED",
                new_state="UNVERIFIED",
                notes=f"CMS NPPES primary source check failed: {'; '.join(result['reasons'])}",
                audit_hash=compute_audit_hash(
                    patient_id_masked="SYSTEM",
                    policy_id="CREDENTIALING",
                    decision="NPPES_FAILED",
                    calibrated_confidence=0.0,
                    criterion_assessments=[],
                    evidence_spans=[],
                    timestamp=now
                )
            )
            db.add(audit_event)
            db.commit()

            return NppesVerificationResponse(
                is_verified=False,
                npi_number=req.npi_number,
                verification_method="NPPES_FAILED_CLOSED",
                registry_reference=None,
                verified_at=None,
                expires_at=None,
                message="CMS NPPES primary source verification failed. Account remains unverified.",
                reasons=result["reasons"]
            )

        # Success: unlock signing and record primary-source verification
        validity_days = settings.CREDENTIAL_VERIFICATION_VALIDITY_DAYS
        expires_at = now + timedelta(days=validity_days)

        prev_state = "VERIFIED" if target.is_verified_medical_pro else "UNVERIFIED"
        target.is_verified_medical_pro = True
        target.npi_number = req.npi_number
        target.verification_method = "NPPES_VERIFIED"
        target.verification_reference = result["registry_reference"]
        target.verified_at = now
        target.verified_by = current_user.username
        target.verification_expires_at = expires_at

        # Immutable audit ledger
        audit_event = CredentialingAuditLog(
            event_id=f"NPPES-VERIF-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=target.id,
            clinician_email=target.email,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            action="VERIFIED",
            verification_method="NPPES_VERIFIED",
            evidence_reference=result["registry_reference"],
            previous_state=prev_state,
            new_state="VERIFIED",
            notes=(
                f"Primary source NPPES verified against CMS Registry API. "
                f"Matched provider: '{result['matched_name']}'. Validity: {validity_days} days."
            ),
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="CREDENTIALING",
                decision="NPPES_VERIFIED",
                calibrated_confidence=1.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=now
            )
        )
        db.add(audit_event)
        db.commit()
        db.refresh(target)

        logger.info(
            f"[CREDENTIALING AUDIT]: Clinician '{target.email}' (NPI: {req.npi_number}) "
            f"verified via primary source CMS NPPES Registry API by '{current_user.username}'. "
            f"Valid until {expires_at.isoformat()}."
        )

        return NppesVerificationResponse(
            is_verified=True,
            npi_number=req.npi_number,
            verification_method="NPPES_VERIFIED",
            registry_reference=result["registry_reference"],
            verified_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            message=f"Primary-source NPPES verification successful. Matched provider: {result['matched_name']}. Signing authority unlocked.",
            reasons=[]
        )

    @api_router.post(
        "/credentialing/verify/manual",
        response_model=UserOut,
        summary="Manual Credentialing Review Approval or Rejection"
    )
    def manual_credentialing_review(
        req: ManualCredentialingRequest,
        current_approver: User = Depends(require_role([UserRole.CREDENTIALING.value])),
        db: Session = Depends(get_db)
    ):
        """
        Manual Credentialing Review (Fallback Path):
        Requires distinct Credentialing role (Admin role cannot approve).
        Enforces separation of duties:
        1. An account cannot approve its own credentials.
        2. An account cannot approve a clinician it provisioned (actor separation).
        Records: evidence checked (NPI, license, state, org), approver, timestamp, previous state, decision.
        """
        decision_clean = req.decision.strip().upper()
        if decision_clean not in ("APPROVED", "REJECTED"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Decision must be either 'APPROVED' or 'REJECTED'."
            )

        target_clinician = db.query(User).filter(User.id == req.clinician_id).first()
        if not target_clinician:
            raise HTTPException(status_code=404, detail=f"Clinician with ID {req.clinician_id} not found.")

        if target_clinician.role != UserRole.CLINICIAN.value:
            raise HTTPException(status_code=400, detail="Manual credentialing review applies strictly to Clinician accounts.")

        # Invariant: approver cannot approve their own account
        if target_clinician.id == current_approver.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duties violation: An approver cannot approve their own account."
            )

        # Invariant: approver cannot approve a clinician they provisioned
        if target_clinician.provisioned_by and (
            target_clinician.provisioned_by == current_approver.username
            or target_clinician.provisioned_by == current_approver.email
            or target_clinician.provisioned_by == str(current_approver.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duties violation: An account cannot approve a clinician it provisioned."
            )

        # Double check provisioning audit log
        prov_audit = db.query(CredentialingAuditLog).filter(
            CredentialingAuditLog.clinician_id == target_clinician.id,
            CredentialingAuditLog.action.in_(["PROVISIONED", "USER_PROVISIONED"]),
            CredentialingAuditLog.actor_id == current_approver.id
        ).first()
        if prov_audit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duties violation: An account cannot approve a clinician it provisioned."
            )

        now = datetime.now(UTC)
        prev_state = "VERIFIED" if target_clinician.is_verified_medical_pro else "UNVERIFIED"

        if decision_clean == "APPROVED":
            target_clinician.is_verified_medical_pro = True
            target_clinician.verification_method = "MANUAL_CREDENTIALING_VERIFIED"
            target_clinician.verification_reference = req.evidence_reference
            target_clinician.verified_at = now
            target_clinician.verified_by = current_approver.username
            target_clinician.verification_expires_at = now + timedelta(days=settings.CREDENTIAL_VERIFICATION_VALIDITY_DAYS)

            if req.npi_number:
                target_clinician.npi_number = req.npi_number
            if req.medical_license:
                target_clinician.medical_license = req.medical_license
            if req.license_state:
                target_clinician.license_state = req.license_state
            if req.credential_title:
                target_clinician.credential_title = req.credential_title
            if req.organization:
                target_clinician.organization = req.organization
            new_state = "VERIFIED"
        else:
            target_clinician.is_verified_medical_pro = False
            target_clinician.verification_method = "MANUAL_CREDENTIALING_REJECTED"
            target_clinician.verification_reference = req.evidence_reference
            new_state = "REJECTED"

        # Immutable audit ledger record
        audit_event = CredentialingAuditLog(
            event_id=f"MANUAL-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=target_clinician.id,
            clinician_email=target_clinician.email,
            actor_id=current_approver.id,
            actor_username=current_approver.username,
            actor_role=current_approver.role,
            action=decision_clean,
            verification_method="MANUAL_CREDENTIALING",
            evidence_reference=req.evidence_reference,
            previous_state=prev_state,
            new_state=new_state,
            notes=(
                f"Manual credentialing {decision_clean} by {current_approver.username} ({current_approver.role}). "
                f"Evidence evaluated: {', '.join(req.evidence_checked)}. Ref: {req.evidence_reference}. Notes: {req.notes or 'None'}"
            ),
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="CREDENTIALING_MANUAL",
                decision=decision_clean,
                calibrated_confidence=1.0 if decision_clean == "APPROVED" else 0.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=now
            )
        )
        db.add(audit_event)
        db.commit()
        db.refresh(target_clinician)

        logger.info(
            f"[CREDENTIALING AUDIT]: Clinician '{target_clinician.email}' manual review: {decision_clean} "
            f"by '{current_approver.username}' ({current_approver.role}). Ref: {req.evidence_reference}"
        )
        return target_clinician

    @api_router.post(
        "/credentialing/users/{user_id}/revoke",
        summary="Revoke or Suspend Clinician Verification"
    )
    def revoke_clinician_verification(
        user_id: int,
        req: RevokeVerificationRequest,
        current_user: User = Depends(require_role([UserRole.CREDENTIALING.value, UserRole.ADMIN.value])),
        db: Session = Depends(get_db)
    ):
        """
        Revokes or suspends a clinician's verified status.
        Security invariant:
        - Immediately blocks all new clinical sign-offs (403 Forbidden).
        - Past signed determinations remain intact, valid, and permanently auditable.
        - Records mandatory credentialing review record and immutable audit trail.
        """
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(status_code=404, detail=f"Clinician with ID {user_id} not found.")

        now = datetime.now(UTC)
        prev_state = "VERIFIED" if target.is_verified_medical_pro else "UNVERIFIED"

        is_admin = current_user.role == UserRole.ADMIN.value
        action = "EMERGENCY_SUSPENDED" if is_admin else "REVOKED"
        verif_method = "ADMIN_EMERGENCY_SUSPENSION" if is_admin else "CREDENTIALING_REVOCATION"

        target.is_verified_medical_pro = False
        target.verification_method = verif_method
        target.verification_reference = req.reason

        audit_event = CredentialingAuditLog(
            event_id=f"REVOKE-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=target.id,
            clinician_email=target.email,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            action=action,
            verification_method=verif_method,
            evidence_reference=req.reason,
            previous_state=prev_state,
            new_state="UNVERIFIED",
            notes=(
                f"{'Admin emergency suspension' if is_admin else 'Credential verification revoked'} by {current_user.username} ({current_user.role}). "
                f"Reason: {req.reason}. Review Notes: {req.mandatory_review_notes or 'None'}"
            ),
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="REVOCATION",
                decision=action,
                calibrated_confidence=1.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=now
            )
        )
        db.add(audit_event)
        db.commit()

        logger.info(
            f"[CREDENTIALING AUDIT]: Verification REVOKED for clinician '{target.email}' "
            f"by '{current_user.username}' ({current_user.role}). Reason: {req.reason}"
        )

        return {
            "status": "SUCCESS",
            "clinician_id": target.id,
            "clinician_email": target.email,
            "is_verified_medical_pro": False,
            "message": "Clinician verification revoked. New sign-offs are immediately blocked. Past signed determinations remain auditable."
        }

    @api_router.get(
        "/credentialing/audit-logs",
        response_model=List[CredentialingAuditLogOut],
        summary="List Credentialing and Provisioning Audit Ledger"
    )
    def list_credentialing_audit_logs(
        clinician_id: Optional[int] = Query(None, description="Filter by specific clinician ID"),
        limit: int = Query(100, ge=1, le=500),
        current_user: User = Depends(require_role([UserRole.CREDENTIALING.value, UserRole.AUDITOR.value, UserRole.ADMIN.value])),
        db: Session = Depends(get_db)
    ):
        """
        Lists immutable credentialing audit records tracking provisioning, primary-source checks,
        manual reviews, revocations, and downgrades.
        Accessible by Credentialing, Auditor, and Admin roles.
        """
        query = db.query(CredentialingAuditLog)
        if clinician_id is not None:
            query = query.filter(CredentialingAuditLog.clinician_id == clinician_id)
        records = query.order_by(CredentialingAuditLog.created_at.desc()).limit(limit).all()
        return records

