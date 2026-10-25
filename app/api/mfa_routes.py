import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.db.models import User, UserSession
from app.services.mfa_service import MFAService
from app.api.deps import get_current_user

class MFASetupResponse(BaseModel):
    mfa_method: str
    totp_secret: Optional[str] = None
    otpauth_uri: Optional[str] = None
    channel_destination: Optional[str] = None
    message: str
    dev_preview_code: Optional[str] = None

class MFAEnableRequest(BaseModel):
    mfa_method: str = Field(..., description="Method to enable: 'totp_app', 'email_otp', or 'sms_otp'")
    verification_code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    phone_number: Optional[str] = Field(default=None, description="Mobile number for SMS OTP")

class MFAChallengeResponse(BaseModel):
    status: str = "MFA_CHALLENGE_REQUIRED"
    mfa_session_token: str
    mfa_method: str
    destination_masked: Optional[str] = None
    message: str
    dev_preview_code: Optional[str] = None

class MFAVerifyRequest(BaseModel):
    mfa_session_token: str = Field(..., description="Ephemeral token issued by login challenge")
    verification_code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code from App, Email, or SMS")
    mfa_method: Optional[str] = Field(default=None, description="Optional specified MFA method to verify against")

class MFAChallengeMethodRequest(BaseModel):
    mfa_session_token: str = Field(..., description="Active MFA challenge token")
    requested_method: str = Field(..., description="Requested MFA factor: 'totp_app', 'email_otp', or 'sms_otp'")

class MFADisableRequest(BaseModel):
    password: str = Field(..., description="Current password for security re-authentication")

def register_mfa_routes(api_router: APIRouter):

    @api_router.post("/auth/mfa/setup", response_model=MFASetupResponse, summary="Initiate MFA Setup (App, Email, or SMS)")
    def setup_mfa(
        method: str = "totp_app",  # "totp_app", "email_otp", "sms_otp"
        phone: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Initiates Multi-Factor Authentication setup for the active user:
        - 'totp_app': Generates RFC 6238 secret key & otpauth URI for Google/Microsoft Authenticator or Apple Passwords.
        - 'email_otp': Generates and transmits a 6-digit verification code to user's registered clinical email.
        - 'sms_otp': Generates and transmits a 6-digit SMS verification code to user's phone number.
        """
        now = datetime.now(timezone.utc)

        if method == "totp_app":
            secret = MFAService.generate_totp_secret()
            current_user.totp_secret = secret
            db.commit()

            import urllib.parse
            uri = MFAService.build_otpauth_uri(current_user.username, secret)
            # Standard QR code generator URL (can be opened in any browser or scanned directly by phone camera)
            qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(uri)}"
            
            return MFASetupResponse(
                mfa_method="totp_app",
                totp_secret=secret,
                otpauth_uri=uri,
                channel_destination=qr_image_url,
                message="Open your Authenticator app (Google, Microsoft, Duo, or Apple). Tap '+', choose 'Scan QR' or 'Enter Key Manually', enter the secret, and submit the 6-digit code."
            )

        elif method == "email_otp":
            code, expires_at = MFAService.generate_numeric_otp(6)
            current_user.active_otp_code = code
            current_user.otp_expires_at = expires_at
            db.commit()

            dispatch = MFAService.send_email_otp(current_user.email, code)
            return MFASetupResponse(
                mfa_method="email_otp",
                channel_destination=dispatch["destination"],
                message=dispatch["message"],
                dev_preview_code=dispatch.get("dev_preview_code")
            )

        elif method == "sms_otp":
            target_phone = phone or current_user.phone_number
            if not target_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number is required to configure SMS OTP authentication."
                )

            current_user.phone_number = target_phone
            code, expires_at = MFAService.generate_numeric_otp(6)
            current_user.active_otp_code = code
            current_user.otp_expires_at = expires_at
            db.commit()

            dispatch = MFAService.send_sms_otp(target_phone, code)
            return MFASetupResponse(
                mfa_method="sms_otp",
                channel_destination=dispatch["destination"],
                message=dispatch["message"],
                dev_preview_code=dispatch.get("dev_preview_code")
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported MFA method '{method}'. Valid options: 'totp_app', 'email_otp', 'sms_otp'."
            )

    @api_router.post("/auth/mfa/enable", summary="Confirm & Enable MFA Method")
    def enable_mfa(
        req: MFAEnableRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Confirms successful receipt of second-factor token and officially activates MFA on the account.
        """
        now = datetime.now(timezone.utc)

        if req.mfa_method == "totp_app":
            if not current_user.totp_secret:
                raise HTTPException(status_code=400, detail="MFA setup not initialized. Call /auth/mfa/setup first.")
            if not MFAService.verify_totp_code(current_user.totp_secret, req.verification_code):
                raise HTTPException(status_code=401, detail="Invalid Authenticator app code. Check device time sync.")

        elif req.mfa_method in ["email_otp", "sms_otp"]:
            if not current_user.active_otp_code or not current_user.otp_expires_at:
                raise HTTPException(status_code=400, detail="No active OTP code found. Request a new code first.")
            expires = current_user.otp_expires_at if current_user.otp_expires_at.tzinfo else current_user.otp_expires_at.replace(tzinfo=timezone.utc)
            if expires < now:
                raise HTTPException(status_code=401, detail="Verification code has expired. Request a new code.")
            if current_user.active_otp_code != req.verification_code:
                raise HTTPException(status_code=401, detail="Invalid verification code.")

        # Activate MFA on user record and register as enabled method
        current_user.add_mfa_method(req.mfa_method)
        current_user.active_otp_code = None
        current_user.otp_expires_at = None
        db.commit()

        return {
            "status": "MFA_ENABLED",
            "mfa_method": req.mfa_method,
            "enabled_methods": current_user.get_enabled_mfa_methods(),
            "message": f"Multi-Factor Authentication successfully activated via {req.mfa_method}."
        }

    @api_router.get("/auth/mfa/status", summary="Get Current User MFA Configuration Status")
    def get_mfa_status(
        current_user: User = Depends(get_current_user)
    ):
        destination = None
        if current_user.mfa_method == "email_otp":
            destination = MFAService.mask_email(current_user.email)
        elif current_user.mfa_method == "sms_otp" and current_user.phone_number:
            destination = MFAService.mask_phone(current_user.phone_number)
        elif current_user.mfa_method == "totp_app":
            destination = "Google / Microsoft Authenticator App"

        enabled = current_user.get_enabled_mfa_methods()
        primary = current_user.mfa_method or enabled[0]
        return {
            "mfa_enabled": True,
            "mfa_method": primary,
            "primary_method": primary,
            "enabled_methods": enabled,
            "available_options": ["totp_app", "email_otp", "sms_otp"],
            "destination_masked": destination,
            "email": current_user.email,
            "phone_number": current_user.phone_number,
            "totp_configured": bool(current_user.totp_secret),
            "mandatory_mfa": True
        }

    @api_router.post("/auth/mfa/challenge-method", summary="Switch Active MFA Factor During Login")
    def switch_login_mfa_factor(
        req: MFAChallengeMethodRequest,
        db: Session = Depends(get_db)
    ):
        """
        Allows the user to select which enabled MFA factor they want to use to authenticate:
        - If 'email_otp': generates a fresh 6-digit code and dispatches to registered clinical email.
        - If 'sms_otp': generates a fresh 6-digit code and dispatches via SMS.
        - If 'totp_app': prompts for the current Authenticator app code.
        """
        now = datetime.now(timezone.utc)
        try:
            payload = decode_access_token(req.mfa_session_token)
        except Exception:
            raise HTTPException(status_code=401, detail="MFA challenge token has expired or is invalid.")

        if payload.get("type") != "mfa_challenge":
            raise HTTPException(status_code=400, detail="Invalid token type for MFA challenge.")

        user_id = payload.get("uid")
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is inactive or not found.")

        enabled = user.get_enabled_mfa_methods()
        if req.requested_method not in enabled:
            raise HTTPException(
                status_code=400,
                detail=f"MFA method '{req.requested_method}' is not configured for this account. Configured methods: {', '.join(enabled)}"
            )

        dev_code = None
        dest_masked = None
        message = ""

        if req.requested_method == "email_otp":
            code, expires_at = MFAService.generate_numeric_otp(6)
            user.active_otp_code = code
            user.otp_expires_at = expires_at
            db.commit()
            dispatch = MFAService.send_email_otp(user.email, code)
            dev_code = dispatch["dev_preview_code"]
            dest_masked = dispatch["destination"]
            message = f"Security code dispatched to {dest_masked}."

        elif req.requested_method == "sms_otp":
            if not user.phone_number:
                raise HTTPException(status_code=400, detail="No phone number configured for SMS verification.")
            code, expires_at = MFAService.generate_numeric_otp(6)
            user.active_otp_code = code
            user.otp_expires_at = expires_at
            db.commit()
            dispatch = MFAService.send_sms_otp(user.phone_number, code)
            dev_code = dispatch["dev_preview_code"]
            dest_masked = dispatch["destination"]
            message = f"SMS security code dispatched to {dest_masked}."

        elif req.requested_method == "totp_app":
            dest_masked = "Google / Microsoft Authenticator App"
            message = "Open Google Authenticator, Microsoft Authenticator, or Duo and enter the 6-digit code."

        return {
            "status": "CHALLENGE_METHOD_SWITCHED",
            "mfa_method": req.requested_method,
            "destination_masked": dest_masked,
            "message": message,
            "dev_preview_code": dev_code
        }

    @api_router.post("/auth/mfa/remove-method", summary="Remove a Configured MFA Method")
    def remove_mfa_method(
        method: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Removes an MFA method, provided at least one other MFA factor remains active.
        """
        enabled = current_user.get_enabled_mfa_methods()
        if len(enabled) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Compliance Policy Enforcement: Accounts must maintain at least one active MFA factor. You cannot remove your only active verification factor."
            )
        success = current_user.remove_mfa_method(method)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to remove MFA method '{method}'.")
        db.commit()
        return {
            "status": "MFA_METHOD_REMOVED",
            "removed_method": method,
            "enabled_methods": current_user.get_enabled_mfa_methods(),
            "message": f"MFA method '{method}' has been removed."
        }

    @api_router.post("/auth/mfa/disable", summary="Disable Multi-Factor Authentication")
    def disable_mfa(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory Security Policy: Every clinical account must have at least one active Multi-Factor Authentication method enabled (Authenticator App, Email OTP, or SMS OTP). MFA cannot be disabled."
        )

    @api_router.post("/auth/mfa/verify-login", summary="Submit MFA Second Factor to Complete Login")
    def verify_mfa_login(
        req: MFAVerifyRequest,
        request: Request,
        db: Session = Depends(get_db)
    ):
        """
        Validates the second factor (App code, Email code, or SMS code) and issues the final 24-hour JWT token.
        """
        now = datetime.now(timezone.utc)

        # 1. Decode ephemeral challenge token
        try:
            payload = decode_access_token(req.mfa_session_token)
        except Exception:
            raise HTTPException(status_code=401, detail="MFA challenge token has expired or is invalid. Please sign in again.")

        if payload.get("type") != "mfa_challenge":
            raise HTTPException(status_code=400, detail="Invalid token type for MFA verification.")

        user_id = payload.get("uid")
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User account is inactive or not found.")

        # 2. Check code according to specified or enabled MFA methods
        enabled = user.get_enabled_mfa_methods()
        chosen = req.mfa_method or user.mfa_method
        verified = False

        # Check TOTP App if chosen or if user has TOTP enabled
        if (chosen == "totp_app" or not req.mfa_method) and "totp_app" in enabled and user.totp_secret:
            if MFAService.verify_totp_code(user.totp_secret, req.verification_code):
                verified = True

        # Check Email/SMS OTP
        if not verified and user.active_otp_code and user.otp_expires_at:
            expires = user.otp_expires_at if user.otp_expires_at.tzinfo else user.otp_expires_at.replace(tzinfo=timezone.utc)
            if expires >= now and user.active_otp_code == req.verification_code:
                verified = True
                user.active_otp_code = None
                user.otp_expires_at = None

        if not verified:
            raise HTTPException(
                status_code=401,
                detail="Invalid verification code. Please check your chosen MFA method and try again."
            )

        # 3. Create active session and issue final bearer token
        session_id = f"SESS-{uuid.uuid4().hex[:12].upper()}"
        device_header = request.headers.get("User-Agent", "Web / Mobile Device")
        client_ip = request.client.host if request.client else "127.0.0.1"

        new_sess = UserSession(
            session_id=session_id,
            user_id=user.id,
            device_name=device_header[:140],
            ip_address=client_ip
        )
        db.add(new_sess)
        db.commit()

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token = create_access_token(
            data={"sub": user.username, "role": user.role, "uid": user.id, "sid": session_id, "mfa": True},
            expires_delta=access_token_expires
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role,
            "username": user.username,
            "expires_in_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "mfa_verified": True
        }
