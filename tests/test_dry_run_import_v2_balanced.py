import json
import pathlib
import subprocess
import sys

def test_dry_run_balanced_payloads(tmp_path, monkeypatch):
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workbook = repo_root / "data" / "input" / "ABC Inc - Financial Statements.xlsx"
    # Run the dry-run script
    result = subprocess.run([sys.executable, str(repo_root / "scripts" / "dry_run_import_v2.py"), str(workbook)],
                            cwd=str(repo_root), capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    # Verify JSON payloads exist
    payload_dir = repo_root / "reports" / "dry_run_payloads"
    assert payload_dir.is_dir(), "Payload directory not found"
    json_files = list(payload_dir.glob("*.json"))
    assert len(json_files) == 18, f"Expected 18 payloads, found {len(json_files)}"
    # Verify each payload is balanced
    for jf in json_files:
        payload = json.loads(jf.read_text())
        debit = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Debit")
        credit = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Credit")
        assert abs(debit - credit) < 0.01, f"Unbalanced payload {jf.name}: debit {debit} != credit {credit}"
