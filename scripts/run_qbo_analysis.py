import sys
import pathlib
# Add repository root to sys.path so that ``src`` can be imported.
repo_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))

from src.qbo_analysis import analyze_profit_and_loss

def format_pct(value):
    return f"{value:.2f}%" if value is not None else "N/A"

def main():
    report_path = repo_root / "reports" / "qbo_profit_and_loss_2026_ytd.json"
    analysis = analyze_profit_and_loss(report_path)
    period = analysis["period"]
    currency = analysis.get("currency", "USD")
    derived = analysis["derived"]
    source = analysis["source"]

    md_lines = []
    md_lines.append("# QuickBooks Profit & Loss – YTD Analysis (2026)")
    md_lines.append("")
    md_lines.append(f"**Period:** {period.get('start_date')} to {period.get('end_date')}")
    md_lines.append(f"**Currency:** {currency}")
    md_lines.append(f"**Accounting Basis:** {source.get('report_basis', 'Accrual') if isinstance(source, dict) else 'Accrual'}")
    md_lines.append("")
    md_lines.append("## Aggregate Totals")
    md_lines.append(f"- Total Revenue: ${source.get('total_revenue', 'N/A')}")
    md_lines.append(f"- Cost of Goods Sold: ${source.get('cost_of_goods_sold', 'N/A')}")
    md_lines.append(f"- Gross Profit: ${source.get('gross_profit', 'N/A')}")
    md_lines.append(f"- Operating Expenses: ${source.get('operating_expenses', 'N/A')}")
    md_lines.append(f"- Net Operating Income: ${source.get('net_operating_income', 'N/A')}")
    md_lines.append(f"- Total Other Expenses: ${source.get('total_other_expenses', 'N/A')}")
    md_lines.append(f"- Net Income: ${source.get('net_income', 'N/A')}")
    md_lines.append("")
    md_lines.append("## Derived Margins")
    md_lines.append(f"- Gross Margin: {format_pct(derived.get('gross_margin_pct'))}")
    md_lines.append(f"- Operating Margin: {format_pct(derived.get('operating_margin_pct'))}")
    md_lines.append(f"- Net Margin: {format_pct(derived.get('net_margin_pct'))}")
    md_lines.append("")
    md_lines.append("**Limitations:** The QuickBooks API for this YTD request returns only aggregate totals; monthly breakdowns are not available. Percentages are calculated from the aggregate numbers. No transaction‑level detail is included.")
    md_content = "\n".join(md_lines)
    out_path = repo_root / "reports" / "qbo_financial_trend_analysis_2026_ytd.md"
    out_path.write_text(md_content, encoding="utf-8")
    print(f"Report written to {out_path}")

if __name__ == "__main__":
    main()
