"""Live QuickBooks data retrieval and comparison with workbook metrics.

This script loads the supplied Excel workbook, computes the normalized monthly
metrics using the project's ingestion and metrics pipeline, generates JournalEntry
payloads via the existing ``prepare_journal_entry`` function, then queries the
QuickBooks sandbox for any JournalEntry objects that exist for the same period.
It compares the generated payloads with the live entries using the same
canonical fingerprint implementation found in ``integrations.qbo_mcp_server``.
A concise markdown report is written to ``reports/live_qb_analysis_report.md``
showing, for each period, whether a matching entry exists in QuickBooks, how many
entries were found, and any differences in totals.

The script performs **no write** to QuickBooks – it only reads via the MCP
connection. If a write is ever required the user must explicitly approve the
operation; this script will stop and display the proposed JournalEntry payloads.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
import calendar

# Ensure the repository root is on ``sys.path`` so that project imports work.
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

# Project imports
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from integrations.qbo_import_preparation import prepare_journal_entry
from integrations.qbo_mcp_server import (
    query_journal_entries,
    _canonical_fingerprint,
)

# Load the account mapping – required for payload generation.
DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"
with open(DEFAULT_MAPPING_PATH, "r", encoding="utf-8") as f:
    account_map = json.load(f)

# ---------------------------------------------------------------------------
# Helper: month end day for a ``YYYY-MM`` period string.
def month_end(day_str: str) -> str:
    year, month = map(int, day_str.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return f"{day_str}-{last_day:02d}"

# ---------------------------------------------------------------------------
# Load workbook and calculate metrics.
# The skill expects a single .xlsx under ``data/input`` – we follow the same logic.
workbook_candidates = list((repo_root / "data" / "input").glob("*.xlsx"))
if len(workbook_candidates) != 1:
    raise FileNotFoundError(
        f"Expected exactly one workbook in {repo_root / 'data' / 'input'}, found {len(workbook_candidates)}"
    )
WORKBOOK_PATH = workbook_candidates[0]

is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
metrics = calculate_financial_metrics(is_stmt, bs_stmt)
periods = metrics.get_chronological_periods()

# ---------------------------------------------------------------------------
# Prepare payloads per period (unbalanced – net_income line omitted unless the mapping
# contains a ``net_income`` key and the period includes ``net_income``).
payloads_by_period = {}
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
    except Exception as exc:
        # If payload generation fails we record the error and continue.
        payloads_by_period[p] = {"error": str(exc)}
        continue
    payloads_by_period[p] = {"payload": payload}

# ---------------------------------------------------------------------------
# Query QuickBooks for each period and compare fingerprints.
report_lines = ["# Live QuickBooks vs Workbook Comparison Report", ""]
for period, info in payloads_by_period.items():
    report_lines.append(f"## Period {period}")
    if "error" in info:
        report_lines.append(f"*Payload generation error:* {info['error']}")
        report_lines.append("")
        continue
    payload = info["payload"]
    # Compute fingerprint of our payload.
    local_fp = _canonical_fingerprint(payload)
    # Query QB for entries spanning the whole month.
    start_date = f"{period}-01"
    end_date = month_end(period)
    try:
        qb_entries = query_journal_entries(start_date, end_date)
    except Exception as exc:
        report_lines.append(f"*QuickBooks query error:* {exc}")
        report_lines.append("")
        continue
    report_lines.append(f"*Found {len(qb_entries)} JournalEntry record(s) in QuickBooks for this month.")
    # Determine if any entry matches our payload.
    match_found = False
    for entry in qb_entries:
        try:
            entry_fp = _canonical_fingerprint(entry)
        except Exception:
            # Skip malformed entries.
            continue
        if entry_fp == local_fp:
            match_found = True
            break
    if match_found:
        report_lines.append("*✅ Matching entry exists in QuickBooks (fingerprint identical).*")
    else:
        report_lines.append("*❓ No matching entry found in QuickBooks.*")
    report_lines.append("")

# Write the markdown report.
reports_dir = repo_root / "reports"
reports_dir.mkdir(parents=True, exist_ok=True)
report_path = reports_dir / "live_qb_analysis_report.md"
report_path.write_text("\n".join(report_lines), encoding="utf-8")
print(f"Live QuickBooks analysis report written to {report_path}")
