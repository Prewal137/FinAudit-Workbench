"""Automated tests for Phase 2 financial metrics engine.

Verifies monthly revenue, MoM changes, gross margins, workbook-defined OpEx groupings,
operating income, net income, trailing-12-month (TTM) aggregations, calendar continuity,
and missing input handling without zero-coercion.
"""

from pathlib import Path
import pytest

from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics
from src.models import (
    CellValue,
    FinancialLineItem,
    FinancialStatement,
    PeriodHeader,
    RowClassification,
)

WORKBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "input" / "ABC Inc - Financial Statements.xlsx"


@pytest.fixture(scope="module")
def statements():
    """Load statements once for module."""
    is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
    return is_stmt, bs_stmt


@pytest.fixture(scope="module")
def metrics(statements):
    """Calculate metrics once for module."""
    is_stmt, bs_stmt = statements
    return calculate_financial_metrics(is_stmt, bs_stmt)


def test_monthly_revenue_and_mom_calculations(metrics, statements):
    """Verify monthly revenue and MoM delta calculations against source workbook."""
    is_stmt, _ = statements
    chronological_periods = metrics.get_chronological_periods()
    assert len(chronological_periods) == 18

    # 1. First chronological period (2025-01): MoM must be None (not 0.0)
    jan25 = metrics.get_monthly("2025-01")
    assert jan25 is not None
    assert jan25.revenue == is_stmt.get_item_by_row(14).get_value("2025-01")
    assert jan25.revenue == 167587.5
    assert jan25.revenue_mom_change_usd is None, "MoM USD for first period must be None, not 0"
    assert jan25.revenue_mom_change_pct is None, "MoM % for first period must be None, not 0"

    # 2. Second chronological period (2025-02): MoM should match Feb 2025 vs Jan 2025
    feb25 = metrics.get_monthly("2025-02")
    feb25_expected_rev = is_stmt.get_item_by_row(14).get_value("2025-02")
    assert feb25.revenue == feb25_expected_rev
    expected_mom_usd = feb25_expected_rev - jan25.revenue
    expected_mom_pct = expected_mom_usd / jan25.revenue
    assert abs(feb25.revenue_mom_change_usd - expected_mom_usd) < 0.01
    assert abs(feb25.revenue_mom_change_pct - expected_mom_pct) < 0.0001

    # 3. Last chronological period (2026-06): check against 2026-05
    jun26 = metrics.get_monthly("2026-06")
    may26 = metrics.get_monthly("2026-05")
    assert jun26.revenue == is_stmt.get_item_by_row(14).get_value("2026-06")
    assert abs(jun26.revenue_mom_change_usd - (jun26.revenue - may26.revenue)) < 0.01
    assert abs(jun26.revenue_mom_change_pct - ((jun26.revenue - may26.revenue) / may26.revenue)) < 0.0001


def test_gross_profit_and_gross_margin(metrics, statements):
    """Verify gross profit and gross margin % for all 18 periods."""
    is_stmt, _ = statements

    for p in is_stmt.get_period_keys():
        m = metrics.get_monthly(p)
        assert m is not None

        row14_rev = is_stmt.get_item_by_row(14).get_value(p)
        row24_cogs = is_stmt.get_item_by_row(24).get_value(p)
        row26_gp = is_stmt.get_item_by_row(26).get_value(p)

        assert abs(m.revenue - row14_rev) < 0.01
        assert abs(m.cogs - row24_cogs) < 0.01
        assert abs(m.gross_profit - row26_gp) < 0.01
        assert abs(m.gross_profit - (m.revenue - m.cogs)) < 0.01

        # Margin
        expected_gm = row26_gp / row14_rev
        assert abs(m.gross_margin_pct - expected_gm) < 0.0001


def test_opex_workbook_defined_groupings_no_double_counting(metrics, statements):
    """Verify OpEx categories adhere to workbook groups and avoid double-counting."""
    is_stmt, _ = statements

    for p in is_stmt.get_period_keys():
        m = metrics.get_monthly(p)
        assert m is not None

        # Calculate expected sums directly from source detail rows
        exp_direct = sum(is_stmt.get_item_by_row(r).get_value(p) for r in range(29, 47))
        exp_sm_payroll = sum(is_stmt.get_item_by_row(r).get_value(p) for r in range(48, 59))
        exp_marketing = sum(is_stmt.get_item_by_row(r).get_value(p) for r in range(61, 71))
        exp_other = sum(is_stmt.get_item_by_row(r).get_value(p) for r in range(72, 103))
        exp_total_row = is_stmt.get_item_by_row(103).get_value(p)

        assert abs(m.direct_opex - exp_direct) < 0.01
        assert abs(m.sm_payroll - exp_sm_payroll) < 0.01
        assert abs(m.marketing - exp_marketing) < 0.01
        assert abs(m.other_opex - exp_other) < 0.01
        assert abs(m.total_opex - exp_total_row) < 0.01

        # Assert no double counting: sum of 4 components equals total OpEx
        component_sum = m.direct_opex + m.sm_payroll + m.marketing + m.other_opex
        assert abs(m.total_opex - component_sum) < 0.01


def test_operating_and_net_income(metrics, statements):
    """Verify operating income, net income, and margins across all 18 periods."""
    is_stmt, _ = statements

    for p in is_stmt.get_period_keys():
        m = metrics.get_monthly(p)
        assert m is not None

        row105_op = is_stmt.get_item_by_row(105).get_value(p)
        row107_ni = is_stmt.get_item_by_row(107).get_value(p)

        assert abs(m.operating_income - row105_op) < 0.01
        assert abs(m.net_income - row107_ni) < 0.01
        assert abs(m.operating_income - (m.gross_profit - m.total_opex)) < 0.01
        assert abs(m.net_income - m.operating_income) < 0.01

        expected_op_margin = row105_op / m.revenue
        assert abs(m.operating_margin_pct - expected_op_margin) < 0.0001
        assert abs(m.net_margin_pct - expected_op_margin) < 0.0001

    # Verify December 2025 Tax Benefit anomaly impact
    dec25 = metrics.get_monthly("2025-12")
    assert dec25.total_opex < 0.0, "Dec 2025 Total OpEx should be negative due to tax benefit"
    assert abs(dec25.total_opex - (-402142.09)) < 0.01
    assert dec25.operating_income > 0.0, "Dec 2025 Operating Income should be positive due to tax benefit"
    assert abs(dec25.operating_income - 534551.41) < 0.01


def test_trailing_12_month_metrics(metrics, statements):
    """Verify TTM window availability and aggregations on consecutive calendar months."""
    is_stmt, _ = statements
    chronological_periods = metrics.get_chronological_periods()

    # Periods 0..10 (2025-01 through 2025-11) must have NO TTM metrics (fewer than 12 months)
    for p in chronological_periods[:11]:
        assert metrics.get_ttm(p) is None, f"TTM for {p} should be None because < 12 months exist"

    # Periods 11..17 (2025-12 through 2026-06) must have valid TTM metrics (exactly 7 periods)
    assert len(metrics.ttm_metrics) == 7

    # Verify 2025-12 TTM (Calendar Year 2025)
    ttm_dec25 = metrics.get_ttm("2025-12")
    assert ttm_dec25 is not None
    assert len(ttm_dec25.trailing_periods) == 12
    assert ttm_dec25.trailing_periods == [
        "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
        "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
    ]

    expected_cy25_rev = sum(metrics.get_monthly(p).revenue for p in ttm_dec25.trailing_periods)
    expected_cy25_cogs = sum(metrics.get_monthly(p).cogs for p in ttm_dec25.trailing_periods)
    expected_cy25_gp = sum(metrics.get_monthly(p).gross_profit for p in ttm_dec25.trailing_periods)
    expected_cy25_opex = sum(metrics.get_monthly(p).total_opex for p in ttm_dec25.trailing_periods)
    expected_cy25_op = sum(metrics.get_monthly(p).operating_income for p in ttm_dec25.trailing_periods)

    assert abs(ttm_dec25.revenue - expected_cy25_rev) < 0.01
    assert abs(ttm_dec25.cogs - expected_cy25_cogs) < 0.01
    assert abs(ttm_dec25.gross_profit - expected_cy25_gp) < 0.01
    assert abs(ttm_dec25.total_opex - expected_cy25_opex) < 0.01
    assert abs(ttm_dec25.operating_income - expected_cy25_op) < 0.01
    assert abs(ttm_dec25.gross_profit - (ttm_dec25.revenue - ttm_dec25.cogs)) < 0.01
    assert abs(ttm_dec25.operating_income - (ttm_dec25.gross_profit - ttm_dec25.total_opex)) < 0.01

    # Verify 2026-06 TTM
    ttm_jun26 = metrics.get_ttm("2026-06")
    assert ttm_jun26 is not None
    assert len(ttm_jun26.trailing_periods) == 12
    assert ttm_jun26.trailing_periods[0] == "2025-07"
    assert ttm_jun26.trailing_periods[-1] == "2026-06"
    assert abs(ttm_jun26.gross_margin_pct - (ttm_jun26.gross_profit / ttm_jun26.revenue)) < 0.0001
    assert abs(ttm_jun26.operating_margin_pct - (ttm_jun26.operating_income / ttm_jun26.revenue)) < 0.0001


def test_balance_sheet_monthly_metrics(metrics, statements):
    """Verify Balance Sheet working capital and current ratio calculations."""
    _, bs_stmt = statements

    for p in bs_stmt.get_period_keys():
        m = metrics.get_monthly(p)
        assert m is not None

        exp_cash = bs_stmt.get_item_by_row(15).get_value(p)
        exp_ca = bs_stmt.get_item_by_row(27).get_value(p)
        exp_cl = bs_stmt.get_item_by_row(54).get_value(p)
        exp_ta = bs_stmt.get_item_by_row(37).get_value(p)
        exp_tl = bs_stmt.get_item_by_row(59).get_value(p)
        exp_te = bs_stmt.get_item_by_row(70).get_value(p)

        assert abs(m.cash - exp_cash) < 0.01
        assert abs(m.current_assets - exp_ca) < 0.01
        assert abs(m.current_liabilities - exp_cl) < 0.01
        assert abs(m.working_capital - (exp_ca - exp_cl)) < 0.01
        assert abs(m.current_ratio - (exp_ca / exp_cl)) < 0.0001
        assert abs(m.total_assets - exp_ta) < 0.01
        assert abs(m.total_liabilities - exp_tl) < 0.01
        assert abs(m.total_equity - exp_te) < 0.01


def test_genuine_zero_versus_missing_values():
    """Verify that genuine numeric zero is preserved as 0.0, while missing value remains None."""
    # Build isolated statement with Period A (revenue = 0.0) and Period B (revenue = None)
    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=[
            PeriodHeader("Month 1", "2026-01", 3, "C"),
            PeriodHeader("Month 2", "2026-02", 4, "D"),
        ],
        items=[
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=None),
            }),
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    "2026-01": CellValue(literal_value=0.0),
                    "2026-02": CellValue(literal_value=None),
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)

    m1 = result.get_monthly("2026-01")
    assert m1.revenue == 0.0, "Genuine numeric 0.0 must be preserved as 0.0"
    assert m1.gross_profit == 0.0
    assert m1.total_opex == 0.0

    m2 = result.get_monthly("2026-02")
    assert m2.revenue is None, "Missing revenue must be None, NOT coerced to 0.0"
    assert m2.gross_profit is None, "Missing gross profit must be None, NOT coerced to 0.0"
    assert m2.total_opex is None, "Missing total opex must be None, NOT coerced to 0.0"
    assert m2.gross_margin_pct is None, "Gross margin % must be None when inputs are missing"
    assert m2.operating_margin_pct is None, "Operating margin % must be None when inputs are missing"
    assert m2.net_margin_pct is None, "Net margin % must be None when inputs are missing"
    assert m2.revenue_mom_change_usd is None, "MoM USD change must be None when revenue is missing"
    assert m2.revenue_mom_change_pct is None, "MoM % change must be None when revenue is missing"


def test_zero_prior_month_revenue_mom():
    """Verify that when previous-month revenue is zero, MoM % returns None (avoid division by zero)."""
    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=[
            PeriodHeader("Month 1", "2026-01", 3, "C"),
            PeriodHeader("Month 2", "2026-02", 4, "D"),
        ],
        items=[
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=150000.0),
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=50000.0),
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=100000.0),
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=60000.0),
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=40000.0),
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=0.0),
                "2026-02": CellValue(literal_value=40000.0),
            }),
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    "2026-01": CellValue(literal_value=0.0),
                    "2026-02": CellValue(literal_value=1000.0),
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)
    m2 = result.get_monthly("2026-02")
    assert m2.revenue == 150000.0
    assert m2.revenue_mom_change_usd == 150000.0  # 150000 - 0
    assert m2.revenue_mom_change_pct is None, "MoM % with zero denominator must be None"


def test_ttm_calendar_gaps_rejected():
    """Verify that 12 periods with a gap in calendar months are rejected and produce NO TTM metrics."""
    # Create 12 periods with a gap: 2024-01 through 2024-06 (6 months), then 2025-01 through 2025-06 (6 months)
    discontinuous_periods = [
        "2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06",
        "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
    ]
    assert len(discontinuous_periods) == 12

    period_headers = [PeriodHeader(p, p, idx + 3, "C") for idx, p in enumerate(discontinuous_periods)]

    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=period_headers,
        items=[
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=10000.0) for p in discontinuous_periods
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=2000.0) for p in discontinuous_periods
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=8000.0) for p in discontinuous_periods
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=3000.0) for p in discontinuous_periods
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in discontinuous_periods
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in discontinuous_periods
            }),
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    p: CellValue(literal_value=100.0) for p in discontinuous_periods
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)
    # Even though 12 periods exist, there is a 6-month gap (2024-06 to 2025-01). TTM must be rejected!
    assert len(result.ttm_metrics) == 0, "Periods with calendar gaps must NOT produce TTM metrics"
    assert result.get_ttm("2025-06") is None


def test_ttm_missing_value_propagation():
    """Verify that if an input within a 12-month TTM window is missing, only affected metrics become None."""
    # 12 consecutive months: 2025-01 through 2025-12
    consecutive_periods = [
        f"2025-{m:02d}" for m in range(1, 13)
    ]
    period_headers = [PeriodHeader(p, p, idx + 3, "C") for idx, p in enumerate(consecutive_periods)]

    # Month 5 (2025-05) has revenue = None, but COGS is complete for all 12 months
    rev_values = {p: 10000.0 for p in consecutive_periods}
    rev_values["2025-05"] = None  # Missing revenue

    cogs_values = {p: 2000.0 for p in consecutive_periods}  # Complete COGS

    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=period_headers,
        items=[
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=rev_values[p]) for p in consecutive_periods
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=cogs_values[p]) for p in consecutive_periods
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=8000.0) for p in consecutive_periods
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=3000.0) for p in consecutive_periods
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in consecutive_periods
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in consecutive_periods
            }),
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    p: CellValue(literal_value=100.0) for p in consecutive_periods
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)
    ttm = result.get_ttm("2025-12")
    assert ttm is not None
    # Because 2025-05 revenue was None:
    assert ttm.revenue is None, "TTM revenue must be None when any month has missing revenue"
    assert ttm.gross_margin_pct is None, "TTM gross margin % must be None when TTM revenue is None"
    assert ttm.operating_margin_pct is None
    assert ttm.net_margin_pct is None

    # But COGS was complete for all 12 months (12 * 2000.0 = 24000.0):
    assert ttm.cogs == 24000.0, "Complete metrics must remain available and not be unnecessarily invalidated"


def test_missing_revenue_expense_and_profit_inputs():
    """Verify missing revenue, expense components, and profit inputs propagate independently as None."""
    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=[
            PeriodHeader("Month 1", "2026-01", 3, "C"),
            PeriodHeader("Month 2", "2026-02", 4, "D"),
            PeriodHeader("Month 3", "2026-03", 5, "E"),
        ],
        items=[
            # Month 1: Complete. Month 2: Missing GP and OpInc. Month 3: Missing Revenue.
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=100000.0),
                "2026-02": CellValue(literal_value=120000.0),
                "2026-03": CellValue(literal_value=None),  # Missing revenue
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=40000.0),
                "2026-02": CellValue(literal_value=45000.0),
                "2026-03": CellValue(literal_value=50000.0),
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=60000.0),
                "2026-02": CellValue(literal_value=None),  # Missing GP
                "2026-03": CellValue(literal_value=50000.0),
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                "2026-01": CellValue(literal_value=30000.0),
                "2026-02": CellValue(literal_value=30000.0),
                "2026-03": CellValue(literal_value=30000.0),
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=30000.0),
                "2026-02": CellValue(literal_value=None),  # Missing Operating Income
                "2026-03": CellValue(literal_value=20000.0),
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                "2026-01": CellValue(literal_value=30000.0),
                "2026-02": CellValue(literal_value=25000.0),
                "2026-03": CellValue(literal_value=20000.0),
            }),
            # OpEx detail rows: row 35 is None in Month 2 (missing expense input)
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    "2026-01": CellValue(literal_value=100.0),
                    "2026-02": CellValue(literal_value=None if r == 35 else 100.0),
                    "2026-03": CellValue(literal_value=100.0),
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)

    # Month 2 check:
    m2 = result.get_monthly("2026-02")
    assert m2.revenue == 120000.0
    # Missing expense input in row 35 propagates to direct_opex and direct_opex_pct:
    assert m2.direct_opex is None, "Direct OpEx must be None when any component row is missing"
    assert m2.direct_opex_pct is None, "Direct OpEx % must be None when direct_opex is None"
    # Unaffected OpEx component (SM payroll, rows 48-58) remains calculated:
    expected_sm_payroll = 11 * 100.0  # rows 48 to 58 = 11 rows
    assert m2.sm_payroll == expected_sm_payroll
    assert abs(m2.sm_payroll_pct - (expected_sm_payroll / 30000.0)) < 0.0001
    # Missing profit inputs:
    assert m2.gross_profit is None
    assert m2.gross_margin_pct is None, "Gross margin % must be None when gross profit is None"
    assert m2.operating_income is None
    assert m2.operating_margin_pct is None, "Operating margin % must be None when operating income is None"
    assert m2.operating_income_mom_change_usd is None, "Op Income MoM must be None when current op income is None"

    # Month 3 check:
    m3 = result.get_monthly("2026-03")
    assert m3.revenue is None
    assert m3.gross_margin_pct is None, "Gross margin % must be None when revenue is None"
    assert m3.operating_margin_pct is None, "Operating margin % must be None when revenue is None"
    assert m3.net_margin_pct is None, "Net margin % must be None when revenue is None"
    assert m3.revenue_mom_change_usd is None, "Revenue MoM USD must be None when revenue is None"
    assert m3.revenue_mom_change_pct is None, "Revenue MoM % must be None when revenue is None"


def test_incomplete_ttm_window_rejected():
    """Verify that statements with fewer than 12 months do not produce any TTM metrics."""
    periods = [f"2026-{m:02d}" for m in range(1, 7)]  # Only 6 months
    period_headers = [PeriodHeader(p, p, idx + 3, "C") for idx, p in enumerate(periods)]

    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=period_headers,
        items=[
            FinancialLineItem("Income Statement", 14, "Total Income", "Total Income", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=10000.0) for p in periods
            }),
            FinancialLineItem("Income Statement", 24, "Total COGS", "Total COGS", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=2000.0) for p in periods
            }),
            FinancialLineItem("Income Statement", 26, "Gross Profit", "Gross Profit", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=8000.0) for p in periods
            }),
            FinancialLineItem("Income Statement", 103, "Total OpEx", "Total OpEx", RowClassification.SUBTOTAL, values_by_period={
                p: CellValue(literal_value=3000.0) for p in periods
            }),
            FinancialLineItem("Income Statement", 105, "Operating Income", "Operating Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in periods
            }),
            FinancialLineItem("Income Statement", 107, "Net Income", "Net Income", RowClassification.CALCULATED_RESULT, values_by_period={
                p: CellValue(literal_value=5000.0) for p in periods
            }),
            *[
                FinancialLineItem("Income Statement", r, f"Account {r}", f"Account {r}", RowClassification.DETAIL_ACCOUNT, values_by_period={
                    p: CellValue(literal_value=100.0) for p in periods
                })
                for r in range(29, 103)
            ]
        ],
    )

    result = calculate_financial_metrics(stmt)
    assert len(result.ttm_metrics) == 0, "No TTM metrics should be produced when fewer than 12 months exist"
    for p in periods:
        assert result.get_ttm(p) is None
