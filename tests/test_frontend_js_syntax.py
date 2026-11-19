"""
Frontend JavaScript Syntax & Integrity Gate.

Guards app/static/js/app.js against syntax regressions (e.g. unexpected tokens,
unclosed brackets) and ensures authentication / login-gate handlers remain
defined in JS and wired in the DOM template.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_JS_PATH = PROJECT_ROOT / "app" / "static" / "js" / "app.js"
INDEX_HTML_PATH = PROJECT_ROOT / "app" / "static" / "index.html"


def test_app_js_syntax_validity():
    """Pin a syntax gate: app/static/js/app.js MUST parse cleanly via node --check.

    Fails loudly if node is not installed; never silently skips.
    """
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.fail(
            "Node.js runtime not found on PATH. Frontend JS syntax check is mandatory and cannot be skipped."
        )

    assert APP_JS_PATH.exists(), f"File not found: {APP_JS_PATH}"

    res = subprocess.run(
        [node_bin, "--check", str(APP_JS_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0, (
        f"JavaScript syntax error detected in {APP_JS_PATH}:\n"
        f"STDOUT:\n{res.stdout}\n"
        f"STDERR:\n{res.stderr}"
    )


def test_app_js_syntax_gate_catches_broken_syntax():
    """Proves that node --check actively detects and fails on syntax errors (broken copy test)."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.fail("Node.js runtime not found on PATH.")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("function brokenFunction() { const x = 1; }}\n")
        temp_path = Path(f.name)

    try:
        res = subprocess.run(
            [node_bin, "--check", str(temp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode != 0, "Expected syntax check to fail on broken JavaScript file!"
        assert "SyntaxError" in res.stderr or "Unexpected token" in res.stderr, (
            f"Expected SyntaxError in stderr, got:\n{res.stderr}"
        )
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_frontend_auth_handlers_present_and_wired():
    """Smoke check: verifies login-gate, signin, and registration handlers

    are present in app/static/js/app.js and bound in app/static/index.html.
    """
    assert APP_JS_PATH.exists(), f"Missing {APP_JS_PATH}"
    assert INDEX_HTML_PATH.exists(), f"Missing {INDEX_HTML_PATH}"

    js_content = APP_JS_PATH.read_text(encoding="utf-8")
    html_content = INDEX_HTML_PATH.read_text(encoding="utf-8")

    # 1. Essential authentication functions in app.js
    required_js_symbols = [
        "async function checkSessionOrShowGate",
        "function showLoginGate",
        "function hideLoginGate",
        "function switchLoginMode",
        "async function handleMedicalRegistration",
        "async function handleCustomLogin",
        "async function executeLogin",
    ]
    for sym in required_js_symbols:
        assert sym in js_content, f"Expected '{sym}' defined in app/static/js/app.js"

    # 2. Wire check in index.html
    assert 'onsubmit="handleCustomLogin(event)"' in html_content, (
        "Login form submission handler 'handleCustomLogin' not wired in index.html"
    )
    assert 'onsubmit="handleMedicalRegistration(event)"' in html_content, (
        "Registration form submission handler 'handleMedicalRegistration' not wired in index.html"
    )
    assert 'id="login-gate-screen"' in html_content, (
        "Login gate overlay '#login-gate-screen' not found in index.html"
    )
