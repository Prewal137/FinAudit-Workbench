import json
from pathlib import Path

# Load chart of accounts snapshot to obtain valid account IDs.
with open(Path(__file__).resolve().parents[1] / "data" / "chart_of_accounts_snapshot.json", "r", encoding="utf-8") as f:
    coa = json.load(f)
valid_account_ids = {str(acct.get("id")) for acct in coa.get("accounts", [])}

# Import the validation function from the post script.
# The import path assumes the repository root is on sys.path (as in other scripts).
import sys
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
import importlib.util, pathlib, sys
SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "post_qbo_journal_entries.py"
spec = importlib.util.spec_from_file_location("post_import", str(SCRIPT_PATH))
mod = importlib.util.module_from_spec(spec)
sys.path.append(str(SCRIPT_PATH.parent.parent))  # add repo root
spec.loader.exec_module(mod)
validate_payload = mod.validate_payload

payload_dir = repo_root / "reports" / "balanced_payloads"

all_ok = True
for payload_path in sorted(payload_dir.glob("*.json")):
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    try:
        validate_payload(payload, valid_account_ids)
        print(f"{payload_path.name}: VALID")
    except Exception as exc:
        all_ok = False
        print(f"{payload_path.name}: INVALID – {exc}")

if not all_ok:
    raise SystemExit(1)
else:
    print("All payloads validated successfully.")
