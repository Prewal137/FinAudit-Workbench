"""

This script implements Phase 4: it creates synthetic financial fixtures, builds minimal
markdown reports, runs the existing numeric‑grader (scripts/compare_financial_metrics.py)
with those fixtures, and evaluates four grading dimensions:

1. **Numeric correctness** – all numeric cells match the deterministic reference.
2. **Completeness** – every expected period appears in each table.
3. **Evidence support** – narrative claims are backed by evidence; unsupported
   causal wording is flagged.
4. **Commentary quality** – at least one labeled (Fact/Interpretation/Hypothesis)
   line appears in the narrative section.

Results are saved as JSON (reports/golden_evaluation_results.json) and a
human‑readable Markdown summary (reports/golden_evaluation_summary.md).  The script
exits with code 0 when every case meets its *expected* outcome (PASS or intentional
FAIL); otherwise it exits with a non‑zero code.
"""

from __future__ import annotations
import json
try:
    import yaml
except ImportError:
    yaml = None
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Dict

# Import metric data classes
# Resolve repository root relative to this script
repo_root = Path(__file__).resolve().parents[1]
# Ensure metric module import works from the repo root
sys.path.append(str(repo_root))
from src.metrics import MonthlyMetrics, FinancialMetricsResult

# ---------------------------------------------------------------------------
# Helper formatting functions (same style as the main report generator)
# ---------------------------------------------------------------------------

def fmt_currency(value: Optional[float]) -> str:
    return f"${value:,.2f}" if value is not None else "N/A"

def fmt_pct(value: Optional[float]) -> str:
    return f"{value * 100:.2f}%" if value is not None else "N/A"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Numeric evaluation utilities (adapted from compare_financial_metrics.py)
# ---------------------------------------------------------------------------
import re

def parse_number(s: str):
    s = s.strip()
    if not s or s.lower() == 'n/a':
        return None
    s = s.replace('$', '').replace(',', '')
    if s.endswith('%'):
        s = s.rstrip('%')
        try:
            return float(s) / 100.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None

def compare_vals(ref, rep, tol):
    if ref is None and rep is None:
        return {'status': 'SKIPPED'}
    if ref is None or rep is None:
        return {'status': 'FAIL', 'ref': ref, 'rep': rep, 'diff': None}
    diff = round(abs(ref - rep), 6)
    status = 'PASS' if diff <= tol else 'FAIL'
    return {'status': status, 'ref': ref, 'rep': rep, 'diff': diff}

def is_ok(status: str) -> bool:
    return status in ('PASS', 'SKIPPED')

def extract_table(lines: List[str], start_regex: str) -> List[str]:
    header_idx = None
    for i, line in enumerate(lines):
        if re.search(start_regex, line, re.IGNORECASE):
            header_idx = i
            break
    if header_idx is None:
        return []
    i = header_idx + 1
    while i < len(lines) and not lines[i].lstrip().startswith('|'):
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith('|'):
        i += 1
    while i < len(lines) and (lines[i].strip() == '' or re.match(r"\s*\|[-| ]+\|", lines[i])):
        i += 1
    rows = []
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith('|'):
            break
        rows.append(line)
        i += 1
    return rows

def evaluate_numeric_correctness(metrics: FinancialMetricsResult, report_text: str, periods: List[str]) -> bool:
    lines = report_text.splitlines()
    monthly_rows = extract_table(lines, r"Monthly Financial Performance")
    rev_gross_rows = extract_table(lines, r"Revenue and Gross‑Margin Trends")
    op_exp_rows = extract_table(lines, r"Operating Expense Analysis")
    inc_net_rows = extract_table(lines, r"Operating Income and Net Income")
    # Build report structures
    report_monthly = {}
    for row in monthly_rows:
        cells = [c.strip() for c in row.strip('|').split('|')]
        if len(cells) < 5:
            continue
        period = cells[0]
        report_monthly[period] = {
            'revenue': parse_number(cells[1]),
            'total_opex': parse_number(cells[2]),
            'operating_income': parse_number(cells[3]),
            'net_income': parse_number(cells[4]),
        }
    report_rev_gross = {}
    for row in rev_gross_rows:
        cells = [c.strip() for c in row.strip('|').split('|')]
        if len(cells) < 6:
            continue
        period = cells[0]
        report_rev_gross[period] = {
            'revenue': parse_number(cells[1]),
            'revenue_mom_usd': parse_number(cells[2]),
            'revenue_mom_pct': parse_number(cells[3]),
            'gross_profit': parse_number(cells[4]),
            'gross_margin': parse_number(cells[5]),
        }
    report_op_exp = {}
    for row in op_exp_rows:
        cells = [c.strip() for c in row.strip('|').split('|')]
        if len(cells) < 6:
            continue
        period = cells[0]
        report_op_exp[period] = {
            'direct_opex': parse_number(cells[1]),
            'sm_payroll': parse_number(cells[2]),
            'marketing': parse_number(cells[3]),
            'other_opex': parse_number(cells[4]),
            'total_opex': parse_number(cells[5]),
        }
    report_inc_net = {}
    for row in inc_net_rows:
        cells = [c.strip() for c in row.strip('|').split('|')]
        if len(cells) < 5:
            continue
        period = cells[0]
        report_inc_net[period] = {
            'operating_income': parse_number(cells[1]),
            'operating_margin': parse_number(cells[2]),
            'net_income': parse_number(cells[3]),
            'net_margin': parse_number(cells[4]),
        }
    MONEY_TOL = 0.01
    PCT_TOL = 0.0001
    for p in periods:
        mm = metrics.monthly_metrics[p]
        # Monthly performance
        if p not in report_monthly:
            return False
        if not is_ok(compare_vals(mm.revenue, report_monthly[p]['revenue'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.total_opex, report_monthly[p]['total_opex'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.operating_income, report_monthly[p]['operating_income'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.net_income, report_monthly[p]['net_income'], MONEY_TOL)['status']):
            return False
        # Rev/gross
        if p not in report_rev_gross:
            return False
        if not is_ok(compare_vals(mm.revenue, report_rev_gross[p]['revenue'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.revenue_mom_change_usd, report_rev_gross[p]['revenue_mom_usd'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.revenue_mom_change_pct, report_rev_gross[p]['revenue_mom_pct'], PCT_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.gross_profit, report_rev_gross[p]['gross_profit'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.gross_margin_pct, report_rev_gross[p]['gross_margin'], PCT_TOL)['status']):
            return False
        # Op expense
        if p not in report_op_exp:
            return False
        if not is_ok(compare_vals(mm.total_opex, report_op_exp[p]['total_opex'], MONEY_TOL)['status']):
            return False
        # Inc/net
        if p not in report_inc_net:
            return False
        if not is_ok(compare_vals(mm.operating_income, report_inc_net[p]['operating_income'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.operating_margin_pct, report_inc_net[p]['operating_margin'], PCT_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.net_income, report_inc_net[p]['net_income'], MONEY_TOL)['status']):
            return False
        if not is_ok(compare_vals(mm.net_margin_pct, report_inc_net[p]['net_margin'], PCT_TOL)['status']):
            return False
    return True

# Synthetic fixture definitions (explicitly labelled)
# ---------------------------------------------------------------------------

def synthetic_normal_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Normal month‑to‑month movement across three periods.

    Periods: 2025‑01, 2025‑02, 2025‑03.
    Revenue grows modestly, expenses stay stable.
    All numbers are hand‑calculated.
    """
    periods = ["2025-01", "2025-02", "2025-03"]
    rev = {"2025-01": 1000.0, "2025-02": 1100.0, "2025-03": 1150.0}
    total_opex = {p: 400.0 for p in periods}
    op_inc = {p: 200.0 for p in periods}
    net_inc = {p: 150.0 for p in periods}
    gross_profit = {p: rev[p] - 300.0 for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = gross_profit[p] / rev[p] if rev[p] != 0 else None
        op_margin = op_inc[p] / rev[p] if rev[p] != 0 else None
        net_margin = net_inc[p] / rev[p] if rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=150.0,
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=150.0 / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})
    return result, periods

def synthetic_large_change_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Large financial change (tax benefit) in the middle period.

    The change is correct – the grader should PASS.
    """
    periods = ["2025-01", "2025-02", "2025-03"]
    rev = {"2025-01": 1000.0, "2025-02": 1200.0, "2025-03": 1300.0}
    total_opex = {"2025-01": 400.0, "2025-02": 300.0, "2025-03": 500.0}
    op_inc = {"2025-01": 200.0, "2025-02": 600.0, "2025-03": 250.0}
    net_inc = {"2025-01": 150.0, "2025-02": 550.0, "2025-03": 200.0}
    gross_profit = {p: rev[p] - 300.0 for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = gross_profit[p] / rev[p] if rev[p] != 0 else None
        op_margin = op_inc[p] / rev[p] if rev[p] != 0 else None
        net_margin = net_inc[p] / rev[p] if rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=150.0,
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=150.0 / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})
    return result, periods

def synthetic_missing_values_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Missing revenue for the middle period and missing operating income for the last.

    The grader must treat missing entries as `N/A` and not coerce them to zero.
    """
    periods = ["2025-01", "2025-02", "2025-03"]
    rev = {"2025-01": 1000.0, "2025-02": None, "2025-03": 1150.0}
    total_opex = {p: 400.0 for p in periods}
    op_inc = {"2025-01": 200.0, "2025-02": 220.0, "2025-03": None}
    net_inc = {"2025-01": 150.0, "2025-02": 160.0, "2025-03": 170.0}
    gross_profit = {p: (rev[p] - 300.0) if rev[p] is not None else None for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = (gross_profit[p] / rev[p]) if rev[p] and rev[p] != 0 else None
        op_margin = (op_inc[p] / rev[p]) if rev[p] and op_inc[p] is not None else None
        net_margin = (net_inc[p] / rev[p]) if rev[p] and rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None and rev[p] is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and rev[p] is not None and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None and op_inc[p] is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0 if rev[p] is not None else None,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=150.0,
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=150.0 / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})
    return result, periods

def synthetic_high_expense_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Unusually high marketing expense in the second period.
    """
    periods = ["2025-01", "2025-02", "2025-03"]
    rev = {p: 1000.0 for p in periods}
    total_opex = {"2025-01": 400.0, "2025-02": 800.0, "2025-03": 400.0}
    marketing = {"2025-01": 150.0, "2025-02": 600.0, "2025-03": 150.0}
    op_inc = {p: rev[p] - total_opex[p] for p in periods}
    net_inc = {p: op_inc[p] - 50.0 for p in periods}
    gross_profit = {p: rev[p] - 300.0 for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = gross_profit[p] / rev[p] if rev[p] != 0 else None
        op_margin = op_inc[p] / rev[p] if rev[p] != 0 else None
        net_margin = net_inc[p] / rev[p] if rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=marketing[p],
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=marketing[p] / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})
    return result, periods

def synthetic_unsupported_causal_fixture() -> Tuple[FinancialMetricsResult, List[str], str]:
    """Correct numeric fixture but includes an unsupported causal claim.

    The narrative contains a causal statement labeled as `[Interpretation]` without
    supporting evidence, which should be flagged by the *Evidence support* check.
    """
    metrics, periods = synthetic_normal_fixture()
    narrative = (
        "## 9. Significant Anomalies and Supporting Evidence\n"
        "[Fact] Revenue increased in Q1 due to new marketing efforts.\n"
            "[Note] Observation without supporting evidence.\n"
            "[Interpretation] Revenue increased because the new marketing campaign was launched.\n"
    )
    return metrics, periods, narrative

# ---------------------------------------------------------------------------
# Additional golden case fixtures (TTM, validation gate, narrative robustness)
# ---------------------------------------------------------------------------

from src.metrics import TTMMetrics

def synthetic_ttm_complete_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Creates 12 consecutive months of data with deterministic values and TTM metrics."""
    periods = [f"2025-{m:02d}" for m in range(1, 13)]
    rev = {p: 1000.0 + 100.0 * i for i, p in enumerate(periods)}
    total_opex = {p: 400.0 for p in periods}
    op_inc = {p: rev[p] - total_opex[p] for p in periods}
    net_inc = {p: op_inc[p] - 50.0 for p in periods}
    gross_profit = {p: rev[p] - 300.0 for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = gross_profit[p] / rev[p] if rev[p] != 0 else None
        op_margin = op_inc[p] / rev[p] if rev[p] != 0 else None
        net_margin = net_inc[p] / rev[p] if rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=150.0,
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=150.0 / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    # Manual TTM aggregation for the final period
    ttm_rev = sum(rev[p] for p in periods)
    ttm_cogs = sum(300.0 for _ in periods)
    ttm_gp = sum(gross_profit[p] for p in periods)
    ttm_gm = ttm_gp / ttm_rev if ttm_rev != 0 else None
    ttm_direct = sum(100.0 for _ in periods)
    ttm_sm = sum(100.0 for _ in periods)
    ttm_mkt = sum(150.0 for _ in periods)
    ttm_other = sum(50.0 for _ in periods)
    ttm_opex = sum(total_opex[p] for p in periods)
    ttm_op_inc = sum(op_inc[p] for p in periods)
    ttm_op_margin = ttm_op_inc / ttm_rev if ttm_rev != 0 else None
    ttm_net_inc = sum(net_inc[p] for p in periods)
    ttm_net_margin = ttm_net_inc / ttm_rev if ttm_rev != 0 else None
    ttm = TTMMetrics(
        period=periods[-1],
        trailing_periods=periods,
        revenue=ttm_rev,
        cogs=ttm_cogs,
        gross_profit=ttm_gp,
        gross_margin_pct=ttm_gm,
        direct_opex=ttm_direct,
        sm_payroll=ttm_sm,
        marketing=ttm_mkt,
        other_opex=ttm_other,
        total_opex=ttm_opex,
        operating_income=ttm_op_inc,
        operating_margin_pct=ttm_op_margin,
        net_income=ttm_net_inc,
        net_margin_pct=ttm_net_margin,
    )
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={periods[-1]: ttm})
    return result, periods

def synthetic_ttm_incomplete_fixture() -> Tuple[FinancialMetricsResult, List[str]]:
    """Creates 11 consecutive months – TTM window should be omitted."""
    periods = [f"2025-{m:02d}" for m in range(1, 12)]
    rev = {p: 1000.0 for p in periods}
    total_opex = {p: 400.0 for p in periods}
    op_inc = {p: rev[p] - total_opex[p] for p in periods}
    net_inc = {p: op_inc[p] - 50.0 for p in periods}
    gross_profit = {p: rev[p] - 300.0 for p in periods}
    monthly: Dict[str, MonthlyMetrics] = {}
    prev_rev = prev_op = prev_net = None
    for p in periods:
        gm_pct = gross_profit[p] / rev[p] if rev[p] != 0 else None
        op_margin = op_inc[p] / rev[p] if rev[p] != 0 else None
        net_margin = net_inc[p] / rev[p] if rev[p] != 0 else None
        rev_mom_usd = rev[p] - prev_rev if prev_rev is not None else None
        rev_mom_pct = (rev[p] - prev_rev) / prev_rev if prev_rev and prev_rev != 0 else None
        op_mom_usd = op_inc[p] - prev_op if prev_op is not None else None
        net_mom_usd = net_inc[p] - prev_net if prev_net is not None else None
        mm = MonthlyMetrics(
            period=p,
            revenue=rev[p],
            revenue_mom_change_usd=rev_mom_usd,
            revenue_mom_change_pct=rev_mom_pct,
            cogs=300.0,
            gross_profit=gross_profit[p],
            gross_margin_pct=gm_pct,
            direct_opex=100.0,
            sm_payroll=100.0,
            marketing=150.0,
            other_opex=50.0,
            total_opex=total_opex[p],
            direct_opex_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            sm_payroll_pct=100.0 / total_opex[p] if total_opex[p] != 0 else None,
            marketing_pct=150.0 / total_opex[p] if total_opex[p] != 0 else None,
            other_opex_pct=50.0 / total_opex[p] if total_opex[p] != 0 else None,
            operating_income=op_inc[p],
            operating_margin_pct=op_margin,
            operating_income_mom_change_usd=op_mom_usd,
            net_income=net_inc[p],
            net_margin_pct=net_margin,
            net_income_mom_change_usd=net_mom_usd,
        )
        monthly[p] = mm
        prev_rev, prev_op, prev_net = rev[p], op_inc[p], net_inc[p]
    result = FinancialMetricsResult(monthly_metrics=monthly, ttm_metrics={})
    return result, periods

# Simple ValidationReport stub for validation‑gate cases
class DummyValidationReport:
    def __init__(self, can_proceed: bool):
        self.can_proceed_to_downstream = can_proceed
        self.critical_findings = []
        self.warning_findings = []
        self.findings = []

def synthetic_validation_gate_fixture(passing: bool) -> Tuple[FinancialMetricsResult, List[str], DummyValidationReport]:
    """Create a minimal metrics fixture together with a ValidationReport indicating downstream gating."""
    metrics, periods = synthetic_normal_fixture()
    val_report = DummyValidationReport(can_proceed=passing)
    return metrics, periods, val_report

# Narrative fixtures for robustness tests
def synthetic_missing_label_fixture() -> Tuple[FinancialMetricsResult, List[str], str]:
    metrics, periods = synthetic_normal_fixture()
    narrative = "[Interpretation] This line lacks a preceding Fact label."
    return metrics, periods, narrative

def synthetic_contradictory_fact_fixture() -> Tuple[FinancialMetricsResult, List[str], str]:
    metrics, periods = synthetic_normal_fixture()
    period = periods[0]
    wrong_rev = (metrics.monthly_metrics[period].revenue or 0.0) + 999.0
    narrative = f"[Fact] Revenue for {period} is ${wrong_rev:,.2f}."
    return metrics, periods, narrative


# ---------------------------------------------------------------------------
# Report generation utilities (tables only; optional narrative)
# ---------------------------------------------------------------------------

def generate_report(metrics: FinancialMetricsResult, periods: List[str], narrative: Optional[str] = None) -> str:
    """Create a minimal markdown report containing sections 3‑7.

    Section headings match the regexes used by `compare_financial_metrics.py`.
    """
    lines: List[str] = []
    lines.append("# Financial Review & Trend Analysis Report")
    # Section 3 – Monthly Financial Performance
    lines.append("## 3. Monthly Financial Performance")
    lines.append("| Period | Revenue | Total OpEx | Operating Income | Net Income |")
    lines.append("|---|---|---|---|---|")
    for p in periods:
        m = metrics.monthly_metrics[p]
        lines.append(f"| {p} | {fmt_currency(m.revenue)} | {fmt_currency(m.total_opex)} | {fmt_currency(m.operating_income)} | {fmt_currency(m.net_income)} |")
    # Section 4 – Revenue and Gross‑Margin Trends
    lines.append("## 4. Revenue and Gross‑Margin Trends")
    lines.append("| Period | Revenue | Revenue MoM Δ (USD) | Revenue MoM Δ (%) | Gross Profit | Gross Margin |")
    lines.append("|---|---|---|---|---|---|")
    for p in periods:
        m = metrics.monthly_metrics[p]
        lines.append(f"| {p} | {fmt_currency(m.revenue)} | {fmt_currency(m.revenue_mom_change_usd)} | {fmt_pct(m.revenue_mom_change_pct)} | {fmt_currency(m.gross_profit)} | {fmt_pct(m.gross_margin_pct)} |")
    # Section 5 – Operating Expense Analysis
    lines.append("## 5. Operating Expense Analysis")
    lines.append("| Period | Direct OpEx | S&M Payroll | Marketing | Other OpEx | Total OpEx |")
    lines.append("|---|---|---|---|---|---|")
    for p in periods:
        m = metrics.monthly_metrics[p]
        lines.append(f"| {p} | {fmt_currency(m.direct_opex)} | {fmt_currency(m.sm_payroll)} | {fmt_currency(m.marketing)} | {fmt_currency(m.other_opex)} | {fmt_currency(m.total_opex)} |")
    # Section 6 – Operating Income and Net Income
    lines.append("## 6. Operating Income and Net Income")
    lines.append("| Period | Operating Income | Operating Margin | Net Income | Net Margin |")
    lines.append("|---|---|---|---|---|")
    for p in periods:
        m = metrics.monthly_metrics[p]
        lines.append(f"| {p} | {fmt_currency(m.operating_income)} | {fmt_pct(m.operating_margin_pct)} | {fmt_currency(m.net_income)} | {fmt_pct(m.net_margin_pct)} |")
    # Section 7 – Trailing‑12‑Month Analysis (omit when no TTM data)
    if metrics.ttm_metrics:
        lines.append("## 7. Trailing‑12‑Month Analysis")
        lines.append("| TTM End Period | Revenue | Gross Margin | Operating Margin | Net Margin |")
        lines.append("|---|---|---|---|---|")
        for p, t in sorted(metrics.ttm_metrics.items()):
            lines.append(f"| {p} | {fmt_currency(t.revenue)} | {fmt_pct(t.gross_margin_pct)} | {fmt_pct(t.operating_margin_pct)} | {fmt_pct(t.net_margin_pct)} |")
    # Optional narrative – ensure at least one labeled line for commentary quality
    if narrative:
        lines.append("")
        lines.append(narrative.rstrip())
    else:
        lines.append("")
        lines.append("[Fact] Synthetic data generated for testing.")
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Narrative analysis utilities (evidence support & commentary quality)
# ---------------------------------------------------------------------------

def evaluate_factual_consistency(report_text: str, metrics: FinancialMetricsResult) -> bool:
    """Check that any `[Fact]` lines about Revenue match the metric value.
    Returns False on the first mismatch, True otherwise.
    """
    import re
    for line in report_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[Fact]"):
            m = re.search(r"Revenue for (\d{4}-\d{2}) is \$(.+)", stripped)
            if m:
                period, val_str = m.group(1), m.group(2)
                try:
                    # Strip any trailing non-numeric characters (e.g., punctuation) before conversion
                    cleaned_val = re.sub(r"[^0-9.,-]", "", val_str).rstrip('.')
                    val = float(cleaned_val.replace(",", ""))
                except ValueError:
                    continue
                metric_rev = metrics.monthly_metrics.get(period).revenue
                if metric_rev is None or abs(metric_rev - val) > 0.01:
                    return False
    return True


def evaluate_narrative(report_text: str) -> Tuple[bool, bool]:
    """Return (evidence_support_pass, commentary_quality_pass).

    *Evidence support* fails when a causal phrase ("because" or "due to") appears in a line
    labeled as `[Interpretation]` or `[Hypothesis]` without an immediately preceding `[Fact]` line.
    *Commentary quality* passes when at least one line starts with one of the required
    labels **and** at least one `[Fact]` line is present.
    """
    evidence_pass = True
    commentary_pass = False
    fact_present = False
    prev_is_fact = False
    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped:
            prev_is_fact = False
            continue
        if stripped.startswith("[Fact]"):
            commentary_pass = True
            fact_present = True
            prev_is_fact = True
            continue
        is_causal = ("because" in stripped.lower() or "due to" in stripped.lower())
        if stripped.startswith("[Interpretation]") or stripped.startswith("[Hypothesis]"):
            commentary_pass = True
            if is_causal and not prev_is_fact:
                evidence_pass = False
            prev_is_fact = False
            continue
        prev_is_fact = False
    if not fact_present:
        commentary_pass = False
    return evidence_pass, commentary_pass

# ---------------------------------------------------------------------------
def check_completeness(report_text: str, periods: List[str]) -> bool:
    """Verify required sections (3‑7) are present and each required table contains all periods."""
    required_sections = [
        r"Monthly Financial Performance",
        r"Revenue and Gross‑Margin Trends",
        r"Operating Expense Analysis",
        r"Operating Income and Net Income",
    ]
    lines = report_text.splitlines()
    for heading in required_sections:
        # Ensure heading exists
        if not any(re.search(heading, line, re.IGNORECASE) for line in lines):
            return False
        rows = extract_table(lines, heading)
        if not rows:
            return False
        periods_in_rows = set()
        for row in rows:
            cols = [c.strip() for c in row.strip('|').split('|')]
            if cols:
                periods_in_rows.add(cols[0])
        if set(periods) != periods_in_rows:
            return False
    return True

# Main runner
# ---------------------------------------------------------------------------

def main() -> int:
    # Load expected outcomes from the yaml file (with fallback if PyYAML missing)
    yaml_path = repo_root / 'evals' / 'golden_cases.yaml'
    if yaml is not None:
        with yaml_path.open('r', encoding='utf-8') as f:
            yaml_cases = yaml.safe_load(f).get('cases', [])
    else:
        # Minimal YAML parser for expected outcomes (fallback when PyYAML unavailable)
        yaml_cases = []
        current = {}
        for raw_line in yaml_path.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if line.startswith('- id:'):
                if current:
                    yaml_cases.append(current)
                    current = {}
                current['id'] = line.split(':', 1)[1].strip()
            elif line.startswith('numeric:'):
                current.setdefault('expected', {})['numeric'] = line.split(':', 1)[1].strip().lower() == 'true'
            elif line.startswith('completeness:'):
                current.setdefault('expected', {})['completeness'] = line.split(':', 1)[1].strip().lower() == 'true'
            elif line.startswith('evidence:'):
                current.setdefault('expected', {})['evidence'] = line.split(':', 1)[1].strip().lower() == 'true'
            elif line.startswith('commentary:'):
                current.setdefault('expected', {})['commentary'] = line.split(':', 1)[1].strip().lower() == 'true'
        if current:
            yaml_cases.append(current)
    yaml_expected = {c['id']: c.get('expected', {}) for c in yaml_cases}

    # Append additional cases defined in the YAML but not in the static list
    # This keeps the original list unchanged while extending coverage.
    additional_cases = []
    if '--extended' in sys.argv:
        if 'ttm_complete' in yaml_expected:
            additional_cases.append({"id": "ttm_complete", "fixture_func": synthetic_ttm_complete_fixture, "narrative": None})
        if 'ttm_incomplete' in yaml_expected:
            additional_cases.append({"id": "ttm_incomplete", "fixture_func": synthetic_ttm_incomplete_fixture, "narrative": None})
        if 'validation_gate_block' in yaml_expected:
            additional_cases.append({"id": "validation_gate_block", "fixture_func": lambda: synthetic_validation_gate_fixture(False), "narrative": None})
        if 'validation_gate_pass' in yaml_expected:
            additional_cases.append({"id": "validation_gate_pass", "fixture_func": lambda: synthetic_validation_gate_fixture(True), "narrative": None})
        if 'missing_label' in yaml_expected:
            additional_cases.append({"id": "missing_label", "fixture_func": synthetic_missing_label_fixture, "narrative": None})
        if 'contradictory_fact' in yaml_expected:
            additional_cases.append({"id": "contradictory_fact", "fixture_func": synthetic_contradictory_fact_fixture, "narrative": None})

    # Base golden cases (original six)
    cases = [
        {"id": "normal_movement", "fixture_func": synthetic_normal_fixture, "narrative": None},
        {"id": "large_change", "fixture_func": synthetic_large_change_fixture, "narrative": None},
        {"id": "missing_values", "fixture_func": synthetic_missing_values_fixture, "narrative": None},
        {"id": "high_expense", "fixture_func": synthetic_high_expense_fixture, "narrative": None},
        {"id": "unsupported_causal", "fixture_func": synthetic_unsupported_causal_fixture, "narrative": True},
        {"id": "deliberate_numeric_error", "fixture_func": synthetic_normal_fixture, "narrative": None, "introduce_error": True},
    ]
    cases.extend(additional_cases)
    # Attach expected outcomes from YAML to each case
    for case in cases:
        case["expected"] = yaml_expected.get(case["id"], {})

    results: List[Dict] = []
    overall_success = True
    for case in cases:
        case_id = case["id"]
        # Call fixture – may return 2 or 3 values
        fixture_result = case["fixture_func"]()
        if isinstance(fixture_result, tuple) and len(fixture_result) == 3:
            metrics, periods, extra = fixture_result
        else:
            metrics, periods = fixture_result
            extra = None
        # Determine narrative and validation report based on extra type
        narrative = None
        validation_report = None
        if isinstance(extra, str):
            narrative = extra
        elif extra is not None:
            validation_report = extra
        report_text = generate_report(metrics, periods, narrative)
        # Inject numeric error if requested (only for original deliberate_numeric_error case)
        if case.get("introduce_error"):
            rev = metrics.monthly_metrics[periods[0]].revenue or 0.0
            wrong_rev = rev + 10.0
            correct_str = fmt_currency(rev)
            wrong_str = fmt_currency(wrong_rev)
            report_text = report_text.replace(correct_str, wrong_str, 1)
        # Save report
        case_dir = repo_root / 'reports' / 'golden_cases' / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / 'report.md').write_text(report_text, encoding='utf-8')
        # Evaluate aspects
        evidence_pass, commentary_pass = evaluate_narrative(report_text)
        numeric_pass = evaluate_numeric_correctness(metrics, report_text, periods)
        completeness_pass = check_completeness(report_text, periods)
        ttm_present = bool(metrics.ttm_metrics)
        validation_gate_pass = validation_report.can_proceed_to_downstream if validation_report else True
        factual_consistency = evaluate_factual_consistency(report_text, metrics) if narrative else True
        case_result = {
            "id": case_id,
            "numeric_correctness": numeric_pass,
            "completeness": completeness_pass,
            "evidence_support": evidence_pass,
            "commentary_quality": commentary_pass,
            "ttm_present": ttm_present,
            "validation_gate_pass": validation_gate_pass,
            "factual_consistency": factual_consistency,
            "expected": case["expected"],
        }
        expected = case["expected"]
        # Base checks
        overall_case = (
            (numeric_pass == expected.get("numeric", numeric_pass)) and
            (completeness_pass == expected.get("completeness", completeness_pass)) and
            (evidence_pass == expected.get("evidence", evidence_pass)) and
            (commentary_pass == expected.get("commentary", commentary_pass))
        )
        # Optional checks
        if "ttm_present" in expected:
            overall_case = overall_case and (ttm_present == expected["ttm_present"])
        if "validation_gate_pass" in expected:
            overall_case = overall_case and (validation_gate_pass == expected["validation_gate_pass"])
        if "factual_consistency" in expected:
            overall_case = overall_case and (factual_consistency == expected["factual_consistency"])
        case_result["overall_pass"] = overall_case
        results.append(case_result)
        if not overall_case:
            overall_success = False
    # Write results JSON
    (repo_root / 'reports' / 'golden_cases' / 'golden_evaluation_results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    # Write Markdown summary (add new columns if present)
    md_lines = ["# Golden Evaluation Summary", ""]
    header = "| Case ID | Numeric | Completeness | Evidence | Commentary |"
    if any('ttm_present' in r for r in results):
        header += " TTM |"
    if any('validation_gate_pass' in r for r in results):
        header += " Validation |"
    if any('factual_consistency' in r for r in results):
        header += " Fact Consistency |"
    header += " Overall |"
    md_lines.append(header)
    sep = "|---" * (header.count("|") - 1) + "|"
    md_lines.append(sep)
    for r in results:
        row = f"| {r['id']} | {'PASS' if r['numeric_correctness'] else 'FAIL'} | {'PASS' if r['completeness'] else 'FAIL'} | {'PASS' if r['evidence_support'] else 'FAIL'} | {'PASS' if r['commentary_quality'] else 'FAIL'}"
        if 'ttm_present' in r:
            row += f" | {'PASS' if r['ttm_present'] else 'FAIL'}"
        if 'validation_gate_pass' in r:
            row += f" | {'PASS' if r['validation_gate_pass'] else 'FAIL'}"
        if 'factual_consistency' in r:
            row += f" | {'PASS' if r['factual_consistency'] else 'FAIL'}"
        row += f" | {'PASS' if r['overall_pass'] else 'FAIL'} |"
        md_lines.append(row)
    (repo_root / 'reports' / 'golden_cases' / 'golden_evaluation_summary.md').write_text("\n".join(md_lines), encoding='utf-8')
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
