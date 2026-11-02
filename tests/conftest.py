import os
import secrets

# Construct an ephemeral in-memory test secret for the test suite session.
# Prevents test execution from relying on or persisting any default or repository secret.
if not os.environ.get("SECRET_KEY") or os.environ.get("SECRET_KEY") == "carepolicyguard-deterministic-clinical-secret-key-3849104812":
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)

import pytest
from app.db.session import engine, Base, SessionLocal
from app.db.seed import seed_database

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield

