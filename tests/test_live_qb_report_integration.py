import sys
import pathlib
import tempfile
from unittest import mock

# Ensure the project root is on the import path for module resolution
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import importlib.util, os

def load_module(module_name: str, rel_path: str):
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path))
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_live_qb_mod = load_module("live_qb_financial_trend_report", "scripts/live_qb_financial_trend_report.py")
normalise_pnl = _live_qb_mod.normalise_pnl
build_metrics_from_quickbooks = _live_qb_mod.build_metrics_from_quickbooks

_run_fin_mod = load_module("run_financial_analysis", "run_financial_analysis.py")
generate_report = _run_fin_mod.generate_report

from src.metrics import MonthlyMetrics, FinancialMetricsResult


# Dummy validation report that mimics the attributes used in generate_report
class DummyVal:
    can_proceed_to_downstream = False
    critical_findings = []
    warning_findings = []
    findings = []

def test_generate_report_includes_source_flag(tmp_path: pathlib.Path):
    # Minimal metrics with a single period
    mm = MonthlyMetrics(
        period="2025-01",
        revenue=1000.0,
        total_opex=600.0,
        operating_income=200.0,
        net_income=150.0,
    )
    metrics = FinancialMetricsResult(monthly_metrics={"2025-01": mm}, ttm_metrics={})
    report_file = tmp_path / "qb_report.md"
    # Call generate_report with source_name="QuickBooks"
    generate_report(
        "QuickBooks",
        None,  # is_stmt not used for QuickBooks source
        None,  # bs_stmt not used
        DummyVal(),
        metrics,
        report_file,
    )
    content = report_file.read_text(encoding="utf-8")
    assert "- Data source: QuickBooks" in content

# Mocked QuickBooks P&L response for a single month
MOCK_PNL = {
    "period": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
    "report": {
        "total_revenue": 5000.0,
        "cost_of_goods_sold": 2000.0,
        "operating_expenses": 1500.0,
        "net_income": 1200.0,
    },
}

@mock.patch("integrations.qbo_mcp_server.get_profit_and_loss", return_value={
    "period": {"start_date": "2025-03-01", "end_date": "2025-03-31"},
    "report": {
        "total_revenue": "6000.5",
        "cost_of_goods_sold": "2500.25",
        "gross_profit": "3500.25",
        "operating_expenses": "1600.00",
        "net_income": "1300.00",
        "net_operating_income": "2000.00",
        "total_other_expenses": "300.00",
    },
})
def test_normalise_pnl_strings(mock_get):
    pnl = mock_get.return_value
    norm = normalise_pnl(pnl)
    assert norm["period"] == "2025-03-01"
    assert norm["revenue"] == 6000.5
    assert norm["cost_of_goods_sold"] == 2500.25
    assert norm["gross_profit"] == 3500.25
    assert norm["operating_expenses"] == 1600.0
    assert norm["net_income"] == 1300.0
    assert norm["net_operating_income"] == 2000.0
    assert norm["total_other_expenses"] == 300.0

@mock.patch("integrations.qbo_mcp_server.get_profit_and_loss", return_value={
    "period": {"start_date": "2025-04-01", "end_date": "2025-04-30"},
    "report": {
        "total_revenue": "not_a_number",
        "cost_of_goods_sold": None,
        "operating_expenses": "abc",
        "net_income": None,
    },
})
def test_normalise_pnl_invalid(mock_get):
    pnl = mock_get.return_value
    norm = normalise_pnl(pnl)
    assert norm["revenue"] is None
    assert norm["cost_of_goods_sold"] is None
    assert norm["operating_expenses"] is None
    assert norm["net_income"] is None



def test_build_metrics_from_quickbooks_two_months():
    # build_metrics_from_quickbooks is loaded via dynamic import above
    # Two months of normalized data
    month1 = {
        "period": "2025-01-01",
        "revenue": 5000.0,
        "cost_of_goods_sold": 2000.0,
        "gross_profit": 3000.0,
        "operating_expenses": 1500.0,
        "net_income": 1200.0,
    }
    month2 = {
        "period": "2025-02-01",
        "revenue": 5500.0,
        "cost_of_goods_sold": 2100.0,
        "gross_profit": 3400.0,
        "operating_expenses": 1600.0,
        "net_income": 1300.0,
    }
    metrics = build_metrics_from_quickbooks([month1, month2])
    assert set(metrics.monthly_metrics.keys()) == {"2025-01", "2025-02"}
    m1 = metrics.monthly_metrics["2025-01"]
    # Gross margin = gross_profit / revenue
    assert m1.gross_margin_pct == 3000.0 / 5000.0
    # Operating income = gross_profit - operating_expenses
    assert m1.operating_income == 3000.0 - 1500.0
    # Net margin = net_income / revenue
    assert m1.net_margin_pct == 1200.0 / 5000.0
    # MoM revenue change
    m2 = metrics.monthly_metrics["2025-02"]
    assert m2.revenue_mom_change_usd == 5500.0 - 5000.0
    assert m2.revenue_mom_change_pct == (5500.0 - 5000.0) / 5000.0
