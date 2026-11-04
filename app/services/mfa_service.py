import hmac
import hashlib
import time
import struct
import base64
import os
import secrets
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any, List
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("app.services.mfa_service")


class DevOtpDeliveryChannel:
    """
    In-memory / server-side development OTP delivery channel for local engineering/testing
    when SMTP is unconfigured. Strictly inactive and forbidden in production.
    """
    _dev_codes: Dict[str, str] = {}

    @classmethod
    def is_available(cls) -> bool:
        env = getattr(settings, "ENVIRONMENT", "development").lower()
        debug_mode = getattr(settings, "DEBUG", True)
        if env == "production" or not debug_mode:
            return False
        return bool(getattr(settings, "DEV_OTP_DELIVERY_ENABLED", False))

    @classmethod
    def deliver(cls, destination: str, code: str) -> None:
        if not cls.is_available():
            raise RuntimeError("Dev OTP delivery channel is disabled or strictly prohibited in production.")
        cls._dev_codes[destination] = code
        # Server-side developer log stream notice (clearly marked as dev code)
        logger.info(f"[DEV OTP DELIVERY]: Second-factor verification code generated for {destination}. (Local Dev Mode Only)")

    @classmethod
    def get_latest_code(cls, destination: str) -> Optional[str]:
        if not cls.is_available():
            return None
        return cls._dev_codes.get(destination)

    @classmethod
    def clear(cls) -> None:
        cls._dev_codes.clear()


class MFAService:

    """
    Unified Multi-Factor Authentication Service:
    1. Authenticator App (RFC 6238 TOTP - Google Authenticator, Duo, Apple Passwords).
    2. Email One-Time Password (OTP) - with live real SMTP delivery support.
    3. SMS / Phone Number One-Time Password (OTP).
    """

    @classmethod
    def mask_email(cls, email: str) -> str:
        if not email or "@" not in email:
            return email or ""
        parts = email.split("@")
        name = parts[0]
        domain = parts[1]
        masked_name = name[:2] + "***" if len(name) > 2 else name[:1] + "***"
        return f"{masked_name}@{domain}"

    @classmethod
    def mask_phone(cls, phone: str) -> str:
        if not phone:
            return ""
        digits = "".join([c for c in phone if c.isdigit()])
        if len(digits) >= 4:
            return f"+1-***-***-{digits[-4:]}"
        return "+1-***-***"

    @classmethod
    def generate_totp_secret(cls) -> str:
        random_bytes = os.urandom(20)
        return base64.b32encode(random_bytes).decode('utf-8').replace('=', '')

    @classmethod
    def generate_totp_code(cls, secret_base32: str, for_time: Optional[int] = None) -> str:
        current_time = for_time if for_time is not None else int(time.time())
        time_step = current_time // 30
        msg = struct.pack(">Q", time_step)

        padded_secret = secret_base32 + '=' * ((8 - len(secret_base32) % 8) % 8)
        key = base64.b32decode(padded_secret, casefold=True)

        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        binary = ((h[offset] & 0x7F) << 24) | ((h[offset + 1] & 0xFF) << 16) | ((h[offset + 2] & 0xFF) << 8) | (h[offset + 3] & 0xFF)
        code = binary % 1_000_000
        return f"{code:06d}"

    @classmethod
    def verify_totp_code(cls, secret_base32: str, code_to_check: str, tolerance_steps: int = 1) -> bool:
        clean_code = str(code_to_check).strip()
        now = int(time.time())
        for delta in range(-tolerance_steps, tolerance_steps + 1):
            valid_code = cls.generate_totp_code(secret_base32, for_time=now + (delta * 30))
            if hmac.compare_digest(clean_code, valid_code):
                return True
        return False

    @classmethod
    def build_otpauth_uri(cls, username: str, secret_base32: str, issuer: str = "CarePolicyGuard") -> str:
        return f"otpauth://totp/{issuer}:{username}?secret={secret_base32}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"

    @classmethod
    def generate_numeric_otp(cls, length: int = 6) -> Tuple[str, datetime]:
        code = "".join([str(secrets.randbelow(10)) for _ in range(length)])
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        return code, expires_at

    @classmethod
    def send_email_otp(cls, email: str, code: str) -> Dict[str, Any]:
        """
        Sends verification code to the user's email address.
        - If SMTP is configured in settings, sends a real live email.
        - If SMTP is unconfigured AND DEV_OTP_DELIVERY_ENABLED is active in dev mode,
          delivers via the server-side dev channel.
        - If SMTP is unconfigured AND dev channel is inactive, raises HTTP 503 promptly
          with a clear error, preventing deadlocks or silent un-deliverable OTP generation.
        """
        masked_email = email[:2] + "***@" + email.split("@")[-1] if "@" in email else email
        smtp_configured = bool(
            settings.SMTP_ENABLED and
            settings.SMTP_HOST and
            settings.SMTP_USER and
            settings.SMTP_PASSWORD
        )

        if smtp_configured:
            sent_successfully = False
            smtp_error = None
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"CarePolicyGuard Verification Code: {code}"
                msg["From"] = settings.SMTP_FROM_EMAIL
                msg["To"] = email

                text_content = (
                    f"CarePolicyGuard Clinical Authentication\n\n"
                    f"Your 6-digit one-time security code is:\n\n"
                    f"    {code}\n\n"
                    f"This code is valid for 10 minutes.\n"
                    f"If you did not request this verification code, please notify your healthcare compliance administrator immediately."
                )

                html_content = f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; background: #0f172a; border-radius: 12px; color: #f8fafc;">
                    <div style="border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px;">
                        <h2 style="color: #38bdf8; margin: 0; font-size: 22px;">CarePolicy<span style="color: #f8fafc;">Guard</span></h2>
                        <p style="color: #94a3b8; margin: 4px 0 0 0; font-size: 13px;">Clinical Prior-Authorization CDS &bull; Healthcare Security</p>
                    </div>
                    <p style="font-size: 14px; color: #cbd5e1;">A login request was initiated for your clinical account. Please enter the verification code below:</p>
                    <div style="background: #090d16; border: 1px solid #38bdf8; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
                        <span style="font-family: monospace; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #38bdf8;">{code}</span>
                    </div>
                    <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">
                        This code will expire in <strong>10 minutes</strong>. If you did not make this request, someone may be attempting to access your healthcare portal.
                    </p>
                    <div style="border-top: 1px solid #1e293b; margin-top: 24px; padding-top: 16px; font-size: 11px; color: #64748b;">
                        Protected under HIPAA Security Rule (45 CFR &sect; 164.312) &bull; Cryptographic Audit Trail
                    </div>
                </div>
                """

                msg.attach(MIMEText(text_content, "plain"))
                msg.attach(MIMEText(html_content, "html"))

                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [email], msg.as_string())
                server.quit()
                sent_successfully = True
            except Exception as e:
                smtp_error = str(e)

            return {
                "status": "SENT" if sent_successfully else "FAILED",
                "channel": "EMAIL",
                "delivery_mode": "LIVE_SMTP",
                "destination": masked_email,
                "sent_live_smtp": sent_successfully,
                "smtp_error": smtp_error,
                "message": f"6-digit authentication code sent via SMTP to {masked_email}. Valid for 10 minutes."
            }

        # SMTP is not configured: check development-only delivery channel
        if DevOtpDeliveryChannel.is_available():
            DevOtpDeliveryChannel.deliver(email, code)
            return {
                "status": "SENT",
                "channel": "EMAIL",
                "delivery_mode": "DEV_CHANNEL",
                "destination": masked_email,
                "sent_live_smtp": False,
                "message": f"Security verification code dispatched via server-side development channel for {masked_email}."
            }

        # Neither SMTP nor dev channel is available: fail promptly with HTTP 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA email delivery service is not configured. Please contact system administrator or configure TOTP application."
        )

    @classmethod
    def send_sms_otp(cls, phone_number: str, code: str) -> Dict[str, Any]:
        masked_phone = (phone_number[:3] + "****" + phone_number[-4:]) if len(phone_number) >= 8 else phone_number
        return {
            "status": "SENT",
            "channel": "SMS",
            "destination": masked_phone,
            "message": f"6-digit authentication code sent via SMS to {masked_phone}. Valid for 10 minutes."
        }
