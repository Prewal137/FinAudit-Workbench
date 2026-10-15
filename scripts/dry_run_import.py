"""Dry-run import preparation for Excel → QuickBooks.

This script loads a workbook, calculates financial metrics, attempts to build a
QuickBooks JournalEntry payload for each period, and writes a reviewable HTML
artifact summarising the results.

It performs **no** write to QuickBooks – only preparation and validation.  Any
period that cannot be prepared (e.g., missing account mapping, unbalanced entry
without a net_income mapping) is listed as **BLOCKED** with the relevant error.

Usage:
    python scripts/dry_run_import.py <workbook_path>

The resulting artifact is written to ``reports/dry_run_import.html``.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Project imports – paths are relative to the repository root.
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from integrations.qbo_import_preparation import prepare_journal_entry
from integrations.qbo_mcp_server import list_chart_of_accounts_dict

# Optional mapping file – developers should place a JSON file here.
DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"


def load_account_map(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Account mapping file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_html_report(period_entries: dict, errors: dict) -> str:
    # Simple HTML page – no external CSS/JS for portability.
    html = ["<html><head><title>Dry‑run Import Report</title></head><body>"]
    html.append("<h1>Dry‑run Import Preparation Report</h1>")
    html.append(f"<p>Generated on {Path.cwd()}</p>")
    html.append("<hr/>")
    for period, data in period_entries.items():
        html.append(f"<h2>Period {period}</h2>")
        if period in errors:
            html.append(f"<p style='color:red;'><strong>BLOCKED:</strong> {errors[period]}</p>")
            continue
        payload = data["payload"]
        totals = data["totals"]
        html.append("<pre>Payload JSON:\n" + json.dumps(payload, indent=2) + "</pre>")
        html.append(f"<p>Debit total: {totals['debit']:.2f}, Credit total: {totals['credit']:.2f}</p>")
        html.append("<ul>")
        for line in payload.get("Line", []):
            acct = line["AccountRef"]["value"]
            amt = line["Amount"]
            ptype = line["PostingType"]
            html.append(f"<li>{ptype} ${amt:.2f} → Account ID {acct}</li>")
        html.append("</ul>")
    html.append("<hr/>")
    html.append("<h2>Summary of Errors</h2>")
    if errors:
        html.append("<ul>")
        for period, err in errors.items():
            html.append(f"<li>{period}: {err}</li>")
        html.append("</ul>")
    else:
        html.append("<p>No errors – all periods prepared successfully.</p>")
    html.append("</body></html>")
    return "\n".join(html)


def main():
    parser = argparse.ArgumentParser(description="Dry‑run import preparation")
    parser.add_argument("workbook", type=str, help="Path to the Excel workbook")
    parser.add_argument(
        "--mapping",
        type=str,
        default=str(DEFAULT_MAPPING_PATH),
        help="Path to account mapping JSON (default: configs/account_map.json)",
    )
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser().resolve()
    mapping_path = Path(args.mapping).expanduser().resolve()

    # Load account map – if missing we treat this as a blocker for all periods.
    try:
        account_map = load_account_map(mapping_path)
    except Exception as exc:
        print(f"ERROR: Unable to load account mapping: {exc}")
        account_map = None


    try:
        coa_snapshot = list_chart_of_accounts_dict()
    except Exception as exc:
        print(f"ERROR: Unable to retrieve chart of accounts: {exc}")
        coa_snapshot = []
        # Ensure the snapshot is a dict with an "accounts" key for later validation.
        if isinstance(coa_snapshot, list):
            coa_snapshot = {"accounts": coa_snapshot}
        # --------------------------------------------------------------
        # Validate account mapping against chart snapshot (duplicate IDs, unknown IDs, net_income equity)
        validation_errors = []
        # Build known IDs set
        known_ids = {str(a.get("id")) for a in coa_snapshot.get("accounts", [])}
        if account_map is not None:
            for key, aid in account_map.items():
                if str(aid) not in known_ids:
                    validation_errors.append(f"Mapping key '{key}' references unknown account ID {aid}")
            # Duplicate detection
            id_to_keys = {}
            for key, aid in account_map.items():
                id_to_keys.setdefault(str(aid), []).append(key)
            dup = {aid: ks for aid, ks in id_to_keys.items() if len(ks) > 1}
            if dup:
                dup_msg = ", ".join([f"ID {aid} used for {', '.join(ks)}" for aid, ks in dup.items()])
                validation_errors.append(f"Duplicate account ID usage: {dup_msg}")
            # net_income equity check
            net_id = account_map.get("net_income")
            if net_id:
                acct = next((a for a in coa_snapshot.get("accounts", []) if str(a.get("id")) == str(net_id)), None)
                if acct and acct.get("type") != "Equity":
                    validation_errors.append(f"Balancing account ID {net_id} is not an Equity account (type={acct.get('type')})")
        if validation_errors:
            global_validation_error_msg = "; ".join(validation_errors)
        else:
            global_validation_error_msg = None

    # Ingest workbook.
    try:
        is_stmt, bs_stmt = load_financial_workbook(workbook_path)
    except Exception as exc:
        print(f"ERROR: Failed to load workbook: {exc}")
        sys.exit(1)

    # Calculate metrics.
    metrics = calculate_financial_metrics(is_stmt, bs_stmt)
    periods = metrics.get_chronological_periods()

    period_entries = {}
    errors = {}
    for p in periods:
        if global_validation_error_msg:
            errors[p] = global_validation_error_msg
            continue
        mm = metrics.get_monthly(p)
        # Build normalized period dict expected by prepare_journal_entry.
        norm = {
            "period": p,
            "revenue": mm.revenue,
            "cost_of_goods_sold": mm.cogs,
            "direct_opex": mm.direct_opex,
            "sm_payroll": mm.sm_payroll,
            "marketing": mm.marketing,
            "other_opex": mm.other_opex,
        }
        # If there is a net_income value we can include it for balancing.
        if mm.net_income is not None:
            norm["net_income"] = mm.net_income
        # Prepare entry – handle missing mapping or validation errors.
        if account_map is None:
            errors[p] = "Missing account mapping file – cannot prepare payload"
            continue
        try:
            payload = prepare_journal_entry(norm, account_map, chart_of_accounts=coa_snapshot)
            # Compute totals for convenience.
            debit_total = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Debit")
            credit_total = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Credit")
            period_entries[p] = {"payload": payload, "totals": {"debit": debit_total, "credit": credit_total}}
        except Exception as exc:
            errors[p] = str(exc)

    # Write HTML artifact.
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = reports_dir / "dry_run_import.html"
    html_content = build_html_report(period_entries, errors)
    artifact_path.write_text(html_content, encoding="utf-8")
    print(f"Dry-run report written to {artifact_path}")

if __name__ == "__main__":
    main()
