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
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
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

