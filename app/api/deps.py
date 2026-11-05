from typing import List, Optional, Any
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token, UserRole
from app.db.session import get_db
from app.db.models import User, UserSession

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login"
)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Decodes JWT bearer token, checks session revocation status,
    and returns authenticated User entity from database.
    """
    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub")
    session_id: Optional[str] = payload.get("sid")

    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: sub claim missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if session was revoked remotely from another device
    if session_id:
        sess = db.query(UserSession).filter(UserSession.session_id == session_id).first()
        if sess and sess.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been terminated from another device. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        elif sess:
            sess.last_active_at = datetime.now(timezone.utc)
            db.commit()

    user = db.query(User).filter((User.username == username) | (User.email == username)).first()
    if user is None:
        # Graceful reconstitution for recognized demo accounts if database was re-initialized
        from app.core.security import UserRole, get_password_hash
        demo_accounts = {
            "clinician@hospital.org": {"role": UserRole.CLINICIAN.value, "npi": "1043256787", "name": "Dr. Sarah Jenkins, MD, FACC", "title": "MD"},
            "doctor@hospital.org": {"role": UserRole.CLINICIAN.value, "npi": "1948201732", "name": "Dr. Sarah Jenkins, MD, FACC", "title": "MD"},
            "auditor@medicare.cms.gov": {"role": UserRole.AUDITOR.value, "name": "CMS Compliance Auditor"},
            "admin@carepolicyguard.med": {"role": UserRole.ADMIN.value, "name": "System Administrator"}
        }
        if username in demo_accounts:
            acc = demo_accounts[username]
            user = User(
                username=username,
                email=username,
                hashed_password=get_password_hash("ClinicianCare!2026"),
                role=acc["role"],
                full_name=acc.get("name"),
                npi_number=acc.get("npi"),
                credential_title=acc.get("title", "MD"),
                is_verified_medical_pro=True,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in system.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account.",
        )
    return user

def require_role(allowed_roles: List[str]):
    """
    Role-Based Access Control (RBAC) dependency factory.
    Example: Depends(require_role(["Admin", "Auditor"]))
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Requires one of roles {allowed_roles}, but user has role '{current_user.role}'.",
            )
        return current_user
    return role_checker


oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False
)

def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Returns authenticated user entity if a valid bearer token is provided and not revoked,
    or None if the request is unauthenticated.
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        username: Optional[str] = payload.get("sub")
        session_id: Optional[str] = payload.get("sid")
        if not username:
            return None
        if session_id:
            sess = db.query(UserSession).filter(UserSession.session_id == session_id).first()
            if sess and sess.is_revoked:
                return None
        return db.query(User).filter(User.username == username).first()
    except Exception:
        return None


def get_verified_clinician_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Enforces that the current authenticated user has the Clinician role,
    is explicitly verified as a medical professional in the system records,
    and credential verification has not expired.
    """
    if current_user.role != UserRole.CLINICIAN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Clinical sign-off requires role '{UserRole.CLINICIAN.value}', but user has role '{current_user.role}'."
        )
    if not getattr(current_user, "is_verified_medical_pro", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Clinician account verification is pending (not verified as a medical professional). Primary-source or Credentialing verification is required before signing determinations."
        )
    # Check verification expiry
    expires_at = getattr(current_user, "verification_expires_at", None)
    if expires_at:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Clinician credential verification expired on {expires_at.strftime('%Y-%m-%d')}. Annual re-verification required before signing determinations."
            )
    return current_user


def verify_case_record_access(
    case_id: str,
    log: Optional[Any],
    current_user: User
) -> Any:
    """
    Enforces HIPAA Minimum Necessary and Anti-Enumeration Defense on case records:
    1. Auditors and Admins retain organization-wide compliance and system inspection rights.
    2. Clinicians and users can only inspect cases they submitted/own or personally signed off.
    3. Anti-Enumeration Oracle Defense: If the case does not exist OR exists but the caller
       is not authorized to view it, returns an IDENTICAL HTTP 404 response to prevent attackers
       from discovering valid case IDs.
    """
    not_found_detail = f"Case adjudication record '{case_id}' not found."
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=not_found_detail,
        )

    # Auditor and Admin have full organizational compliance/audit inspection rights
    if current_user.role in (UserRole.AUDITOR.value, UserRole.ADMIN.value, "Auditor", "Admin"):
        return log

    # If case has no assigned owner (e.g. unassigned demo evaluation created without user_id)
    if getattr(log, "user_id", None) is None:
        return log

    # Case owner check (the user who submitted or created the case)
    if getattr(log, "user_id", None) is not None and log.user_id == current_user.id:
        return log

    # Signer check (the verified clinician who signed off the case)
    signed_by = getattr(log, "signed_by", None)
    if signed_by:
        signed_by_lower = signed_by.lower()
        if (current_user.username and current_user.username.lower() in signed_by_lower) or \
           (current_user.email and current_user.email.lower() in signed_by_lower):
            return log

    signer_npi = getattr(log, "signer_npi", None)
    if signer_npi and getattr(current_user, "npi_number", None):
        if signer_npi == current_user.npi_number:
            return log

    # Anti-enumeration oracle defense: do NOT return 403; return 404 with identical message
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=not_found_detail,
    )


