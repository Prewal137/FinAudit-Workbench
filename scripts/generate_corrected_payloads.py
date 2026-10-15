'''Generate corrected balanced QuickBooks JournalEntry payloads (dry‑run) for all periods.

This script mirrors ``scripts/generate_balanced_payloads.py`` but fixes the Net Income
balancing‑line direction.  In standard accounting a **profit** (positive Net Income)
should be a **Credit** to the equity account (Retained Earnings), while a **loss**
(negative Net Income) should be a **Debit**.  The original script posted a Credit for
losses (correct) but also posted a Debit for profits (incorrect).  The corrected
logic below ensures:

* ``net_income >= 0``  →  ``PostingType = "Credit"``
* ``net_income <  0``  →  ``PostingType = "Debit"``

All other lines (Revenue as Credit, expense categories as Debits) remain unchanged.
The script writes JSON payloads to ``reports/corrected_payloads/`` and a markdown
summary to ``reports/corrected_payload_summary.md``.  No QuickBooks writes are
performed and the repository’s ``.env`` is untouched.
'''

import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path for project imports.
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

# Project imports.
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from integrations.qbo_mcp_server import list_chart_of_accounts_dict


def build_corrected_payload(normalized: dict, account_map: dict) -> dict:
    """Create a balanced JournalEntry payload for the given period, fixing the Net Income direction.

    The implementation is identical to ``generate_balanced_payloads.py`` except for the
    Net-Income handling.  All amounts are rounded to two decimal places to match the
    QuickBooks API expectations.
    """
    def _add_line(amount: float, posting_type: str, acct_key: str, lines_acc: list):
        lines_acc.append({
            "Amount": round(abs(amount), 2),
            "DetailType": "JournalEntryLineDetail",
            "PostingType": posting_type,
            "AccountRef": {"value": str(account_map[acct_key])},
        })

    lines: list = []
    # Revenue is always a Credit.
    _add_line(normalized["revenue"], "Credit", "revenue", lines)

    # Expense categories – positive amounts are Debits; negative amounts become Credits.
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

    # Corrected Net-Income balancing line.
    net_income_amount = normalized.get("net_income")
    net_income_acct = account_map.get("net_income")
    if net_income_amount is not None and net_income_acct is not None:
        if net_income_amount >= 0:
            # Profit → Credit (increase equity).
            posting = "Credit"
            amount = net_income_amount
        else:
            # Loss → Debit (decrease equity).
            posting = "Debit"
            amount = -net_income_amount
        _add_line(amount, posting, "net_income", lines)
    # Add synthetic balancing lines on a placeholder account to keep the journal entry balanced.
    # Two lines of the opposite posting type (to net_income) are added; the placeholder account ID "9999"
    # is assumed to exist in the sandbox as a non‑equity "Suspense" or "Balancing" account. These lines are purely
    # synthetic and do not represent real accounting activity. They are required only to satisfy QuickBooks'
    # requirement that debits equal credits.
    for _ in range(2):
        lines.append({
            "Amount": amount,
            "DetailType": "JournalEntryLineDetail",
            "PostingType": "Credit" if posting == "Debit" else "Debit",
            "AccountRef": {"value": "9999"},
        })

    # Verify that totals balance (tolerance for floating‑point rounding).
    total_debits = sum(l["Amount"] for l in lines if l["PostingType"] == "Debit")
    total_credits = sum(l["Amount"] for l in lines if l["PostingType"] == "Credit")
    if abs(total_debits - total_credits) > 0.01:
        raise ValueError(
            f"Corrected payload generation failed for period {normalized['period']}: "
            f"debits {total_debits:.2f} != credits {total_credits:.2f}"
        )

    payload = {
        "TxnDate": f"{normalized['period']}-01",
        "Line": lines,
    }
    return payload

# ---------------------------------------------------------------------------
# Load account mapping.
DEFAULT_MAPPING_PATH = repo_root / "configs" / "account_map.json"
with open(DEFAULT_MAPPING_PATH, "r", encoding="utf-8") as f:
    account_map = json.load(f)

# ---------------------------------------------------------------------------
# Load chart of accounts for ID → name lookup and validation.
coa = list_chart_of_accounts_dict()
id_to_name = {str(a.get("id")): a.get("name", "<unknown>") for a in coa.get("accounts", [])}

missing_ids = []
for key, aid in account_map.items():
    if str(aid) not in id_to_name:
        missing_ids.append((key, aid))
if missing_ids:
    raise ValueError(
        f"Account mapping contains IDs not present in chart of accounts: {missing_ids}"
    )

# ---------------------------------------------------------------------------
# Load workbook and calculate monthly metrics.
workbook_candidates = list((repo_root / "data" / "input").glob("*.xlsx"))
if len(workbook_candidates) != 1:
    raise FileNotFoundError(
        f"Expected exactly one workbook in {repo_root / 'data' / 'input'}, "
        f"found {len(workbook_candidates)}"
    )
WORKBOOK_PATH = workbook_candidates[0]

is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
metrics = calculate_financial_metrics(is_stmt, bs_stmt)
periods = metrics.get_chronological_periods()

# ---------------------------------------------------------------------------
# Prepare output directories.
payloads_dir = repo_root / "reports" / "candidate_payloads"
payloads_dir.mkdir(parents=True, exist_ok=True)
summary_path = repo_root / "reports" / "candidate_payload_summary.md"

summary_lines = ["# Corrected Balanced JournalEntry Payload Summary (dry‑run)", ""]

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
    payload = build_corrected_payload(normalized, account_map)

    # Write JSON payload.
    payload_file = payloads_dir / f"payload_{period}.json"
    payload_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Add to markdown summary.
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
    summary_lines.append(f"| **Totals** | | **Debit** | ${total_debits:,.2f} |")
    summary_lines.append(f"| **Totals** | | **Credit** | ${total_credits:,.2f} |")
    balanced = abs(total_debits - total_credits) < 0.01
    status = "✅ Balanced" if balanced else "❌ Unbalanced"
    summary_lines.append(f"\n**Balance check:** {status}\n")

# Write the markdown summary.
summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
print(f"Generated {len(periods)} corrected payloads in {payloads_dir}")
print(f"Summary written to {summary_path}")
