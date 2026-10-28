import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.db.session import engine, SessionLocal, Base, get_db
from app.db.seed import seed_database
from app.api.routes import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Create DB schema & seed CMS policies and demo credentials
    print(f"[*] Initializing {settings.PROJECT_NAME} v{settings.VERSION}...")
    Base.metadata.create_all(bind=engine)
    
    # Ensure SQLite columns for User model are present in existing DB files
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(users)"))
            cols = [r[1] for r in res.fetchall()]
            new_cols = [
                ("npi_number", "VARCHAR(20)"),
                ("medical_license", "VARCHAR(50)"),
                ("license_state", "VARCHAR(10)"),
                ("credential_title", "VARCHAR(50)"),
                ("specialty", "VARCHAR(100)"),
                ("organization", "VARCHAR(150)"),
                ("is_verified_medical_pro", "BOOLEAN DEFAULT 0"),
                ("verification_method", "VARCHAR(100)"),
                ("mfa_enabled_methods", "VARCHAR(100) DEFAULT 'email_otp'"),
                ("oauth_provider", "VARCHAR(50)"),
                ("oauth_sub", "VARCHAR(255)")
            ]
            for col_name, col_type in new_cols:
                if cols and col_name not in cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
            conn.commit()
    except Exception as mig_err:
        print(f"[-] SQLite migration notice: {mig_err}")

    db = SessionLocal()
    try:
        seed_database(db)
        print("[+] Database schema verified and Medicare policies pre-seeded successfully.")
    except Exception as e:
        print(f"[-] Database seeding warning: {e}")
    finally:
        db.close()

    yield

    # 2. Shutdown
    print(f"[*] Shutting down {settings.PROJECT_NAME}...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression Middleware (Compresses responses >= 1KB by 70-85%)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# OWASP & HIPAA Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# API Routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Static Files & UI Dashboard
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serves the interactive single-page dashboard."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": f"Welcome to {settings.PROJECT_NAME}. UI index.html not found."}

@app.get("/health", tags=["System"])
def health_check():
    """Microservice liveness and readiness probe."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "tau_threshold": settings.ABSTENTION_THRESHOLD,
        "phi_masking": settings.ENABLE_PHI_MASKING
    }

@app.get("/metrics", tags=["System"], include_in_schema=False)
def root_metrics(db=Depends(get_db)):
    """Root Prometheus scraper alias."""
    from app.api.metrics_routes import get_prometheus_metrics
    return get_prometheus_metrics(db)

@app.get("/metrics/json", tags=["System"], include_in_schema=False)
def root_metrics_json(db=Depends(get_db)):
    """Root operational metrics JSON alias."""
    from app.api.metrics_routes import get_metrics_json
    return get_metrics_json(db)

@app.get("/cds-services", tags=["HL7 Da Vinci CRD"], include_in_schema=False)
def root_cds_discovery():
    """Root HL7 Da Vinci CRD discovery alias."""
    from app.api.cds_hooks_routes import cds_services_discovery
    return cds_services_discovery()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

