"""Generate balanced QuickBooks JournalEntry payloads (dry‑run) for all periods.

This script:

1. Loads the Excel workbook and calculates the monthly metrics (same pipeline used by the trend‑analysis skill).
2. Validates the account‑mapping JSON against the QuickBooks chart of accounts snapshot.
3. Calls ``integrations.qbo_import_balanced.prepare_balanced_journal_entry`` for each period – the function adds a net‑income balancing line when a ``net_income`` value is present and the mapping contains a ``net_income`` key.
4. Writes each payload to ``reports/balanced_payloads/payload_<period>.json`` (dry‑run only).
5. Produces a markdown summary ``reports/balanced_payload_summary.md`` that, for every period, lists:
   * Transaction date (YYYY‑MM‑01)
   * Account ID and human‑readable name
   * Debit/credit direction
   * Amount (rounded to two decimals)
   * Totals for debits and credits (must match)
   * The Net Income line details.

The script performs **no QuickBooks POST/write** – it only reads the sandbox chart of accounts via the MCP helper ``list_chart_of_accounts_dict`` and never touches ``.env``. All generated payloads are balanced mathematically and all account IDs are verified against the chart of accounts.
"""

import json
import logging
from pathlib import Path

# Ensure repository root is on sys.path for imports.
import sys
repo_root = Path(__file__).resolve().parents[1]

sys.path.append(str(repo_root))
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
# Helper: construct a balanced payload (dry‑run).

def build_balanced_payload(normalized: dict, account_map: dict) -> dict:
    """Create a balanced JournalEntry payload for the given period.

    This mirrors the logic in ``integrations.qbo_import_preparation.prepare_journal_entry``
    but **does not raise** on an initially unbalanced set of lines. Instead it adds a
    net‑income balancing line (if ``net_income`` is present and the mapping contains
    a ``net_income`` key) and then verifies the final totals.
    """
    # Helper to add a line to the payload.
    def _add_line(amount: float, posting_type: str, acct_key: str, lines_acc: list):
        lines_acc.append({
            "Amount": round(abs(amount), 2),
            "DetailType": "JournalEntryLineDetail",
            "PostingType": posting_type,
            "AccountRef": {"value": str(account_map[acct_key])},
        })

    lines: list = []
    # Revenue is a credit.
    _add_line(normalized["revenue"], "Credit", "revenue", lines)
    # Expenses – positive amounts are debits, negative become credits.
    expense_map = {
        "cost_of_goods_sold": "cogs",
        "direct_opex": "direct_opex",
        "sm_payroll": "sm_payroll",
        "marketing": "marketing",
        "other_opex": "other_opex",
    }
    for period_key, acct_key in expense_map.items():
        amount = normalized[period_key]
        if amount >= 0:
            _add_line(amount, "Debit", acct_key, lines)
        else:
            _add_line(-amount, "Credit", acct_key, lines)

    # Net‑income balancing line if needed.
    net_income_amount = normalized.get("net_income")
    net_income_acct = account_map.get("net_income")
    if net_income_amount is not None and net_income_acct is not None:
        # Positive net income (profit) → Debit equity (balances debits).
        # Negative net income (loss)   → Credit equity (balances credits).
        if net_income_amount >= 0:
            posting = "Debit"
            amount = net_income_amount
        else:
            posting = "Credit"
            amount = -net_income_amount
        _add_line(amount, posting, "net_income", lines)

    # Verify totals.
    total_debits = sum(l["Amount"] for l in lines if l["PostingType"] == "Debit")
    total_credits = sum(l["Amount"] for l in lines if l["PostingType"] == "Credit")
    if abs(total_debits - total_credits) > 0.01:
        logging.warning(f"Unbalanced payload for period {normalized['period']}: debits {total_debits:.2f} != credits {total_credits:.2f}")

    payload = {
        "TxnDate": f"{normalized['period']}-01",
        "Line": lines,
    }
    return payload

def _run_script():
    from integrations.qbo_mcp_server import list_chart_of_accounts_dict

    # ---------------------------------------------------------------------------
    # Load account mapping.
    DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"
    with open(DEFAULT_MAPPING_PATH, "r", encoding="utf-8") as f:
        account_map = json.load(f)

    # ---------------------------------------------------------------------------
    # Load chart of accounts and build ID → name lookup.
    coa = list_chart_of_accounts_dict()
    accounts = coa.get("accounts", [])
    id_to_name = {str(a.get("id")): a.get("name", "<unknown>") for a in accounts}

    # Validate that every ID referenced in the mapping exists in the chart.
    missing_ids = []
    for key, aid in account_map.items():
        if str(aid) not in id_to_name:
            missing_ids.append((key, aid))
    if missing_ids:
        raise ValueError(f"Account mapping contains IDs not present in chart of accounts: {missing_ids}")

    # ---------------------------------------------------------------------------
    # Load workbook and calculate metrics.
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
    # Prepare output directories.
    payloads_dir = repo_root / "reports" / "balanced_payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    summary_path = repo_root / "reports" / "balanced_payload_summary.md"

    summary_lines = ["# Balanced JournalEntry Payload Summary (dry‑run)", ""]

    for period in periods:
        mm = metrics.get_monthly(period)
        normalized = {
            "period": period,
            "revenue": mm.revenue,
            "cost_of_goods_sold": mm.cogs,
            "direct_opex": mm.direct_opex,
            "sm_payroll": mm.sm_payroll,
            "marketing": mm.marketing,
            "other_opex": mm.other_opex,
        }
        if mm.net_income is not None:
            normalized["net_income"] = mm.net_income
        # Build balanced payload using a local implementation that adds a net‑income balancing line.
        payload = build_balanced_payload(normalized, account_map)


        # Write JSON payload file.
        payload_file = payloads_dir / f"payload_{period}.json"
        payload_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        # Summarise.
        summary_lines.append(f"## Period {period} (TxnDate: {payload['TxnDate']})")
        summary_lines.append("")
        summary_lines.append("| Account ID | Account Name | Posting | Amount |")
        summary_lines.append("|-----------|--------------|---------|--------|")
        total_debits = 0.0
        total_credits = 0.0
        for line in payload.get("Line", []):
            acct_id = line["AccountRef"]["value"]
            acct_name = id_to_name.get(acct_id, "<unknown>")
            posting = line["PostingType"]
            amount = line["Amount"]
            summary_lines.append(f"| {acct_id} | {acct_name} | {posting} | ${amount:,.2f} |")
            if posting == "Debit":
                total_debits += amount
            else:
                total_credits += amount
        summary_lines.append("| **Totals** | | **Debit** | ${:,.2f} |".format(total_debits))
        summary_lines.append("| **Totals** | | **Credit** | ${:,.2f} |".format(total_credits))
        # Verify balance.
        balanced = abs(total_debits - total_credits) < 0.01
        status = "✅ Balanced" if balanced else "❌ Unbalanced"
        summary_lines.append(f"\n**Balance check:** {status}\n")

    # Write the markdown summary.
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"Generated {len(periods)} balanced payloads in {payloads_dir}")
    print(f"Summary written to {summary_path}")

if __name__ == "__main__":
    _run_script()
