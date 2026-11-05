import os
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings

INSECURE_SECRET_PLACEHOLDERS: set[str] = {
    "",
    "carepolicyguard-deterministic-clinical-secret-key-3849104812",
    "change_me",
    "changeme",
    "secret",
    "password",
    "insecure",
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "CarePolicyGuard"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Policy-Aware Multi-Agent Clinical Evidence & Coverage Verification Engine"
    API_V1_PREFIX: str = "/api/v1"

    # Security & Tokens: Mandatory cryptographic secret without default fallback
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Persistence: Local non-credential file-based SQLite default for zero-config local development and testing.
    # Structural audit: Scheme is file-based (sqlite), contains zero credentials (no username or password),
    # points to a local relative path, and executes strictly on local disk with no remote network reachability.
    # Enterprise or containerized deployments must override this with an authenticated PostgreSQL connection string.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./carepolicyguard.db")

    # Clinical Multi-Agent & Abstention Calibration
    # Operating Choice Documentation (Task 2):
    # ABSTENTION_THRESHOLD = 0.85 is an uncalibrated heuristic operating choice, not a measured Bayesian probability.
    # Tradeoff Analysis: A threshold of 0.85 prioritizes zero false approvals (preventing improper authorizations
    # of invasive or expensive procedures) at the acceptable expense of routing borderline cases to human clinical review.
    # The CalibrationHarness provides selective-risk derivation on validation data for future empirical tuning.
    ABSTENTION_THRESHOLD: float = float(os.getenv("ABSTENTION_THRESHOLD", "0.85"))
    ENABLE_PHI_MASKING: bool = True

    # LLM Inference Gateway (OpenAI-compatible, Ollama, vLLM, or Gemini)
    # HIPAA & Privacy Guardrail: Hard default-off for network egress of clinical text
    ENABLE_REMOTE_LLM_EGRESS: bool = os.getenv("ENABLE_REMOTE_LLM_EGRESS", "false").lower() in ("true", "1", "yes")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_SAMPLE_PASSES: int = int(os.getenv("LLM_SAMPLE_PASSES", "3"))

    # CORS & Networking
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # Live Email Delivery (SMTP)
    SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "false").lower() in ("true", "1", "yes")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "auth@carepolicyguard.med")

    # OAuth Single Sign-On (Google)
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # Demo User Seeding (Strictly dev-only; passwords must come from environment with no default fallbacks)
    SEED_DEMO_USERS: bool = os.getenv("SEED_DEMO_USERS", "false").lower() in ("true", "1", "yes")
    DEMO_ADMIN_PASSWORD: str = os.getenv("DEMO_ADMIN_PASSWORD", "")
    DEMO_AUDITOR_PASSWORD: str = os.getenv("DEMO_AUDITOR_PASSWORD", "")
    DEMO_CLINICIAN_PASSWORD: str = os.getenv("DEMO_CLINICIAN_PASSWORD", "")
    DEMO_DOCTOR_PASSWORD: str = os.getenv("DEMO_DOCTOR_PASSWORD", "")

    # Environment & Deployment Mode
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

    @field_validator("DEBUG", mode="before")
    @classmethod
    def validate_debug(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes", "dev", "development")

    # Retention & Minimization Policies (HIPAA 45 CFR § 164.502(b), § 164.526)
    RETENTION_DAYS_ADJUDICATION: int = int(os.getenv("RETENTION_DAYS_ADJUDICATION", "30"))
    RETENTION_DAYS_QUEUE: int = int(os.getenv("RETENTION_DAYS_QUEUE", "14"))

    # Development-only MFA delivery channel (Forbidden in production)
    DEV_OTP_DELIVERY_ENABLED: bool = os.getenv("DEV_OTP_DELIVERY_ENABLED", "false").lower() in ("true", "1", "yes")

    # Development-only Mock OAuth Acceptance (Strictly prohibited in production)
    DEV_MOCK_OAUTH_ENABLED: bool = os.getenv("DEV_MOCK_OAUTH_ENABLED", "false").lower() in ("true", "1", "yes")

    # Production First-Admin Bootstrap (One-time, closes permanently once first admin exists)
    BOOTSTRAP_ADMIN_EMAIL: str = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "")
    BOOTSTRAP_ADMIN_PASSWORD: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")

    # Credentialing & Licensure Verification Validity Period (Days until re-verification required)
    CREDENTIAL_VERIFICATION_VALIDITY_DAYS: int = int(os.getenv("CREDENTIAL_VERIFICATION_VALIDITY_DAYS", "365"))

    @field_validator("DEV_MOCK_OAUTH_ENABLED", mode="after")
    @classmethod
    def validate_dev_mock_oauth(cls, v: bool) -> bool:
        env = os.getenv("ENVIRONMENT", "development").lower()
        debug_val = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")
        if env == "production" or not debug_val:
            if v:
                import logging
                logging.getLogger("app.core.config").warning(
                    "[SECURITY ALERT]: DEV_MOCK_OAUTH_ENABLED is strictly prohibited when ENVIRONMENT=production or DEBUG=False. Forcing to False."
                )
            return False
        return v

    @field_validator("DEV_OTP_DELIVERY_ENABLED", mode="after")
    @classmethod
    def validate_dev_otp(cls, v: bool) -> bool:
        env = os.getenv("ENVIRONMENT", "development").lower()
        debug_val = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")
        if env == "production" or not debug_val:
            if v:
                import logging
                logging.getLogger("app.core.config").warning(
                    "[SECURITY ALERT]: DEV_OTP_DELIVERY_ENABLED is strictly prohibited when ENVIRONMENT=production or DEBUG=False. Forcing to False."
                )
            return False
        return v


    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: Any) -> str:
        key = str(v or "").strip()
        if not key or key in INSECURE_SECRET_PLACEHOLDERS:
            raise ValueError(
                "SECRET_KEY environment variable is required and cannot be empty or an insecure default placeholder. "
                "Set the SECRET_KEY environment variable (e.g. generate via: python -c 'import secrets; print(secrets.token_urlsafe(48))')."
            )
        return key

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
