import sys
import pathlib
import importlib.util
import calendar
from datetime import datetime

repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

# Load workbook metrics
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics

# Locate workbook
workbook_candidates = list((repo_root / "data" / "input").glob("*.xlsx"))
if len(workbook_candidates) != 1:
    raise FileNotFoundError(f"Expected exactly one workbook, found {len(workbook_candidates)}")
WORKBOOK_PATH = workbook_candidates[0]

is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
metrics = calculate_financial_metrics(is_stmt, bs_stmt)

# Helper to get month start/end strings
def month_range(year_month: str):
    year, month = map(int, year_month.split("-"))
    start = f"{year_month}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year_month}-{last_day:02d}"
    return start, end

# Import live QB helpers
live_mod_path = repo_root / "scripts" / "live_qb_financial_trend_report.py"
spec = importlib.util.spec_from_file_location("live_qb", str(live_mod_path))
live_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_mod)

# Get live P&L data for given month
from integrations.qbo_mcp_server import get_profit_and_loss

def get_live_metrics_for_months(months):
    normalized = []
    for m in months:
        start, end = month_range(m)
        pnl = get_profit_and_loss(start, end)
        normalized.append(live_mod.normalise_pnl(pnl))
    return live_mod.build_metrics_from_quickbooks(normalized)

# Compare Jan and Feb 2025
months_to_compare = ["2025-01", "2025-02"]
live_metrics = get_live_metrics_for_months(months_to_compare)

# Helper for tolerance
TOL = 0.01

def compare_field(wb_val, live_val):
    diff = None if wb_val is None or live_val is None else abs(wb_val - live_val)
    match = diff is not None and diff <= TOL
    return diff, match

def fmt(val):
    return f"{val:.2f}" if isinstance(val, (int, float)) else str(val)

print("--- Comparison Jan/Feb 2025 (Workbook vs Live QuickBooks) ---")
print(f"{'Metric':<25}{'Workbook':>15}{'Live QB':>15}{'Diff':>10}{'Match':>8}")
for period in months_to_compare:
    wb = metrics.monthly_metrics.get(period)
    live = live_metrics.monthly_metrics.get(period)
    if not wb or not live:
        continue
    for field in [
        "revenue",
        "gross_profit",
        "total_opex",
        "operating_income",
        "net_income",
        "gross_margin_pct",
        "operating_margin_pct",
        "net_margin_pct",
    ]:
        wb_val = getattr(wb, field, None)
        live_val = getattr(live, field, None)
        diff, match = compare_field(wb_val, live_val)
        row = [period, field, fmt(wb_val), fmt(live_val), fmt(diff) if diff is not None else "N/A", str(match)]
        print("{:<8} {:<20} {:>15} {:>15} {:>10} {:>8}".format(*row))

# December 2025 investigation
dec_month = "2025-12"
live_dec = get_live_metrics_for_months([dec_month])
ld = live_dec.monthly_metrics.get(dec_month)
print("\n--- December 2025 Live QuickBooks Metrics ---")
print(f"Operating Income: {ld.operating_income}")
print(f"Net Income: {ld.net_income}")
if ld.net_income is not None and ld.operating_income is not None and ld.net_income > 0 and ld.operating_income < 0:
    print("*** Flag: Positive Net Income with Negative Operating Income – requires review ***")

# Read live report to check anomalies and validation gate
report_path = repo_root / "reports" / "financial-trend-analysis_live_qb_report.md"
if report_path.is_file():
    content = report_path.read_text(encoding="utf-8")
    # Simple checks
    if "## 2. Data Coverage and Validation Status" in content:
        start = content.find("## 2. Data Coverage and Validation Status")
        end = content.find("##", start + 1)
        section = content[start:end] if end != -1 else content[start:]
        print("\n--- Validation Status Section ---")
        print(section.strip())
    if "## 9. Significant Anomalies" in content:
        start = content.find("## 9. Significant Anomalies")
        end = content.find("##", start + 1)
        section = content[start:end] if end != -1 else content[start:]
        print("\n--- Anomalies Section ---")
        print(section.strip())
else:
    print("Live report file not found.")
