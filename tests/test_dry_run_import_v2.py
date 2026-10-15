"""Tests for the dry‑run importer script `dry_run_import_v2.py`.

These tests verify that the script runs without raising an exception, produces an HTML report,
and (given the current workbook data) does **not** generate any JSON payload files because all
periods result in unbalanced entries (as expected without an automatic net‑income balancing line).
"""

import pathlib
import subprocess
import sys

def test_dry_run_import_v2_generates_html_and_no_payloads(tmp_path, monkeypatch):
    # Ensure the script runs in the repository root.
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    # Run the script.
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "dry_run_import_v2.py"),
         "data/input/ABC Inc - Financial Statements.xlsx"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=300,
    )
    # The script should exit cleanly (returncode 0).
    assert result.returncode == 0, f"Script failed: {result.stderr}";
    # Verify the HTML report was created.
    html_path = repo_root / "reports" / "dry_run_import_v2.html"
    assert html_path.is_file(), "HTML report not found"
    # Verify that the payload directory exists but contains no JSON files (all periods errored).
    payload_dir = repo_root / "reports" / "dry_run_payloads"
    # Verify that payloads were generated for each period.
    json_files = list(payload_dir.glob("*.json"))
    assert payload_dir.is_dir(), "Payload directory not created"
    expected_count = 18  # number of periods in the test workbook
    assert len(json_files) == expected_count, f"Expected {expected_count} payload files, found {[p.name for p in json_files]}"
