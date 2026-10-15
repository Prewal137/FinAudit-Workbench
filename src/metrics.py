"""Financial metrics engine for FinAudit-Workbench.

Implements deterministic financial metric calculations, MoM changes,
gross margins, workbook-defined OpEx groupings, operating/net income,
trailing-12-month (TTM) metrics, calendar continuity validation,
and explicit handling of missing periods without zero-coercion.
Defined in accordance with docs/workbook_ingestion_spec.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.models import FinancialStatement


@dataclass
class MonthlyMetrics:
    """Calculated financial metrics for a single monthly reporting period."""
    period: str  # Format: 'YYYY-MM'
    
    # Revenue & MoM
    revenue: Optional[float] = None
    revenue_mom_change_usd: Optional[float] = None
    revenue_mom_change_pct: Optional[float] = None
    
    # Cost of Goods Sold & Gross Profit
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_margin_pct: Optional[float] = None  # gross_profit / revenue
    
    # Operating Expenses by workbook-defined categories
    direct_opex: Optional[float] = None
    sm_payroll: Optional[float] = None
    marketing: Optional[float] = None
    other_opex: Optional[float] = None
    total_opex: Optional[float] = None
    
    # OpEx Category Percentages of Total OpEx
    direct_opex_pct: Optional[float] = None
    sm_payroll_pct: Optional[float] = None
    marketing_pct: Optional[float] = None
    other_opex_pct: Optional[float] = None
    
    # Operating Income & Margin
    operating_income: Optional[float] = None
    operating_margin_pct: Optional[float] = None  # operating_income / revenue
    operating_income_mom_change_usd: Optional[float] = None
    
    # Net Income & Margin
    net_income: Optional[float] = None
    net_margin_pct: Optional[float] = None  # net_income / revenue
    net_income_mom_change_usd: Optional[float] = None

    # Balance Sheet metrics (if Balance Sheet available)
    cash: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    working_capital: Optional[float] = None
    current_ratio: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize monthly metrics to a dictionary."""
        return {
            "period": self.period,
            "revenue": self.revenue,
            "revenue_mom_change_usd": self.revenue_mom_change_usd,
            "revenue_mom_change_pct": self.revenue_mom_change_pct,
            "cogs": self.cogs,
            "gross_profit": self.gross_profit,
            "gross_margin_pct": self.gross_margin_pct,
            "direct_opex": self.direct_opex,
            "sm_payroll": self.sm_payroll,
            "marketing": self.marketing,
            "other_opex": self.other_opex,
            "total_opex": self.total_opex,
            "direct_opex_pct": self.direct_opex_pct,
            "sm_payroll_pct": self.sm_payroll_pct,
            "marketing_pct": self.marketing_pct,
            "other_opex_pct": self.other_opex_pct,
            "operating_income": self.operating_income,
            "operating_margin_pct": self.operating_margin_pct,
            "operating_income_mom_change_usd": self.operating_income_mom_change_usd,
            "net_income": self.net_income,
            "net_margin_pct": self.net_margin_pct,
            "net_income_mom_change_usd": self.net_income_mom_change_usd,
            "cash": self.cash,
            "current_assets": self.current_assets,
            "current_liabilities": self.current_liabilities,
            "working_capital": self.working_capital,
            "current_ratio": self.current_ratio,
            "total_assets": self.total_assets,
            "total_liabilities": self.total_liabilities,
            "total_equity": self.total_equity,
        }


@dataclass
class TTMMetrics:
    """Trailing-Twelve-Month (TTM) aggregated financial metrics."""
    period: str  # As of month (e.g., '2026-06')
    trailing_periods: List[str]  # Exactly 12 consecutive calendar periods included
    
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    
    direct_opex: Optional[float] = None
    sm_payroll: Optional[float] = None
    marketing: Optional[float] = None
    other_opex: Optional[float] = None
    total_opex: Optional[float] = None
    
    operating_income: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    
    net_income: Optional[float] = None
    net_margin_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize TTM metrics to a dictionary."""
        return {
            "period": self.period,
            "trailing_periods": self.trailing_periods,
            "revenue": self.revenue,
            "cogs": self.cogs,
            "gross_profit": self.gross_profit,
            "gross_margin_pct": self.gross_margin_pct,
            "direct_opex": self.direct_opex,
            "sm_payroll": self.sm_payroll,
            "marketing": self.marketing,
            "other_opex": self.other_opex,
            "total_opex": self.total_opex,
            "operating_income": self.operating_income,
            "operating_margin_pct": self.operating_margin_pct,
            "net_income": self.net_income,
            "net_margin_pct": self.net_margin_pct,
        }


@dataclass
class FinancialMetricsResult:
    """Container for all calculated monthly and TTM metrics."""
    monthly_metrics: Dict[str, MonthlyMetrics] = field(default_factory=dict)
    ttm_metrics: Dict[str, TTMMetrics] = field(default_factory=dict)

    def get_monthly(self, period: str) -> Optional[MonthlyMetrics]:
        """Retrieve metrics for a given period."""
        return self.monthly_metrics.get(period)

    def get_ttm(self, period: str) -> Optional[TTMMetrics]:
        """Retrieve TTM metrics ending at a given period."""
        return self.ttm_metrics.get(period)

    def get_chronological_periods(self) -> List[str]:
        """List of periods in chronological order."""
        return sorted(self.monthly_metrics.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all metrics to dictionary."""
        return {
            "monthly_metrics": {p: m.to_dict() for p, m in self.monthly_metrics.items()},
            "ttm_metrics": {p: t.to_dict() for p, t in self.ttm_metrics.items()},
        }


def _sum_account_range(stmt: FinancialStatement, row_range: range, period: str) -> Optional[float]:
    """Sum detail account values for a given range. Returns None if any input is missing."""
    total = 0.0
    for r in row_range:
        item = stmt.get_item_by_row(r)
        val = item.get_value(period)
        if val is None:
            return None
        total += val
    return total


def _safe_sum(values: List[Optional[float]]) -> Optional[float]:
    """Sum a list of floats. If any value is None, return None to propagate unavailable inputs."""
    if any(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Safely calculate ratio. Returns None if either input is None or denominator is zero."""
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return numerator / denominator


def _is_consecutive_calendar_months(periods: List[str]) -> bool:
    """Verify that a sequence of 'YYYY-MM' strings forms strictly consecutive calendar months."""
    if len(periods) < 2:
        return True
    
    parsed: List[Tuple[int, int]] = []
    for p in periods:
        try:
            parts = p.split("-")
            parsed.append((int(parts[0]), int(parts[1])))
        except (ValueError, IndexError):
            return False

    for i in range(1, len(parsed)):
        prev_y, prev_m = parsed[i - 1]
        curr_y, curr_m = parsed[i]
        months_diff = (curr_y * 12 + curr_m) - (prev_y * 12 + prev_m)
        if months_diff != 1:
            return False
    return True


def calculate_financial_metrics(
    is_stmt: FinancialStatement,
    bs_stmt: Optional[FinancialStatement] = None,
) -> FinancialMetricsResult:
    """Calculate deterministic financial metrics across all periods.
    
    Chronologically sorts periods for MoM and TTM calculations.
    Preserves genuine numeric zeros while propagating missing values as None.
    Validates calendar month continuity for all 12-month TTM windows.
    """
    raw_periods = is_stmt.get_period_keys()
    # Sort chronologically (oldest to newest)
    chronological_periods = sorted(raw_periods)

    monthly_dict: Dict[str, MonthlyMetrics] = {}
    prev_metrics: Optional[MonthlyMetrics] = None

    for p in chronological_periods:
        # 1. Core Income Statement lines
        rev = is_stmt.get_item_by_row(14).get_value(p)
        cogs = is_stmt.get_item_by_row(24).get_value(p)
        gp = is_stmt.get_item_by_row(26).get_value(p)

        # 2. OpEx categories per Section 8 of specification
        direct_opex = _sum_account_range(is_stmt, range(29, 47), p)
        sm_payroll = _sum_account_range(is_stmt, range(48, 59), p)
        marketing = _sum_account_range(is_stmt, range(61, 71), p)
        other_opex = _sum_account_range(is_stmt, range(72, 103), p)
        total_opex = is_stmt.get_item_by_row(103).get_value(p)

        # Operating Income (Row 105) & Net Income (Row 107)
        op_inc = is_stmt.get_item_by_row(105).get_value(p)
        net_inc = is_stmt.get_item_by_row(107).get_value(p)

        # Safe margins (None if rev is None or 0.0)
        gm_pct = _safe_ratio(gp, rev)
        op_margin_pct = _safe_ratio(op_inc, rev)
        net_margin_pct = _safe_ratio(net_inc, rev)

        # OpEx category proportions of total OpEx
        dir_pct = _safe_ratio(direct_opex, total_opex)
        sm_pct = _safe_ratio(sm_payroll, total_opex)
        mkt_pct = _safe_ratio(marketing, total_opex)
        oth_pct = _safe_ratio(other_opex, total_opex)

        # MoM calculations
        rev_mom_usd: Optional[float] = None
        rev_mom_pct: Optional[float] = None
        op_inc_mom_usd: Optional[float] = None
        net_inc_mom_usd: Optional[float] = None

        if prev_metrics is not None and prev_metrics.revenue is not None and rev is not None:
            rev_mom_usd = rev - prev_metrics.revenue
            if prev_metrics.revenue != 0.0:
                rev_mom_pct = (rev - prev_metrics.revenue) / prev_metrics.revenue
            else:
                rev_mom_pct = None  # Zero previous-period revenue returns None

        if prev_metrics is not None and prev_metrics.operating_income is not None and op_inc is not None:
            op_inc_mom_usd = op_inc - prev_metrics.operating_income

        if prev_metrics is not None and prev_metrics.net_income is not None and net_inc is not None:
            net_inc_mom_usd = net_inc - prev_metrics.net_income

        # Optional Balance Sheet Metrics
        cash_val: Optional[float] = None
        ca_val: Optional[float] = None
        cl_val: Optional[float] = None
        wc_val: Optional[float] = None
        cr_val: Optional[float] = None
        ta_val: Optional[float] = None
        tl_val: Optional[float] = None
        te_val: Optional[float] = None

        if bs_stmt is not None and p in bs_stmt.get_period_keys():
            cash_val = bs_stmt.get_item_by_row(15).get_value(p)
            ca_val = bs_stmt.get_item_by_row(27).get_value(p)
            cl_val = bs_stmt.get_item_by_row(54).get_value(p)
            ta_val = bs_stmt.get_item_by_row(37).get_value(p)
            tl_val = bs_stmt.get_item_by_row(59).get_value(p)
            te_val = bs_stmt.get_item_by_row(70).get_value(p)

            if ca_val is not None and cl_val is not None:
                wc_val = ca_val - cl_val
                cr_val = _safe_ratio(ca_val, cl_val)

        m = MonthlyMetrics(
            period=p,
            revenue=rev,
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=cogs,
            gross_profit=gp,
            gross_margin_pct=gm_pct,
            direct_opex=direct_opex,
            sm_payroll=sm_payroll,
            marketing=marketing,
            other_opex=other_opex,
            total_opex=total_opex,
            direct_opex_pct=dir_pct,
            sm_payroll_pct=sm_pct,
            marketing_pct=mkt_pct,
            other_opex_pct=oth_pct,
            operating_income=op_inc,
            operating_margin_pct=op_margin_pct,
            operating_income_mom_change_usd=op_inc_mom_usd,
            net_income=net_inc,
            net_margin_pct=net_margin_pct,
            net_income_mom_change_usd=net_inc_mom_usd,
            cash=cash_val,
            current_assets=ca_val,
            current_liabilities=cl_val,
            working_capital=wc_val,
            current_ratio=cr_val,
            total_assets=ta_val,
            total_liabilities=tl_val,
            total_equity=te_val,
        )

        monthly_dict[p] = m
        prev_metrics = m

    # 3. Trailing-12-Month (TTM) Calculations
    ttm_dict: Dict[str, TTMMetrics] = {}

    for i in range(len(chronological_periods)):
        current_period = chronological_periods[i]
        # Must have at least 12 periods up to this index
        if i >= 11:
            window_periods = chronological_periods[i - 11 : i + 1]
            
            # Reject windows with gaps in calendar continuity
            if not _is_consecutive_calendar_months(window_periods):
                continue

            window_metrics = [monthly_dict[wp] for wp in window_periods]

            # Calculate TTM components safely without zero-coercion
            ttm_rev = _safe_sum([m.revenue for m in window_metrics])
            ttm_cogs = _safe_sum([m.cogs for m in window_metrics])
            ttm_gp = _safe_sum([m.gross_profit for m in window_metrics])
            ttm_gm = _safe_ratio(ttm_gp, ttm_rev)

            ttm_direct = _safe_sum([m.direct_opex for m in window_metrics])
            ttm_sm_pay = _safe_sum([m.sm_payroll for m in window_metrics])
            ttm_mkt = _safe_sum([m.marketing for m in window_metrics])
            ttm_other = _safe_sum([m.other_opex for m in window_metrics])
            ttm_opex = _safe_sum([m.total_opex for m in window_metrics])

            ttm_op_inc = _safe_sum([m.operating_income for m in window_metrics])
            ttm_op_margin = _safe_ratio(ttm_op_inc, ttm_rev)

            ttm_net_inc = _safe_sum([m.net_income for m in window_metrics])
            ttm_net_margin = _safe_ratio(ttm_net_inc, ttm_rev)

            ttm_dict[current_period] = TTMMetrics(
                period=current_period,
                trailing_periods=window_periods,
                revenue=ttm_rev,
                cogs=ttm_cogs,
                gross_profit=ttm_gp,
                gross_margin_pct=ttm_gm,
                direct_opex=ttm_direct,
                sm_payroll=ttm_sm_pay,
                marketing=ttm_mkt,
                other_opex=ttm_other,
                total_opex=ttm_opex,
                operating_income=ttm_op_inc,
                operating_margin_pct=ttm_op_margin,
                net_income=ttm_net_inc,
                net_margin_pct=ttm_net_margin,
            )

    return FinancialMetricsResult(
        monthly_metrics=monthly_dict,
        ttm_metrics=ttm_dict,
    )
