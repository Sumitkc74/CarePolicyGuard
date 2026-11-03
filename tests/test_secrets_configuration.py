"""
Secrets and Configuration Security Verification Tests.

Proves:
1. SECRET_KEY is required and startup/Settings fail fast if unset or placeholder.
2. Dynamic test secrets constructed in-memory succeed without persisting credentials.
3. docker-compose.yml enforces required environment variables without default fallbacks.
4. .dockerignore excludes .git, held-out benchmarks, databases, and sensitive artifacts.
"""

import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_SECRET_PLACEHOLDERS, Settings


def test_settings_fails_fast_when_secret_key_empty():
    """
    Verifies that Settings refuses to instantiate when SECRET_KEY is empty,
    failing fast with an explicit error naming SECRET_KEY.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, SECRET_KEY="")

    error_str = str(exc_info.value)
    assert "SECRET_KEY" in error_str
    assert "required" in error_str.lower() or "cannot be empty" in error_str.lower()


def test_settings_fails_fast_when_secret_key_is_known_insecure_placeholder():
    """
    Verifies that known documentation placeholders are rejected fail-fast.
    """
    for placeholder in INSECURE_SECRET_PLACEHOLDERS:
        if not placeholder:
            continue
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, SECRET_KEY=placeholder)
        error_str = str(exc_info.value)
        assert "SECRET_KEY" in error_str


def test_settings_proceeds_with_dynamic_in_memory_test_secret():
    """
    Verifies that an authentic test secret constructed in-memory proceeds cleanly.
    Never stores or commits secrets to disk.
    """
    ephemeral_test_secret = secrets.token_urlsafe(32)
    cfg = Settings(_env_file=None, SECRET_KEY=ephemeral_test_secret)
    assert cfg.SECRET_KEY == ephemeral_test_secret


def test_docker_compose_requires_secrets_without_default_fallbacks():
    """
    Verifies that docker-compose.yml uses required variable expansion ${VAR:?message}
    for SECRET_KEY and POSTGRES_PASSWORD, with no plaintext fallback defaults.
    """
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml not found"

    content = compose_path.read_text(encoding="utf-8")

    # 1. SECRET_KEY must use ${SECRET_KEY:?...} required syntax
    secret_key_match = re.search(r'\$\{SECRET_KEY:\?([^}]+)\}', content)
    assert secret_key_match is not None, "SECRET_KEY must be enforced via ${SECRET_KEY:?message}"
    assert "SECRET_KEY" in secret_key_match.group(0)

    # 2. POSTGRES_PASSWORD must use ${POSTGRES_PASSWORD:?...} required syntax
    postgres_pass_match = re.search(r'\$\{POSTGRES_PASSWORD:\?([^}]+)\}', content)
    assert postgres_pass_match is not None, "POSTGRES_PASSWORD must be enforced via ${POSTGRES_PASSWORD:?message}"

    # 3. Ensure no default fallback patterns exist for credentials
    assert "careguard_secure_pass" not in content, "Found plaintext default database password in compose"
    assert "carepolicyguard-deterministic-clinical-secret-key" not in content, "Found plaintext default SECRET_KEY in compose"

    # 4. Ensure no ${SECRET_KEY:-...} fallback pattern exists
    assert not re.search(r'\$\{SECRET_KEY:-', content), "SECRET_KEY must not have a fallback default"


def test_dockerignore_excludes_git_and_sensitive_directories():
    """
    Verifies that .dockerignore excludes repository metadata (.git),
    held-out datasets, environment files, local databases, and caches.
    """
    dockerignore_path = Path(__file__).resolve().parent.parent / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore not found"

    lines = [
        line.strip()
        for line in dockerignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    # Required exclusions
    assert any(".git" in line for line in lines), ".dockerignore must exclude .git"
    assert any(".env" in line for line in lines), ".dockerignore must exclude .env"
    assert any("carepolicyguard-heldout" in line for line in lines), ".dockerignore must exclude carepolicyguard-heldout"
    assert any(".pytest_cache" in line for line in lines), ".dockerignore must exclude .pytest_cache"
    assert any("*.db" in line or "carepolicyguard.db" in line for line in lines), ".dockerignore must exclude databases"


def test_database_url_default_is_local_non_credential():
    """
    Verifies structurally that the default DATABASE_URL contains zero embedded credentials
    (username and password must be None), uses a local file-based scheme (sqlite),
    and targets no remote network host.
    Does not print or hardcode any connection string value.
    """
    ephemeral_test_secret = secrets.token_urlsafe(32)
    cfg = Settings(_env_file=None, SECRET_KEY=ephemeral_test_secret)

    parsed = urlsplit(cfg.DATABASE_URL)
    # 1. Must be local file-based database scheme
    assert parsed.scheme == "sqlite"

    # 2. Must contain no username or password credentials
    assert parsed.username is None
    assert parsed.password is None

    # 3. Must not target a remote host or network socket
    assert parsed.hostname is None or parsed.hostname == ""
    assert parsed.port is None


def test_env_example_matches_live_config_and_demo_seeding():
    """
    Task 5 Consistency Test:
    Proves:
    1. Every variable named in .env.example is an active field in Settings.
    2. Every demo-seeding variable that Settings reads appears in .env.example.
    3. All demo password and secret keys are empty in .env.example (zero stored secrets).
    4. The comment names SEED_DEMO_USERS and explicitly notes development-only scope.
    """
    env_example_path = Path(__file__).resolve().parent.parent / ".env.example"
    assert env_example_path.exists(), ".env.example not found"

    content = env_example_path.read_text(encoding="utf-8")
    var_lines = [
        line.strip() for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    ]

    example_vars = {line.split("=")[0].strip(): line.split("=", 1)[1].strip() for line in var_lines}
    settings_fields = set(Settings.model_fields.keys())

    # 1. Every variable in .env.example is recognized by Settings
    for var in example_vars:
        assert var in settings_fields, f"Variable '{var}' in .env.example is not read by Settings"

    # 2. Every demo-seeding variable in Settings appears in .env.example
    expected_demo_vars = {
        "SEED_DEMO_USERS",
        "DEMO_ADMIN_PASSWORD",
        "DEMO_AUDITOR_PASSWORD",
        "DEMO_CLINICIAN_PASSWORD",
        "DEMO_DOCTOR_PASSWORD"
    }
    for demo_var in expected_demo_vars:
        assert demo_var in example_vars, f"Demo seeding variable '{demo_var}' is missing from .env.example"

    # 3. All password/secret values in .env.example are empty strings
    for sec_key in ["SECRET_KEY", "DEMO_ADMIN_PASSWORD", "DEMO_AUDITOR_PASSWORD", "DEMO_CLINICIAN_PASSWORD", "DEMO_DOCTOR_PASSWORD", "SMTP_PASSWORD", "GOOGLE_CLIENT_SECRET"]:
        if sec_key in example_vars:
            assert example_vars[sec_key] == "", f"Security violation: {sec_key} in .env.example must be empty"

    # 4. Comment specifies SEED_DEMO_USERS and development-only
    assert "SEED_DEMO_USERS" in content
    assert "development" in content.lower() or "dev-only" in content.lower()


