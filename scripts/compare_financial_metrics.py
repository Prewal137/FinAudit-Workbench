import json, pathlib, re, sys

# Paths
repo_root = pathlib.Path('.').resolve()
report_path = repo_root / 'reports' / 'financial-trend-analysis_report.md'
output_json = repo_root / 'reports' / 'financial_metrics_comparison.json'
output_md = repo_root / 'reports' / 'financial_metrics_comparison.md'

# Load deterministic metrics using the project's code
sys.path.append(str(repo_root))
from src.ingestion import load_financial_workbook
from src.metrics import calculate_financial_metrics

wb_path = repo_root / 'data' / 'input' / 'ABC Inc - Financial Statements.xlsx'
is_stmt, bs_stmt = load_financial_workbook(wb_path)
metrics = calculate_financial_metrics(is_stmt, bs_stmt)

# Helper to normalize numbers from markdown (remove $ and commas, %)
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

# Read markdown report
with report_path.open(encoding='utf-8') as f:
    md_text = f.read()
lines = md_text.splitlines()

def extract_table(start_regex: str):
    # Locate the heading line containing the table name
    header_idx = None
    for i, line in enumerate(lines):
        if re.search(start_regex, line, re.IGNORECASE):
            header_idx = i
            break
    if header_idx is None:
        return []
    # Move forward to the first line that starts a markdown table (a line beginning with '|')
    i = header_idx + 1
    while i < len(lines) and not lines[i].lstrip().startswith('|'):
        i += 1
    # At this point, lines[i] should be the header row of the table.
    # Skip the header row
    if i < len(lines) and lines[i].lstrip().startswith('|'):
        i += 1  # skip header
    # Skip any blank lines before the separator and the separator row if present
    while i < len(lines) and (lines[i].strip() == "" or re.match(r"\s*\|[-| ]+\|", lines[i])):
        i += 1
    rows = []
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith('|'):
            break
        rows.append(line)
        i += 1
    return rows

monthly_perf_rows = extract_table(r"Monthly Financial Performance")
rev_gross_rows = extract_table(r"Revenue and Gross‑Margin Trends")
op_exp_rows = extract_table(r"Operating Expense Analysis")
inc_net_rows = extract_table(r"Operating Income and Net Income")
ttm_rows = extract_table(r"Trailing‑12‑Month Analysis")

def split_cells(row: str):
    return [c.strip() for c in row.strip('|').split('|')]

# Build dictionaries from the report tables
report_monthly = {}
for row in monthly_perf_rows:
    cells = split_cells(row)
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
    cells = split_cells(row)
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
    cells = split_cells(row)
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
    cells = split_cells(row)
    if len(cells) < 5:
        continue
    period = cells[0]
    report_inc_net[period] = {
        'operating_income': parse_number(cells[1]),
        'operating_margin': parse_number(cells[2]),
        'net_income': parse_number(cells[3]),
        'net_margin': parse_number(cells[4]),
    }

report_ttm = {}
for row in ttm_rows:
    cells = split_cells(row)
    if len(cells) < 5:
        continue
    period = cells[0]
    report_ttm[period] = {
        'revenue': parse_number(cells[1]),
        'gross_margin': parse_number(cells[2]),
        'operating_margin': parse_number(cells[3]),
        'net_margin': parse_number(cells[4]),
    }

# Comparison tolerances
MONEY_TOL = 0.01  # $0.01
PCT_TOL = 0.0001   # 0.01% expressed as decimal

def compare_vals(ref, rep, tol):
    if ref is None and rep is None:
        return {'status': 'SKIPPED'}
    if ref is None or rep is None:
        return {'status': 'FAIL', 'ref': ref, 'rep': rep, 'diff': None}
    diff = round(abs(ref - rep), 6)
    status = 'PASS' if diff <= tol else 'FAIL'
    return {'status': status, 'ref': ref, 'rep': rep, 'diff': diff}

comparison = {'monthly': {}, 'ttm': {}, 'summary': {'total': 0, 'passes': 0, 'fails': 0, 'skipped': 0}}

# Monthly comparisons
for period, mm in metrics.monthly_metrics.items():
    entry = {}
    entry['revenue'] = compare_vals(mm.revenue, report_rev_gross.get(period, {}).get('revenue'), MONEY_TOL)
    entry['gross_profit'] = compare_vals(mm.gross_profit, report_rev_gross.get(period, {}).get('gross_profit'), MONEY_TOL)
    entry['gross_margin_pct'] = compare_vals(mm.gross_margin_pct, report_rev_gross.get(period, {}).get('gross_margin'), PCT_TOL)
    entry['total_opex'] = compare_vals(mm.total_opex, report_op_exp.get(period, {}).get('total_opex'), MONEY_TOL)
    entry['net_income'] = compare_vals(mm.net_income, report_inc_net.get(period, {}).get('net_income'), MONEY_TOL)
    entry['operating_margin_pct'] = compare_vals(mm.operating_margin_pct, report_inc_net.get(period, {}).get('operating_margin'), PCT_TOL)
    entry['net_margin_pct'] = compare_vals(mm.net_margin_pct, report_inc_net.get(period, {}).get('net_margin'), PCT_TOL)
    entry['revenue_mom_usd'] = compare_vals(mm.revenue_mom_change_usd, report_rev_gross.get(period, {}).get('revenue_mom_usd'), MONEY_TOL)
    entry['revenue_mom_pct'] = compare_vals(mm.revenue_mom_change_pct, report_rev_gross.get(period, {}).get('revenue_mom_pct'), PCT_TOL)
    comparison['monthly'][period] = entry

# TTM comparisons
for period, ttm in metrics.ttm_metrics.items():
    entry = {}
    entry['revenue'] = compare_vals(ttm.revenue, report_ttm.get(period, {}).get('revenue'), MONEY_TOL)
    entry['gross_margin_pct'] = compare_vals(ttm.gross_margin_pct, report_ttm.get(period, {}).get('gross_margin'), PCT_TOL)
    entry['operating_margin_pct'] = compare_vals(ttm.operating_margin_pct, report_ttm.get(period, {}).get('operating_margin'), PCT_TOL)
    entry['net_margin_pct'] = compare_vals(ttm.net_margin_pct, report_ttm.get(period, {}).get('net_margin'), PCT_TOL)
    comparison['ttm'][period] = entry

# Summarise overall counts
for cat in ('monthly', 'ttm'):
    for period, metrics_dict in comparison[cat].items():
        for metric, result in metrics_dict.items():
            comparison['summary']['total'] += 1
            if result['status'] == 'PASS':
                comparison['summary']['passes'] += 1
            elif result['status'] == 'FAIL':
                comparison['summary']['fails'] += 1
            else:
                comparison['summary']['skipped'] += 1

# Write JSON comparison
output_json.write_text(json.dumps(comparison, indent=2), encoding='utf-8')

# Helper for markdown formatting
def fmt(val, is_pct=False):
    if val is None:
        return 'N/A'
    if is_pct:
        return f"{val*100:.2f}%"
    return f"${val:,.2f}"

lines_md = []
lines_md.append('# Financial Metrics Comparison')
lines_md.append('')
lines_md.append('## Summary')
summary = comparison['summary']
lines_md.append(f"- Total comparisons: {summary['total']}")
lines_md.append(f"- Passes: {summary['passes']}")
lines_md.append(f"- Failures: {summary['fails']}")
lines_md.append(f"- Skipped / N/A: {summary['skipped']}")
lines_md.append('')

# Monthly comparison table
lines_md.append('## Monthly Comparisons')
header = ['Period', 'Metric', 'Reference', 'Report', 'Diff', 'Status']
lines_md.append('|' + '|'.join(header) + '|')
lines_md.append('|' + '|'.join(['---'] * len(header)) + '|')
for period in sorted(comparison['monthly'].keys()):
    for metric, res in sorted(comparison['monthly'][period].items()):
        is_pct = metric.endswith('pct')
        ref = fmt(res.get('ref'), is_pct)
        rep = fmt(res.get('rep'), is_pct)
        diff_val = res.get('diff')
        diff = fmt(diff_val, is_pct) if diff_val is not None else 'N/A'
        lines_md.append(f"|{period}|{metric}|{ref}|{rep}|{diff}|{res['status']}|")
lines_md.append('')

# TTM comparison table
lines_md.append('## TTM Comparisons')
header = ['TTM End Period', 'Metric', 'Reference', 'Report', 'Diff', 'Status']
lines_md.append('|' + '|'.join(header) + '|')
lines_md.append('|' + '|'.join(['---'] * len(header)) + '|')
for period in sorted(comparison['ttm'].keys()):
    for metric, res in sorted(comparison['ttm'][period].items()):
        is_pct = metric.endswith('pct')
        ref = fmt(res.get('ref'), is_pct)
        rep = fmt(res.get('rep'), is_pct)
        diff_val = res.get('diff')
        diff = fmt(diff_val, is_pct) if diff_val is not None else 'N/A'
        lines_md.append(f"|{period}|{metric}|{ref}|{rep}|{diff}|{res['status']}|")
lines_md.append('')

output_md.write_text('\n'.join(lines_md), encoding='utf-8')
print('Comparison files written to', output_json, 'and', output_md)
