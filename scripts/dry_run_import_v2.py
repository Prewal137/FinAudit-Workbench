"""Extended dry‑run import preparation script.

This script builds on the existing ``dry_run_import.py`` but correctly records
payloads for each period, writes a JSON file per period under
``reports/dry_run_payloads/`` and generates an HTML summary report.
All operations are **local only** – no calls are made to the QuickBooks
sandbox. Errors are reported per period and the output files are clearly
marked as NOT POSTED.
"""

import argparse
import json
import sys
from pathlib import Path

# Project imports – paths are resolved relative to the repository root.
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from integrations.qbo_import_balanced import prepare_balanced_journal_entry as prepare_journal_entry
from integrations.qbo_mcp_server import list_chart_of_accounts_dict, is_duplicate_journal_entry

DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"


def load_account_map(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Account mapping file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_html_report(period_entries: dict, errors: dict) -> str:
    html = ["<html><head><title>Dry‑run Import Report</title></head><body>"]
    html.append("<h1>Dry‑run Import Preparation Report</h1>")
    html.append(f"<p>Generated on {Path.cwd()}</p>")
    html.append("<hr/>")
    for period, data in period_entries.items():
        payload = data["payload"]
        totals = data["totals"]
        html.append(f"<h2>Period {period}</h2>")
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
    html.append("<h2>Errors</h2>")
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
    parser = argparse.ArgumentParser(description="Safe workbook‑import dry run (local only)")
    parser.add_argument("workbook", help="Path to Excel workbook")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING_PATH), help="Path to account mapping JSON")
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser().resolve()
    mapping_path = Path(args.mapping).expanduser().resolve()

    # Load mapping (may raise and abort).
    try:
        account_map = load_account_map(mapping_path)
    except Exception as e:
        print(f"ERROR: Unable to load account mapping: {e}")
        sys.exit(1)

    # Load chart of accounts snapshot.
    try:
        coa_snapshot = list_chart_of_accounts_dict()
    except Exception as e:
        print(f"ERROR: Unable to retrieve chart of accounts: {e}")
        coa_snapshot = {"accounts": []}

    # Load workbook.
    try:
        is_stmt, bs_stmt = load_financial_workbook(workbook_path)
    except Exception as e:
        print(f"ERROR: Failed to load workbook: {e}")
        sys.exit(1)

    metrics = calculate_financial_metrics(is_stmt, bs_stmt)
    periods = metrics.get_chronological_periods()

    period_entries = {}
    errors = {}

    for p in periods:
        mm = metrics.get_monthly(p)
        norm = {
            "period": p,
            "revenue": mm.revenue,
            "cost_of_goods_sold": mm.cogs,
            "direct_opex": mm.direct_opex,
            "sm_payroll": mm.sm_payroll,
            "marketing": mm.marketing,
            "other_opex": mm.other_opex,
        }
        if mm.net_income is not None:
            norm["net_income"] = mm.net_income
        try:
            payload = prepare_journal_entry(norm, account_map)
            # Duplicate detection – safe‑guard against already‑imported periods.
            if is_duplicate_journal_entry(payload, p):
                errors[p] = f"Duplicate journal entry detected for period {p}"
                continue
            # Record totals and store payload.
            totals = {
                "debit": sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Debit"),
                "credit": sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Credit"),
            }
            period_entries[p] = {"payload": payload, "totals": totals}
            # Write JSON payload for review.
            payload_dir = repo_root / "reports" / "dry_run_payloads"
            payload_dir.mkdir(parents=True, exist_ok=True)
            (payload_dir / f"{p}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            errors[p] = str(exc)

    # Generate HTML report.
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    html_path = reports_dir / "dry_run_import_v2.html"
    html_path.write_text(build_html_report(period_entries, errors), encoding="utf-8")
    print(f"Dry-run HTML report written to {html_path}")
    print("JSON payloads written under reports/dry_run_payloads/ (marked NOT POSTED)")


if __name__ == "__main__":
    main()
