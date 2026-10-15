"""Generate a financial‑trend analysis report using live QuickBooks P&L data (read‑only).

This script demonstrates how the same report‑generation logic used for the Excel
workbook can be driven by normalized QuickBooks data. It does **not** perform any
validation of the source data – the workbook validation gate is omitted, and the
report clearly identifies the data source as "QuickBooks".
"""

import argparse
from pathlib import Path
from typing import List, Optional

from integrations.qbo_mcp_server import get_profit_and_loss
from src.metrics import MonthlyMetrics, FinancialMetricsResult, TTMMetrics
from run_financial_analysis import generate_report

# ---------------------------------------------------------------------
# Helper utilities (mirroring parts of src/metrics for safe calculations)
# ---------------------------------------------------------------------

def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator

# ---------------------------------------------------------------------
# Normalise QuickBooks P&L response to the metric schema expected by the report
# ---------------------------------------------------------------------

def normalise_pnl(pnl: dict) -> dict:
    """Map the QuickBooks P&L dictionary to a flat structure with the keys
    used by the workbook metrics.

    The workbook distinguishes several expense categories; QuickBooks provides
    only an aggregate ``operating_expenses`` value. Those detailed categories are
    left as ``None`` to signal missing detail (requirement 4).
    """
    report = pnl.get("report", {})
    return {
        "period": pnl.get("period", {}).get("start_date", ""),
        "revenue": report.get("total_revenue"),
        "cost_of_goods_sold": report.get("cost_of_goods_sold"),
        # Gross profit is revenue minus COGS when both are present.
        "gross_profit": (
            report.get("total_revenue") - report.get("cost_of_goods_sold")
            if report.get("total_revenue") is not None and report.get("cost_of_goods_sold") is not None
            else None
        ),
        "operating_expenses": report.get("operating_expenses"),
        "net_income": report.get("net_income"),
    }

# ---------------------------------------------------------------------
# Build FinancialMetricsResult from a list of normalised month dicts
# ---------------------------------------------------------------------

def build_metrics_from_quickbooks(normalised: List[dict]) -> FinancialMetricsResult:
    monthly = {}
    prev_rev = None
    prev_op_inc = None
    prev_net_inc = None
    for entry in normalised:
        period = entry["period"][:7]  # Ensure YYYY‑MM format
        rev = entry.get("revenue")
        cogs = entry.get("cost_of_goods_sold")
        gp = entry.get("gross_profit")
        op_exp = entry.get("operating_expenses")
        net = entry.get("net_income")

        # Derive totals and ratios similar to src.metrics logic.
        gross_margin = _safe_ratio(gp, rev)
        total_opex = op_exp
        operating_income = (gp - total_opex) if gp is not None and total_opex is not None else None
        operating_margin = _safe_ratio(operating_income, rev)
        net_margin = _safe_ratio(net, rev)

        # MoM calculations (only revenue for now, other changes omitted).
        rev_mom_usd = rev - prev_rev if rev is not None and prev_rev is not None else None
        rev_mom_pct = (rev - prev_rev) / prev_rev if rev is not None and prev_rev not in (None, 0) else None
        op_inc_mom_usd = operating_income - prev_op_inc if operating_income is not None and prev_op_inc is not None else None
        net_inc_mom_usd = net - prev_net_inc if net is not None and prev_net_inc is not None else None

        mm = MonthlyMetrics(
            period=period,
            revenue=rev,
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=cogs,
            gross_profit=gp,
            gross_margin_pct=gross_margin,
            direct_opex=None,
            sm_payroll=None,
            marketing=None,
            other_opex=op_exp,
            total_opex=total_opex,
            direct_opex_pct=None,
            sm_payroll_pct=None,
            marketing_pct=None,
            other_opex_pct=_safe_ratio(op_exp, total_opex),
            operating_income=operating_income,
            operating_margin_pct=operating_margin,
            operating_income_mom_change_usd=op_inc_mom_usd,
            net_income=net,
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_inc_mom_usd,
        )
        monthly[period] = mm
        prev_rev = rev
        prev_op_inc = operating_income
        prev_net_inc = net

    return FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})

# ---------------------------------------------------------------------
# Dummy validation report for live data (no validation performed)
# ---------------------------------------------------------------------
class DummyValidationReport:
    can_proceed_to_downstream = False
    critical_findings = []
    warning_findings = []
    findings = []

# ---------------------------------------------------------------------
# Main entry point – generate report for a given month range
# ---------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate a financial‑trend report from live QuickBooks P&L data.")
    parser.add_argument("start_month", help="First month in YYYY‑MM format (inclusive)")
    parser.add_argument("end_month", help="Last month in YYYY‑MM format (inclusive)")
    args = parser.parse_args()

    # Generate normalised monthly data using the MCP read‑only tool.
    normalised = []
    # Simple month iterator (year‑month arithmetic).
    from datetime import datetime
    cur = datetime.strptime(args.start_month, "%Y-%m")
    end = datetime.strptime(args.end_month, "%Y-%m")
    while cur <= end:
        start_date = cur.strftime("%Y-%m-01")
        # End of month – determine last day.
        if cur.month == 12:
            next_month = datetime(cur.year + 1, 1, 1)
        else:
            next_month = datetime(cur.year, cur.month + 1, 1)
        last_day = (next_month - timedelta(days=1)).day
        end_date = cur.strftime(f"%Y-%m-{last_day:02d}")
        pnl = get_profit_and_loss(start_date, end_date)
        normalised.append(normalise_pnl(pnl))
        # advance month
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    metrics = build_metrics_from_quickbooks(normalised)
    dummy_val = DummyValidationReport()
    report_path = Path("reports") / "financial-trend-analysis_live_qb_report.md"
    generate_report("QuickBooks", None, None, dummy_val, metrics, report_path)
    print(f"Live‑data report written to {report_path}")

if __name__ == "__main__":
    from datetime import timedelta
    main()
