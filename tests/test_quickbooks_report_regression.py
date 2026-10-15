import pathlib
from src.metrics import MonthlyMetrics, FinancialMetricsResult

# Reuse DummyVal from test_live_qb_report_integration
class DummyVal:
    can_proceed_to_downstream = False
    critical_findings = []
    warning_findings = []
    findings = []

def test_quickbooks_report_content(tmp_path: pathlib.Path):
    mm = MonthlyMetrics(
        period="2025-01",
        revenue=1000.0,
        total_opex=600.0,
        operating_income=200.0,
        net_income=150.0,
    )
    metrics = FinancialMetricsResult(monthly_metrics={"2025-01": mm}, ttm_metrics={})
    report_file = tmp_path / "qb_report.md"
    # Import generate_report
    from run_financial_analysis import generate_report
    generate_report(
        "QuickBooks",
        None,  # is_stmt not used for QuickBooks
        None,  # bs_stmt not used
        DummyVal(),
        metrics,
        report_file,
    )
    content = report_file.read_text(encoding="utf-8")
    # Check expense label uses "Operating Expenses"
    assert "| Period | Direct OpEx | S&M Payroll | Marketing | Operating Expenses | Total OpEx |" in content
    # Check balance-sheet unavailable notice
    assert "*Balance‑sheet data is not available for QuickBooks source.*" in content
    # Check no supported anomalies message
    assert "- No supported anomalies found for QuickBooks source." in content
    # Ensure workbook-specific recommendation lines are absent
    assert "Reconcile the December 2025 tax benefit" not in content
