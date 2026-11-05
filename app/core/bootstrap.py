import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import UserRole, compute_audit_hash, get_password_hash
from app.db.models import CredentialingAuditLog, User

logger = logging.getLogger("app.core.bootstrap")


def is_production_admin_seeded(db: Session) -> bool:
    """
    Checks if at least one legitimate production admin exists in the system.
    Evaluation / demo-seeded accounts (is_demo_user=True) do NOT count as production admins.
    """
    count = db.query(User).filter(
        User.role == UserRole.ADMIN.value,
        User.is_demo_user.is_(False),
    ).count()
    return count > 0


def bootstrap_production_admin(
    db: Session,
    email: str,
    password: str,
    full_name: str | None = None
) -> User:
    """
    One-time production first-admin bootstrap.
    Executed strictly via operator CLI or deployment environment variables,
    never via the public registration endpoint.

    Security constraints:
    - Permanently closes once the first production admin exists (future attempts rejected and logged).
    - Forces password change (must_change_password=True) on first login.
    - Forces MFA setup (must_setup_mfa=True) on first login.
    - Tagged as is_bootstrap=True, is_demo_user=False.
    """
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Invalid administrator email address provided for bootstrap.")

    if len(password) < 12:
        raise ValueError("Bootstrap administrator password must be at least 12 characters.")

    # Check if a production admin already exists
    if is_production_admin_seeded(db):
        logger.warning(
            f"[SECURITY AUDIT]: Attempted production bootstrap admin creation for '{clean_email}' "
            f"REJECTED. Production administrator already exists; bootstrap path is permanently closed."
        )
        raise RuntimeError("Production admin already exists. Bootstrap path is permanently closed.")

    # Check if a user with this email exists
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        if existing.is_demo_user:
            raise RuntimeError(
                f"Cannot bootstrap production admin on demo account '{clean_email}'. "
                f"Demo accounts are strictly segregated from production."
            )
        raise RuntimeError(f"User with email '{clean_email}' already exists in system.")

    bootstrap_admin = User(
        username=clean_email,
        email=clean_email,
        full_name=full_name or "System Administrator (Bootstrap)",
        hashed_password=get_password_hash(password),
        role=UserRole.ADMIN.value,
        is_active=True,
        is_bootstrap=True,
        is_demo_user=False,
        must_change_password=True,
        must_setup_mfa=True,
        mfa_enabled=True,
        mfa_method="email_otp",
        mfa_enabled_methods="email_otp",
        provisioned_by="OPERATOR_CLI_BOOTSTRAP"
    )
    db.add(bootstrap_admin)
    db.commit()
    db.refresh(bootstrap_admin)

    # Log immutable audit event for bootstrap creation
    audit_event = CredentialingAuditLog(
        event_id=f"BOOTSTRAP-{uuid.uuid4().hex[:12].upper()}",
        clinician_id=bootstrap_admin.id,
        clinician_email=bootstrap_admin.email,
        actor_id=None,
        actor_username="SYSTEM_OPERATOR",
        actor_role="BOOTSTRAP",
        action="PROVISIONED",
        verification_method="OPERATOR_BOOTSTRAP",
        evidence_reference="SYSTEM_BOOTSTRAP_CLI",
        previous_state=None,
        new_state="ACTIVE_ADMIN",
        notes="First production administrator bootstrapped by deployment operator. Forced password change and MFA setup required on first login.",
        audit_hash=compute_audit_hash(
            patient_id_masked="SYSTEM",
            policy_id="BOOTSTRAP",
            decision="ADMIN_PROVISIONED",
            calibrated_confidence=1.0,
            criterion_assessments=[],
            evidence_spans=[],
            timestamp=datetime.now(UTC)
        )
    )
    db.add(audit_event)
    db.commit()

    logger.info(
        f"[SECURITY NOTICE]: Production bootstrap admin created successfully for '{clean_email}'. "
        f"Forced password change and MFA setup enforced on first login. Bootstrap path is now CLOSED."
    )
    return bootstrap_admin


def audit_self_registered_admins(db: Session) -> list[dict[str, Any]]:
    """
    Scans the database for unverified or legacy self-registered Admin accounts.
    Legitimate admins:
    - is_bootstrap == True (bootstrapped by operator)
    - is_demo_user == True (evaluation demo seed)
    - provisioned_by is not None (created by an authorized existing Admin)

    Any Admin account that lacks these credentials was self-registered via the open endpoint.
    Actions: Flags and suspends (is_active=False) the account, logging an audit notice.
    """
    flagged: list[dict[str, Any]] = []
    admins = db.query(User).filter(User.role == UserRole.ADMIN.value).all()

    for adm in admins:
        is_legit = (
            adm.is_bootstrap
            or adm.is_demo_user
            or (adm.provisioned_by and adm.provisioned_by.strip())
        )
        if not is_legit:
            logger.warning(
                f"[SECURITY ALERT]: Legacy self-registered admin account detected: '{adm.email}'. "
                f"Suspicious unauthenticated creation without bootstrap or admin provisioning. "
                f"Suspending account (is_active=False) pending manual operator security review."
            )
            adm.is_active = False
            flagged.append({
                "id": adm.id,
                "email": adm.email,
                "status": "SUSPENDED",
                "action_required": "Operator review and explicit re-provisioning or deletion required."
            })
    if flagged:
        db.commit()
    return flagged


def migrate_legacy_unverified_clinicians(db: Session) -> list[dict[str, Any]]:
    """
    Scans existing Clinician accounts and downgrades any account that was 'verified'
    purely via format checks (FORMAT_CHECK_ONLY / NPPES_CMS_LUHN_VERIFIED) or OAuth auto-verification.
    No grandfathering: all such accounts are downgraded to unverified (is_verified_medical_pro=False)
    with an operator log notice explaining re-verification is required.
    """
    downgraded: list[dict[str, Any]] = []
    clinicians = db.query(User).filter(
        User.role == UserRole.CLINICIAN.value,
        User.is_demo_user.is_(False),
        User.is_verified_medical_pro.is_(True)
    ).all()

    for c in clinicians:
        method = c.verification_method or ""
        is_legacy = (
            method in ("NPPES_CMS_LUHN_VERIFIED", "FORMAT_CHECK_ONLY", "NPPES_LUHN_ONLY")
            or method.startswith("OAUTH_")
            or not method
        )
        if is_legacy:
            logger.warning(
                f"[SECURITY NOTICE]: Clinician account '{c.email}' was verified only via "
                f"self-asserted format check or OAuth auto-verification ('{method}'). "
                f"Downgrading to UNVERIFIED (pending). Primary-source NPPES or Credentialing verification required."
            )
            c.is_verified_medical_pro = False
            c.verification_method = "FORMAT_CHECK_ONLY"

            # Record audit log
            audit_event = CredentialingAuditLog(
                event_id=f"DOWNGRADE-{uuid.uuid4().hex[:12].upper()}",
                clinician_id=c.id,
                clinician_email=c.email,
                actor_id=None,
                actor_username="SYSTEM_MIGRATION",
                actor_role="SECURITY_MIGRATION",
                action="DOWNGRADED",
                verification_method="FORMAT_CHECK_ONLY",
                evidence_reference=method,
                previous_state="VERIFIED",
                new_state="UNVERIFIED",
                notes="Downgraded by Task 4 security migration. Legacy format check or OAuth auto-verification is insufficient. Re-verification required.",
                audit_hash=compute_audit_hash(
                    patient_id_masked="SYSTEM",
                    policy_id="DOWNGRADE",
                    decision="DOWNGRADED",
                    calibrated_confidence=1.0,
                    criterion_assessments=[],
                    evidence_spans=[],
                    timestamp=datetime.now(UTC)
                )
            )
            db.add(audit_event)
            downgraded.append({
                "id": c.id,
                "email": c.email,
                "previous_method": method,
                "new_state": "UNVERIFIED"
            })

    if downgraded:
        db.commit()
    return downgraded
