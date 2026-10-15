"""Local validation script for QuickBooks account mapping.

This script reads the account mapping from `configs/account_map.json`
and the sandbox chart‑of‑accounts snapshot stored locally at
`data/chart_of_accounts_snapshot.json`. It performs the same checks as
the earlier validation script but avoids any network calls.
"""

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"
CHART_SNAPSHOT_PATH = repo_root / "data" / "chart_of_accounts_snapshot.json"

def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate(account_map: dict, chart: dict) -> list:
    errors = []
    known_ids = {str(a.get("id")) for a in chart.get("accounts", [])}
    # 1. missing IDs
    for key, aid in account_map.items():
        if str(aid) not in known_ids:
            errors.append(f"Mapping key '{key}' references unknown account ID {aid}")
    # 2. duplicate IDs
    id_to_keys = {}
    for key, aid in account_map.items():
        id_to_keys.setdefault(str(aid), []).append(key)
    dup = {aid: ks for aid, ks in id_to_keys.items() if len(ks) > 1}
    if dup:
        dup_msg = ", ".join([f"ID {aid} used for {', '.join(ks)}" for aid, ks in dup.items()])
        errors.append(f"Duplicate account ID usage: {dup_msg}")
    # 3. net_income must be Equity
    net_id = account_map.get("net_income")
    if net_id:
        acct = next((a for a in chart.get("accounts", []) if str(a.get("id")) == str(net_id)), None)
        if acct and acct.get("type") != "Equity":
            errors.append(f"Balancing account ID {net_id} is not an Equity account (type={acct.get('type')})")
    return errors

def main():
    try:
        account_map = load_json(DEFAULT_MAPPING_PATH)
    except Exception as e:
        print(f"ERROR loading account map: {e}")
        sys.exit(1)
    try:
        chart = load_json(CHART_SNAPSHOT_PATH)
    except Exception as e:
        print(f"ERROR loading chart snapshot: {e}")
        sys.exit(1)
    errs = validate(account_map, chart)
    if errs:
        print("Validation FAILED:")
        for e in errs:
            print(f" - {e}")
        sys.exit(2)
    else:
        print("Validation SUCCESS: mapping is consistent with the chart of accounts.")
        sys.exit(0)

if __name__ == "__main__":
    main()
