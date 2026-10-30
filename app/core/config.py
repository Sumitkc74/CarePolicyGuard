import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "CarePolicyGuard"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Policy-Aware Multi-Agent Clinical Evidence & Coverage Verification Engine"
    API_V1_PREFIX: str = "/api/v1"
    
    # Security & Tokens
    SECRET_KEY: str = os.getenv("SECRET_KEY", "carepolicyguard-deterministic-clinical-secret-key-3849104812")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # Persistence
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./carepolicyguard.db")
    
    # Clinical Multi-Agent & Abstention Calibration
    ABSTENTION_THRESHOLD: float = float(os.getenv("ABSTENTION_THRESHOLD", "0.85"))
    ENABLE_PHI_MASKING: bool = True
    
    # LLM Inference Gateway (OpenAI-compatible, Ollama, vLLM, or Gemini)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_SAMPLE_PASSES: int = int(os.getenv("LLM_SAMPLE_PASSES", "3"))
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
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

    # Default Demo Credentials
    DEFAULT_ADMIN_USER: str = "admin@carepolicyguard.med"
    DEFAULT_ADMIN_PASS: str = "AdminGuard!2026"
    DEFAULT_AUDITOR_USER: str = "auditor@medicare.cms.gov"
    DEFAULT_AUDITOR_PASS: str = "AuditorSecure!2026"
    DEFAULT_CLINICIAN_USER: str = "clinician@hospital.org"
    DEFAULT_CLINICIAN_PASS: str = "ClinicianCare!2026"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

settings = Settings()

