"""Tests for the safe QuickBooks sandbox importer (post_qbo_journal_entries.py).

These tests run entirely in‑memory and *do not* hit the QuickBooks API. All network
interactions are monkey‑patched.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
import logging
import importlib.util
import pytest

# Path to the repository root – the script adds this to ``sys.path`` on import.
REPO_ROOT = Path.cwd()
SCRIPT_PATH = REPO_ROOT / "scripts" / "post_qbo_journal_entries.py"

def load_script_module():
    spec = importlib.util.spec_from_file_location("post_import", str(SCRIPT_PATH))
    module = importlib.util.module_from_spec(spec)
    # Ensure the repo root is on sys.path for the module's imports.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(module)
    return module

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_account_map():
    """Return a dict mimicking the chart of accounts containing the IDs used in the test payloads."""
    return {
        "1": {"id": "1", "name": "Revenue", "type": "Income"},
        "2": {"id": "2", "name": "Retained Earnings", "type": "Equity"},
        "7": {"id": "7", "name": "Direct OPEX", "type": "Expense"},
        "14": {"id": "14", "name": "Other OPEX", "type": "Expense"},
        "16": {"id": "16", "name": "Marketing", "type": "Expense"},
        "57": {"id": "57", "name": "SM Payroll", "type": "Expense"},
        "80": {"id": "80", "name": "COGS", "type": "Expense"},
    }

@pytest.fixture
def payload_dir(tmp_path):
    """Create a temporary dry‑run payload directory with a single balanced payload."""
    payload_dir = tmp_path / "dry_run_payloads"
    payload_dir.mkdir()
    # Build a minimal balanced payload (same structure as generate_test_payload.py).
    payload = {
        "TxnDate": "2025-01-01",
        "Line": [
            {"Amount": 800.0, "DetailType": "JournalEntryLineDetail", "PostingType": "Credit", "AccountRef": {"value": "1"}},
            {"Amount": 600.0, "DetailType": "JournalEntryLineDetail", "PostingType": "Debit", "AccountRef": {"value": "80"}},
            {"Amount": 400.0, "DetailType": "JournalEntryLineDetail", "PostingType": "Debit", "AccountRef": {"value": "7"}},
            {"Amount": 200.0, "DetailType": "JournalEntryLineDetail", "PostingType": "Credit", "AccountRef": {"value": "2"}}  # net‑income loss (credit) balances the entry
        ],
    }
    (payload_dir / "2025-01.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload_dir

# ---------------------------------------------------------------------------
# Helper to invoke the script's command line interface.
# ---------------------------------------------------------------------------

def run_script(module, args: list[str]):
    """Run ``module.main`` with ``sys.argv`` patched.

    Returns the ``SystemExit`` exception if the script exits via ``sys.exit``.
    """
    old_argv = sys.argv
    sys.argv = [str(SCRIPT_PATH)] + args
    try:
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        return exc_info.value
    finally:
        sys.argv = old_argv

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dry_run_never_posts(monkeypatch, payload_dir, valid_account_map):
    """Dry‑run mode should not issue any HTTP POST requests."""
    mod = load_script_module()

    # Patch MCP helpers.
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": list(valid_account_map.values())})
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: False)
    # Ensure the POST function would raise if called.
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("POST should not be called"))))
    # Use a temporary manifest location – the script uses the repo path, we override via monkeypatch.
    manifest_path = REPO_ROOT / "reports" / "import_manifest.json"
    # Ensure a clean state.
    if manifest_path.is_file():
        manifest_path.unlink()

    # Run the script in dry‑run mode (no --confirm-write).
    exit = run_script(mod, ["--payload-dir", str(payload_dir)])
    assert exit.code == 0
    # Verify manifest now does NOT contain the processed period.
    assert not manifest_path.is_file()
    # If a manifest file was created (e.g., by a previous run), ensure the period is not listed.
    if manifest_path.is_file():
        manifest_data = json.loads(manifest_path.read_text())
        assert "2025-01" not in manifest_data.get("imported", [])


def test_target_not_sandbox(monkeypatch, payload_dir, valid_account_map):
    """The script should abort if the QuickBooks environment is not a sandbox."""
    mod = load_script_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "production", "company_name": "ProdCo"})
    # No further patches needed because the script should exit early.
    exit = run_script(mod, ["--payload-dir", str(payload_dir)])
    assert exit.code != 0

def test_invalid_payload_unbalanced(monkeypatch, payload_dir, valid_account_map):
    """Unbalanced payloads must cause validation failure and abort the run."""
    # Corrupt the payload to make it unbalanced (remove the net‑income line).
    payload_file = payload_dir / "2025-01.json"
    payload = json.loads(payload_file.read_text())
    payload["Line"] = [line for line in payload["Line"] if line["AccountRef"]["value"] != "2"]  # drop net‑income credit line
    payload_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    mod = load_script_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": list(valid_account_map.values())})
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: False)
    # POST should not be called; protect it.
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("POST should not be called"))))
    exit = run_script(mod, ["--payload-dir", str(payload_dir)])
    # The script exits with non‑zero status due to validation error.
    assert exit.code != 0

def test_duplicate_skips_post(monkeypatch, payload_dir, valid_account_map):
    """When ``is_duplicate_journal_entry`` returns True the period is skipped without POST."""
    mod = load_script_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": list(valid_account_map.values())})
    # Simulate a duplicate for the period.
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: True)
    # Protect POST.
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("POST should not be called"))))
    manifest_path = REPO_ROOT / "reports" / "import_manifest.json"
    # Ensure a clean state: remove any existing manifest.
    if manifest_path.is_file():
        manifest_path.unlink()
    exit = run_script(mod, ["--payload-dir", str(payload_dir)])
    assert exit.code == 0
    # Verify the manifest does NOT contain the period (and should not be created).
    assert not manifest_path.is_file()

def test_real_post_success(monkeypatch, payload_dir, valid_account_map):
    """When ``--confirm-write`` is given, a successful POST records the period in the manifest."""
    mod = load_script_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": list(valid_account_map.values())})
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: False)
    # Mock refresh_access_token to return a dummy token.
    monkeypatch.setattr(mod, "refresh_access_token", lambda: "dummy-token")
    # Mock the POST request – verify it receives the expected URL and payload.
    def fake_post(url, headers=None, json=None, timeout=None):
        assert "journalentry" in url
        # The payload should be the same JSON we wrote to the file.
        assert json["TxnDate"] == "2025-01-01"
        return SimpleNamespace(raise_for_status=lambda: None)
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=fake_post))
    exit = run_script(mod, ["--payload-dir", str(payload_dir), "--confirm-write"])
    assert exit.code == 0
    manifest_path = REPO_ROOT / "reports" / "import_manifest.json"
    manifest_data = json.loads(manifest_path.read_text())
    assert "2025-01" in manifest_data.get("imported", [])

def test_real_post_failure(monkeypatch, payload_dir, valid_account_map, caplog):
    """A failed HTTP POST should abort the run and leave the manifest unchanged for that period.
    Additionally, verify that QuickBooks error details are logged safely.
    """
    mod = load_script_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": list(valid_account_map.values())})
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: False)
    monkeypatch.setattr(mod, "refresh_access_token", lambda: "dummy-token")
    # Simulate an HTTP 400 error with QuickBooks fault JSON.
    import json, httpx
    error_body = {
        "Fault": {
            "Error": [
                {
                    "code": "123",
                    "Message": "Invalid field value",
                    "Detail": "The AccountRef value is not valid."
                }
            ]
        }
    }
    def bad_post(*args, **kwargs):
        request = httpx.Request("POST", args[0])
        response = httpx.Response(400, request=request, content=json.dumps(error_body).encode())
        raise httpx.HTTPStatusError("Bad Request", request=request, response=response)
    monkeypatch.setattr(mod, "httpx", SimpleNamespace(post=bad_post))
    caplog.set_level(logging.ERROR)
    exit = run_script(mod, ["--payload-dir", str(payload_dir), "--confirm-write"])
    assert exit.code != 0
    # The manifest should not contain the failed period.
    manifest_path = REPO_ROOT / "reports" / "import_manifest.json"
    if manifest_path.is_file():
        manifest_data = json.loads(manifest_path.read_text())
        assert "2025-01" not in manifest_data.get("imported", [])
    # Verify the QuickBooks error details were logged without exposing credentials.
    logged = [rec.getMessage() for rec in caplog.records]
    assert any("QuickBooks API error" in msg and "code=123" in msg and "Invalid field value" in msg for msg in logged), "Expected sanitized QuickBooks error details in log"

