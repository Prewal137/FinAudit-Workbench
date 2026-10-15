import json
import pathlib
import importlib.util
import sys
import pytest

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "post_qbo_journal_entries.py"


def load_module():
    spec = importlib.util.spec_from_file_location("post_import", str(SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.append(str(repo_root))
    spec.loader.exec_module(mod)
    return mod


def run_script(module, args):
    old_argv = sys.argv
    sys.argv = [str(SCRIPT_PATH)] + args
    try:
        with pytest.raises(SystemExit) as exc_info:
            module.main()
        return exc_info.value
    finally:
        sys.argv = old_argv


def test_period_filename_prefix(monkeypatch, tmp_path):
    payload_dir = tmp_path / "payloads"
    payload_dir.mkdir()
    payload = {
        "TxnDate": "2025-01-01",
        "Line": [
            {"Amount": 100.0, "PostingType": "Credit", "AccountRef": {"value": "1"}},
            {"Amount": 100.0, "PostingType": "Debit", "AccountRef": {"value": "2"}}
        ]
    }
    (payload_dir / "payload_2025-01.json").write_text(json.dumps(payload), encoding="utf-8")
    mod = load_module()
    monkeypatch.setattr(mod, "get_company_info", lambda: {"environment": "sandbox", "company_name": "TestCo"})
    monkeypatch.setattr(mod, "list_chart_of_accounts_dict", lambda: {"accounts": [{"id": "1"}, {"id": "2"}]})
    monkeypatch.setattr(mod, "is_duplicate_journal_entry", lambda payload, period: False)
    monkeypatch.setattr(mod, "refresh_access_token", lambda: "dummy-token")
    # Dry‑run (no --confirm-write) should succeed and exit 0
    exit = run_script(mod, ["--payload-dir", str(payload_dir), "--period", "2025-01"])
    assert exit.code == 0
