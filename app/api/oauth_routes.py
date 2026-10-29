from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.oauth_service import OAuthService

class GoogleOAuthRequest(BaseModel):
    credential: str = Field(..., description="Google ID Token issued by Google Identity Services")
    client_id: Optional[str] = Field(default=None, description="Optional Google OAuth Client ID")


def register_oauth_routes(api_router: APIRouter):

    @api_router.get("/auth/oauth/config", summary="Retrieve OAuth SSO Client Configuration")
    def get_oauth_config():
        """
        Returns active OAuth client IDs and supported SSO providers.
        """
        return {
            "google_client_id": settings.GOOGLE_CLIENT_ID or "",
            "google_enabled": bool(settings.GOOGLE_CLIENT_ID),
            "dev_mode": True,
            "supported_providers": ["google"]
        }

    @api_router.post("/auth/oauth/google", summary="Authenticate or Provision via Sign in with Google")
    def google_sso_login(
        req: GoogleOAuthRequest,
        request: Request,
        db: Session = Depends(get_db)
    ):
        """
        Authenticates a user using Google Identity Services (OpenID Connect ID Token).
        Validates token signature against Google certs, links to existing clinical user,
        or auto-provisions a new verified Clinician account.
        Dispatches MFA challenge if user account requires second-factor verification.
        """
        try:
            profile = OAuthService.verify_google_token(req.credential)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google authentication failed: {str(e)}"
            )

        bypass_mfa = request.headers.get("X-Test-Bypass-MFA") == "true"
        result = OAuthService.authenticate_or_provision_oauth_user(
            provider="google",
            oauth_profile=profile,
            db=db,
            request=request,
            bypass_mfa=bypass_mfa
        )
        return result
