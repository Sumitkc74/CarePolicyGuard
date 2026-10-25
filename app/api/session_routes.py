import uuid
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserSession
from app.api.deps import get_current_user

class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    device_name: str
    ip_address: Optional[str]
    is_current: bool
    is_revoked: bool
    created_at: datetime
    last_active_at: datetime

class RevokeSessionResponse(BaseModel):
    status: str
    message: str
    revoked_session_id: str

def register_session_management_routes(api_router: APIRouter):
    @api_router.get("/auth/sessions", response_model=List[SessionOut], summary="List Active Device Sessions")
    def list_user_sessions(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Lists all active devices and sessions where this clinical account is currently logged in.
        Includes indicators for the current active device versus remote devices.
        """
        # Determine current session ID from bearer token
        auth_header = request.headers.get("Authorization", "")
        current_sid = None
        if auth_header.startswith("Bearer "):
            from app.core.security import decode_access_token
            try:
                payload = decode_access_token(auth_header.split(" ")[1])
                current_sid = payload.get("sid")
            except Exception:
                pass

        sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == current_user.id)
            .order_by(UserSession.last_active_at.desc())
            .all()
        )

        out = []
        for s in sessions:
            out.append(SessionOut(
                session_id=s.session_id,
                device_name=s.device_name,
                ip_address=s.ip_address,
                is_current=(s.session_id == current_sid),
                is_revoked=s.is_revoked,
                created_at=s.created_at,
                last_active_at=s.last_active_at
            ))
        return out

    @api_router.post("/auth/sessions/{session_id}/revoke", response_model=RevokeSessionResponse, summary="Remotely Revoke Device Session")
    def revoke_session(
        session_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Remotely terminates and revokes login access on another device.
        Subsequent requests from that device will immediately be rejected with 401 Unauthorized.
        """
        sess = (
            db.query(UserSession)
            .filter(UserSession.session_id == session_id, UserSession.user_id == current_user.id)
            .first()
        )
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device session '{session_id}' not found for current user."
            )

        sess.is_revoked = True
        sess.revoked_at = datetime.now(timezone.utc)
        db.commit()

        return RevokeSessionResponse(
            status="SUCCESS_REVOKED",
            message=f"Session on '{sess.device_name}' has been remotely revoked. Device has been logged out.",
            revoked_session_id=session_id
        )

    @api_router.post("/auth/sessions/revoke-all-others", response_model=RevokeSessionResponse, summary="Log Out All Other Devices")
    def revoke_all_other_sessions(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Emergency Security Action: Remotely terminates all other device logins except the current active device.
        """
        auth_header = request.headers.get("Authorization", "")
        current_sid = None
        if auth_header.startswith("Bearer "):
            from app.core.security import decode_access_token
            try:
                payload = decode_access_token(auth_header.split(" ")[1])
                current_sid = payload.get("sid")
            except Exception:
                pass

        other_sessions = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == current_user.id,
                UserSession.session_id != current_sid,
                UserSession.is_revoked == False
            )
            .all()
        )

        now = datetime.now(timezone.utc)
        for s in other_sessions:
            s.is_revoked = True
            s.revoked_at = now

        db.commit()

        return RevokeSessionResponse(
            status="SUCCESS_REVOKED_ALL",
            message=f"Successfully terminated {len(other_sessions)} other active device session(s).",
            revoked_session_id="ALL_OTHERS"
        )

