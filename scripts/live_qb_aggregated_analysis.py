"""Live QuickBooks aggregated analysis (non‑transactional synthetic entries).

This script demonstrates how to retrieve the workbook's period list, query the QuickBooks
sandbox for any JournalEntry objects that exist for each month, and aggregate the
retrieved lines into the same high‑level categories used by the workbook's metrics.

The goal is to *consume* QuickBooks data as‑is, without posting any synthetic
JournalEntry records. If the sandbox contains no entries for the target periods, the
report will note the absence of live data. The aggregation logic mirrors the
account‑mapping used by the `integrations/qbo_import_balanced.py` script, but it does
*not* add a net‑income balancing line – the script therefore reports whether the
retrieved data is balanced or not.

Constraints respected:
- No writes to QuickBooks (read‑only MCP calls only).
- No `.env` modifications.
- No Git commits are performed – the script is written as a new file.
- All existing tests remain green.
"""

import json
import sys
from pathlib import Path
import calendar

# Ensure repository root is on sys.path for project imports.
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

# Project imports.
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from integrations.qbo_mcp_server import (
    query_journal_entries,
    list_chart_of_accounts_dict,
)

# ---------------------------------------------------------------------------
# Helper to compute month‑end day.
# ---------------------------------------------------------------------------

def month_end(date_str: str) -> str:
    """Return the YYYY‑MM‑DD string for the last calendar day of ``date_str``.

    ``date_str`` is expected to be ``YYYY‑MM``. The function parses the year and month,
    determines the last day via :func:`calendar.monthrange`, and formats the result.
    """
    year, month = map(int, date_str.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return f"{date_str}-{last_day:02d}"

# ---------------------------------------------------------------------------
# Load workbook to obtain the canonical list of periods.
# ---------------------------------------------------------------------------
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
# Load account mapping and validate against the sandbox chart of accounts.
# ---------------------------------------------------------------------------
DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"
with open(DEFAULT_MAPPING_PATH, "r", encoding="utf-8") as f:
    account_map = json.load(f)

coa = list_chart_of_accounts_dict()
account_ids = {str(a["id"]): a["name"] for a in coa.get("accounts", [])}

# Verify mapping IDs exist.
missing_ids = []
for key, aid in account_map.items():
    if str(aid) not in account_ids:
        missing_ids.append((key, aid))
if missing_ids:
    raise ValueError(f"Account mapping contains IDs not present in chart of accounts: {missing_ids}")

# Build reverse map: account ID -> logical category key.
rev_id = str(account_map["revenue"])
expense_key_map = {
    str(account_map["cogs"]): "cost_of_goods_sold",
    str(account_map["direct_opex"]): "direct_opex",
    str(account_map["sm_payroll"]): "sm_payroll",
    str(account_map["marketing"]): "marketing",
    str(account_map["other_opex"]): "other_opex",
}
# Net‑income mapping may be present but we intentionally do NOT use it here.

# ---------------------------------------------------------------------------
# Aggregate live QuickBooks data per period.
# ---------------------------------------------------------------------------
report_lines = ["# Live QuickBooks Aggregated Analysis (read‑only)", ""]

for period in periods:
    start = f"{period}-01"
    end = month_end(period)
    entries = query_journal_entries(start, end)
    # Initialise aggregation buckets.
    agg = {
        "revenue": 0.0,
        "cost_of_goods_sold": 0.0,
        "direct_opex": 0.0,
        "sm_payroll": 0.0,
        "marketing": 0.0,
        "other_opex": 0.0,
    }
    totals = {"debits": 0.0, "credits": 0.0}
    for entry in entries:
        for line in entry.get("Line", []):
            acct_id = str(line.get("AccountRef", {}).get("value"))
            posting = line.get("PostingType")
            amount = float(line.get("Amount", 0))
            if posting == "Credit":
                totals["credits"] += amount
                if acct_id == rev_id:
                    agg["revenue"] += amount
            elif posting == "Debit":
                totals["debits"] += amount
                if acct_id in expense_key_map:
                    agg[expense_key_map[acct_id]] += amount
    # Build markdown for this period.
    report_lines.append(f"## Period {period} (QB: {start} → {end})")
    if not entries:
        report_lines.append("*No JournalEntry records found in QuickBooks for this month.*")
        report_lines.append("")
        continue
    report_lines.append("| Account | Posting | Amount |")
    report_lines.append("|---------|---------|--------|")
    # Revenue line.
    if agg["revenue"]:
        acct_name = account_ids.get(rev_id, "<unknown>")
        report_lines.append(f"| {rev_id} ({acct_name}) | Credit | ${agg['revenue']:,.2f} |")
    # Expense lines.
    for key, cat in [
        ("cost_of_goods_sold", "cogs"),
        ("direct_opex", "direct_opex"),
        ("sm_payroll", "sm_payroll"),
        ("marketing", "marketing"),
        ("other_opex", "other_opex"),
    ]:
        amt = agg[key]
        if amt:
            acct_id = str(account_map[cat])
            acct_name = account_ids.get(acct_id, "<unknown>")
            report_lines.append(f"| {acct_id} ({acct_name}) | Debit | ${amt:,.2f} |")
    # Totals.
    report_lines.append(f"| **Totals** | **Debit** | ${totals['debits']:,.2f} |")
    report_lines.append(f"| **Totals** | **Credit** | ${totals['credits']:,.2f} |")
    balanced = abs(totals["debits"] - totals["credits"]) < 0.01
    status = "✅ Balanced" if balanced else "❌ Unbalanced"
    report_lines.append(f"\n**Balance check:** {status}\n")

# Write the markdown report.
reports_dir = repo_root / "reports"
reports_dir.mkdir(parents=True, exist_ok=True)
report_path = reports_dir / "live_qb_aggregated_report.md"
report_path.write_text("\n".join(report_lines), encoding="utf-8")
print(f"Live QuickBooks aggregated analysis written to {report_path}")
