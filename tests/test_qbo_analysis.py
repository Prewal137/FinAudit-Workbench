import json
from pathlib import Path
import pytest

from src.qbo_analysis import analyze_profit_and_loss

# Helper to locate the repository root (two levels up from this file: tests -> repo).
REPO_ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def report_2026_path():
    return REPO_ROOT / "reports" / "qbo_profit_and_loss_2026_ytd.json"

@pytest.fixture
def report_2025_path():
    return REPO_ROOT / "reports" / "qbo_profit_and_loss_2025.json"

def test_analyze_populated_report(report_2026_path):
    analysis = analyze_profit_and_loss(report_2026_path)
    # Verify period and currency preservation
    assert analysis["period"] == {"start_date": "2026-01-01", "end_date": "2026-10-15"}
    assert analysis["currency"] == "USD"
    # Verify all metric_status entries are "available"
    for status in analysis["metric_status"].values():
        assert status == "available"
    # Verify derived margins (rounded to two decimals)
    derived = analysis["derived"]
    assert derived["gross_margin_pct"] == 96.03
    assert derived["operating_margin_pct"] == 44.69
    assert derived["net_margin_pct"] == 16.10

def test_analyze_empty_report(report_2025_path):
    analysis = analyze_profit_and_loss(report_2025_path)
    # All metric_status should be "unavailable"
    for status in analysis["metric_status"].values():
        assert status == "unavailable"
    # Derived margins should be None because total revenue is missing/None
    derived = analysis["derived"]
    assert derived["gross_margin_pct"] is None
    assert derived["operating_margin_pct"] is None
    assert derived["net_margin_pct"] is None

def test_missing_metrics(tmp_path):
    # Create a minimal report JSON missing gross_profit and net_income
    data = {
        "retrieved_at": "2026-10-15T00:00:00Z",
        "period": {"start_date": "2026-01-01", "end_date": "2026-06-30"},
        "report": {
            "total_revenue": "5000.00",
            "cost_of_goods_sold": "1500.00",
            # gross_profit omitted
            "operating_expenses": "2000.00",
            # net_operating_income omitted
            "total_other_expenses": "300.00",
            # net_income omitted
        },
        "metric_status": {
            "total_revenue": "available",
            "cost_of_goods_sold": "available",
            "gross_profit": "unavailable",
            "operating_expenses": "available",
            "net_operating_income": "unavailable",
            "total_other_expenses": "available",
            "net_income": "unavailable",
        },
        "no_report_data": False,
        "currency": "USD",
        "report_name": "ProfitAndLoss",
        "report_basis": "Accrual",
    }
    json_path = tmp_path / "partial_report.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    analysis = analyze_profit_and_loss(json_path)
    derived = analysis["derived"]
    # gross_margin_pct cannot be computed without gross_profit
    assert derived["gross_margin_pct"] is None
    # operating_margin_pct cannot be computed without net_operating_income
    assert derived["operating_margin_pct"] is None
    # net_margin_pct cannot be computed without net_income
    assert derived["net_margin_pct"] is None
    # Metric status matches input
    assert analysis["metric_status"]["gross_profit"] == "unavailable"
    assert analysis["metric_status"]["net_income"] == "unavailable"

def test_preserve_dates_and_currency(report_2026_path):
    analysis = analyze_profit_and_loss(report_2026_path)
    assert analysis["period"]["start_date"] == "2026-01-01"
    assert analysis["period"]["end_date"] == "2026-10-15"
    assert analysis["currency"] == "USD"

# End of test file
