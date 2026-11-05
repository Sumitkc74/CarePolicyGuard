import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.security import compute_audit_hash, get_password_hash, UserRole
from app.db.models import CredentialingAuditLog, User, UserSession
from app.schemas.contracts import (
    AdminCreateAdminRequest,
    AdminInviteClinicianRequest,
    UserOut,
    UserStatusUpdateRequest,
)

logger = logging.getLogger("app.api.admin")


def register_admin_routes(api_router: APIRouter):
    """
    Registers admin provisioning and management endpoints.
    Enforces separation of duties: Admin role only.
    """

    @api_router.post(
        "/admin/users/clinicians",
        response_model=UserOut,
        status_code=status.HTTP_201_CREATED,
        summary="Admin Provision / Invite Clinician"
    )
    def admin_invite_clinician(
        req: AdminInviteClinicianRequest,
        current_admin: User = Depends(require_role([UserRole.ADMIN.value])),
        db: Session = Depends(get_db)
    ):
        """
        Admin Provisions / Invites a Clinician Account.
        Strict Governance Rules:
        - The account is created UNVERIFIED (is_verified_medical_pro=False) and CANNOT sign.
        - Invitation does NOT set, imply, or pre-approve verification.
        - Admin provisioning NEVER sets is_verified_medical_pro, npi_number from a generated value,
          or any credential field on its own.
        - Verification must be performed by primary source (NPPES) or Credentialing authority.
        """
        clean_email = req.email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Valid email address is required."
            )

        existing = db.query(User).filter(
            (User.username == clean_email) | (User.email == clean_email)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{clean_email}' already exists in system."
            )

        initial_password = req.initial_password or secrets.token_urlsafe(16)

        new_clinician = User(
            username=clean_email,
            email=clean_email,
            full_name=req.full_name or clean_email.split("@")[0].replace(".", " ").title(),
            hashed_password=get_password_hash(initial_password),
            role=UserRole.CLINICIAN.value,
            is_active=True,
            is_verified_medical_pro=False,  # Unverified by design
            verification_method=None,
            npi_number=None,  # Never invented or generated
            credential_title=None,
            medical_license=None,
            license_state=None,
            specialty=None,
            organization=None,
            is_demo_user=False,
            is_bootstrap=False,
            must_change_password=True,
            must_setup_mfa=False,
            mfa_enabled=True,
            mfa_method="email_otp",
            mfa_enabled_methods="email_otp",
            provisioned_by=current_admin.username
        )
        db.add(new_clinician)
        db.commit()
        db.refresh(new_clinician)

        # Audit ledger record
        audit_event = CredentialingAuditLog(
            event_id=f"PROV-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=new_clinician.id,
            clinician_email=new_clinician.email,
            actor_id=current_admin.id,
            actor_username=current_admin.username,
            actor_role=current_admin.role,
            action="PROVISIONED",
            verification_method="ADMIN_PROVISIONED",
            evidence_reference=f"ADMIN-INVITE-BY-{current_admin.username}",
            previous_state=None,
            new_state="UNVERIFIED",
            notes=f"Clinician account provisioned by Admin '{current_admin.username}'. Account is unverified and unable to sign determinations.",
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="ADMIN_PROVISIONING",
                decision="CLINICIAN_PROVISIONED",
                calibrated_confidence=1.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=datetime.now(UTC)
            )
        )
        db.add(audit_event)
        db.commit()

        logger.info(
            f"[ADMIN AUDIT]: Clinician account '{clean_email}' provisioned by Admin '{current_admin.username}'. "
            f"Account created UNVERIFIED; cannot sign until primary-source/credentialing verification."
        )
        return new_clinician

    @api_router.post(
        "/admin/users/admins",
        response_model=UserOut,
        status_code=status.HTTP_201_CREATED,
        summary="Create New Administrator (Admin Only)"
    )
    def admin_create_admin(
        req: AdminCreateAdminRequest,
        current_admin: User = Depends(require_role([UserRole.ADMIN.value])),
        db: Session = Depends(get_db)
    ):
        """
        Creates a new Admin account.
        Sole path to new Admin accounts after bootstrap:
        Must be executed by an authenticated, active administrator.
        Self-registration can never grant Admin role.
        """
        clean_email = req.email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Valid email address is required."
            )

        if len(req.password) < 12:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Administrator password must be at least 12 characters."
            )

        username = (req.username or clean_email).strip().lower()
        existing = db.query(User).filter(
            (User.username == username) | (User.email == clean_email)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with username/email '{clean_email}' already exists in system."
            )

        new_admin = User(
            username=username,
            email=clean_email,
            full_name=req.full_name or "Administrator",
            hashed_password=get_password_hash(req.password),
            role=UserRole.ADMIN.value,
            is_active=True,
            is_demo_user=False,
            is_bootstrap=False,
            must_change_password=False,
            must_setup_mfa=False,
            mfa_enabled=True,
            mfa_method="email_otp",
            mfa_enabled_methods="email_otp",
            provisioned_by=current_admin.username
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)

        # Audit ledger record
        audit_event = CredentialingAuditLog(
            event_id=f"ADM-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=new_admin.id,
            clinician_email=new_admin.email,
            actor_id=current_admin.id,
            actor_username=current_admin.username,
            actor_role=current_admin.role,
            action="ADMIN_CREATED",
            verification_method="ADMIN_PROVISIONED",
            evidence_reference=f"CREATED-BY-{current_admin.username}",
            previous_state=None,
            new_state="ACTIVE_ADMIN",
            notes=f"New Admin account created by existing Admin '{current_admin.username}'.",
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="ADMIN_CREATION",
                decision="ADMIN_CREATED",
                calibrated_confidence=1.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=datetime.now(UTC)
            )
        )
        db.add(audit_event)
        db.commit()

        logger.info(f"[ADMIN AUDIT]: New Admin '{clean_email}' created by Admin '{current_admin.username}'.")
        return new_admin

    @api_router.get(
        "/admin/users/clinicians",
        response_model=List[UserOut],
        summary="List Clinicians with Verification State"
    )
    def admin_list_clinicians(
        pending_only: bool = Query(False, description="Filter for unverified clinicians only"),
        current_admin: User = Depends(require_role([UserRole.ADMIN.value, UserRole.CREDENTIALING.value])),
        db: Session = Depends(get_db)
    ):
        """
        Lists all clinicians or unverified (pending) clinicians with their verification state.
        Accessible by Admin and Credentialing roles.
        """
        query = db.query(User).filter(User.role == UserRole.CLINICIAN.value)
        if pending_only:
            query = query.filter(User.is_verified_medical_pro.is_(False))
        clinicians = query.order_by(User.created_at.desc()).all()
        return clinicians

    @api_router.post(
        "/admin/users/{user_id}/status",
        summary="Deactivate or Suspend User Account"
    )
    def admin_set_user_status(
        user_id: int,
        req: UserStatusUpdateRequest,
        current_admin: User = Depends(require_role([UserRole.ADMIN.value])),
        db: Session = Depends(get_db)
    ):
        """
        Deactivates or suspends a user account.
        Security invariant:
        - Signing and login are immediately blocked while suspended.
        - Active user sessions are revoked.
        - Existing signed determinations are untouched and remain permanently auditable.
        """
        target_user = db.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found."
            )

        # Protect against deactivating oneself if sole active admin
        if target_user.id == current_admin.id and not req.is_active:
            active_admins = db.query(User).filter(
                User.role == UserRole.ADMIN.value,
                User.is_active.is_(True)
            ).count()
            if active_admins <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the sole remaining active administrator."
                )

        prev_status = target_user.is_active
        target_user.is_active = req.is_active

        # If deactivated, revoke all active sessions immediately
        if not req.is_active:
            sessions = db.query(UserSession).filter(
                UserSession.user_id == target_user.id,
                UserSession.is_revoked.is_(False)
            ).all()
            for s in sessions:
                s.is_revoked = True
                s.revoked_at = datetime.now(UTC)

        action_name = "ACTIVATED" if req.is_active else "SUSPENDED"
        audit_event = CredentialingAuditLog(
            event_id=f"STATUS-{uuid.uuid4().hex[:12].upper()}",
            clinician_id=target_user.id,
            clinician_email=target_user.email,
            actor_id=current_admin.id,
            actor_username=current_admin.username,
            actor_role=current_admin.role,
            action=action_name,
            verification_method="ADMIN_STATUS_UPDATE",
            evidence_reference=req.reason or "ADMIN_DISCRETION",
            previous_state="ACTIVE" if prev_status else "SUSPENDED",
            new_state="ACTIVE" if req.is_active else "SUSPENDED",
            notes=f"User account status updated by Admin '{current_admin.username}'. Reason: {req.reason}",
            audit_hash=compute_audit_hash(
                patient_id_masked="SYSTEM",
                policy_id="ACCOUNT_STATUS",
                decision=action_name,
                calibrated_confidence=1.0,
                criterion_assessments=[],
                evidence_spans=[],
                timestamp=datetime.now(UTC)
            )
        )
        db.add(audit_event)
        db.commit()

        logger.info(
            f"[ADMIN AUDIT]: User '{target_user.email}' (ID: {target_user.id}) {action_name} "
            f"by Admin '{current_admin.username}'. Reason: {req.reason}"
        )
        return {
            "status": "SUCCESS",
            "user_id": target_user.id,
            "username": target_user.username,
            "is_active": target_user.is_active,
            "message": f"User account has been {action_name.lower()}."
        }

