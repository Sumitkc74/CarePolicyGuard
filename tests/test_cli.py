import pytest
import io
from unittest.mock import patch
from app.cli import main

def test_cli_policies(capsys):
    with patch("sys.argv", ["cli.py", "policies"]):
        main()
    captured = capsys.readouterr().out
    assert "LOADED CMS COVERAGE POLICIES" in captured
    assert "NCD-20.4" in captured

def test_cli_cache_stats(capsys):
    with patch("sys.argv", ["cli.py", "cache-stats"]):
        main()
    captured = capsys.readouterr().out
    assert "IN-MEMORY POLICY CACHE TELEMETRY" in captured
    assert "Total Requests:" in captured

def test_cli_export_audit(tmp_path):
    output_file = tmp_path / "test_audit.csv"
    with patch("sys.argv", ["cli.py", "export-audit", "--output", str(output_file)]):
        main()
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "Event ID,Timestamp (UTC),Case ID" in content

def test_cli_adjudicate_inline(capsys):
    with patch("sys.argv", [
        "cli.py", "adjudicate",
        "--text", "71yo female with ICM post-MI, EF 28%, NYHA II, GDMT > 90d, no shock.",
        "--policy", "NCD-20.4",
        "--tau", "0.80",
        "--no-save"
    ]):
        main()
    captured = capsys.readouterr().out
    assert "Final Determination:" in captured
    assert "NCD-20.4" in captured
    assert "STATUTORY CRITERIA EVALUATION:" in captured

