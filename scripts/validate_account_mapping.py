"""Validation script for QuickBooks account mappings.

This script performs **validation‑only** checks on `configs/account_map.json`
against the sandbox chart of accounts. It reports:

* Missing or unknown account IDs
* Duplicate account IDs used for different logical keys
* Whether the `net_income` balancing account (if present) is an Equity account

The script does **not** generate any journal‑entry payloads and does not
interact with QuickBooks beyond retrieving the read‑only chart of accounts.

Run it with:
    python scripts/validate_account_mapping.py
"""

import json
from pathlib import Path

# Project imports – repo root is two levels up from this file.
repo_root = Path(__file__).resolve().parents[1]
# Load chart of accounts from a local snapshot to avoid remote calls.
CHART_SNAPSHOT_PATH = repo_root / "data" / "chart_of_accounts_snapshot.json"

DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"

def load_account_map(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Account mapping file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_account_map(account_map: dict, chart: dict):
    errors = []
    # Build a set of known IDs from chart
    known_ids = {str(acct.get("id")) for acct in chart.get("accounts", [])}
    # 1. Verify every mapped ID exists
    for key, acct_id in account_map.items():
        if str(acct_id) not in known_ids:
            errors.append(f"Mapping key '{key}' references unknown account ID {acct_id}")
    # 2. Detect duplicate IDs across different keys
    id_to_keys = {}
    for key, acct_id in account_map.items():
        id_to_keys.setdefault(str(acct_id), []).append(key)
    duplicates = {aid: ks for aid, ks in id_to_keys.items() if len(ks) > 1}
    if duplicates:
        dup_msg = ", ".join([f"ID {aid} used for {', '.join(ks)}" for aid, ks in duplicates.items()])
        errors.append(f"Duplicate account ID usage: {dup_msg}")
    # 3. Verify net_income (balancing) account is Equity, if present
    net_id = account_map.get("net_income")
    if net_id:
        acct = next((a for a in chart.get("accounts", []) if str(a.get("id")) == str(net_id)), None)
        if acct and acct.get("type") != "Equity":
            errors.append(f"Balancing account ID {net_id} is not an Equity account (type={acct.get('type')})")
    return errors

def main():
    mapping_path = DEFAULT_MAPPING_PATH
    try:
        account_map = load_account_map(mapping_path)
    except Exception as e:
        print(f"ERROR loading account map: {e}")
        sys.exit(1)
    try:
        chart = list_chart_of_accounts_dict()
    except Exception as e:
        print(f"ERROR retrieving chart of accounts: {e}")
        sys.exit(1)
    errors = validate_account_map(account_map, chart)
    if errors:
        print("Validation FAILED with the following issues:")
        for err in errors:
            print(f" - {err}")
        sys.exit(2)
    else:
        print("Validation SUCCESS: account mapping is consistent with the chart of accounts.")
        sys.exit(0)

if __name__ == "__main__":
    main()
