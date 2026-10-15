"""Validation engine for FinAudit-Workbench.

Implements structural validation, formula arithmetic verification, Balance Sheet
reconciliation, missing-cache handling, and anomaly detection as specified in
docs/workbook_ingestion_spec.md.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.models import (
    FinancialLineItem,
    FinancialStatement,
    FindingSeverity,
    FindingStatus,
    RowClassification,
    ValidationFinding,
    ValidationReport,
)

TOLERANCE = 0.01

EXPECTED_PERIODS = [
    "2026-06", "2026-05", "2026-04", "2026-03", "2026-02", "2026-01",
    "2025-12", "2025-11", "2025-10", "2025-09", "2025-08", "2025-07",
    "2025-06", "2025-05", "2025-04", "2025-03", "2025-02", "2025-01",
]

IS_FORMULA_ROWS = [14, 24, 26, 59, 71, 103, 105, 107]
BS_FORMULA_ROWS = [15, 27, 33, 36, 37, 54, 58, 59, 70, 71]


def _check_arithmetic(
    report: ValidationReport,
    rule_id: str,
    statement: str,
    period: str,
    row_num: int,
    actual: Optional[float],
    expected: Optional[float],
    description: str,
    severity: FindingSeverity = FindingSeverity.CRITICAL,
) -> None:
    """Helper to check numeric equality with tolerance or record UNABLE_TO_EVALUATE."""
    if actual is None or expected is None:
        report.add_finding(
            ValidationFinding(
                rule_id=rule_id,
                severity=severity,
                status=FindingStatus.UNABLE_TO_EVALUATE,
                statement=statement,
                period=period,
                row_number=row_num,
                details=f"{description}: unable to evaluate (actual={actual!r}, expected={expected!r})",
                actual_value=actual,
                expected_value=expected,
            )
        )
        return

    diff = abs(actual - expected)
    passed = diff < TOLERANCE
    report.add_finding(
        ValidationFinding(
            rule_id=rule_id,
            severity=severity,
            status=FindingStatus.PASSED if passed else FindingStatus.FAILED,
            statement=statement,
            period=period,
            row_number=row_num,
            details=f"{description}: diff={diff:.8f}" if passed else f"{description}: mismatch (diff={diff:.8f})",
            actual_value=actual,
            expected_value=expected,
        )
    )


def _sum_rows(statement: FinancialStatement, row_range: range, period: str) -> Optional[float]:
    """Sum effective numeric values across a range of rows.
    
    Returns None if any row is missing an effective value.
    """
    total = 0.0
    for r in row_range:
        item = statement.get_item_by_row(r)
        val = item.get_value(period)
        if val is None:
            return None
        total += val
    return total


def validate_financial_statements(
    is_stmt: FinancialStatement,
    bs_stmt: FinancialStatement,
) -> ValidationReport:
    """Run all independent validation checks across both financial statements.
    
    Always executes all checks unconditionally and compiles a complete ValidationReport.
    """
    report = ValidationReport()

    # 1. Structural Checks: Periods and Dimensions
    # VAL-PER-01: Period Count and Order
    is_periods = is_stmt.get_period_keys()
    bs_periods = bs_stmt.get_period_keys()

    is_per_ok = (len(is_periods) == 18 and is_periods == EXPECTED_PERIODS)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-PER-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if is_per_ok else FindingStatus.FAILED,
            statement="Income Statement",
            details="18 monthly periods present in exact reverse chronological order"
            if is_per_ok else f"Period sequence mismatch in Income Statement: {is_periods}",
        )
    )

    bs_per_ok = (len(bs_periods) == 18 and bs_periods == EXPECTED_PERIODS)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-PER-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if bs_per_ok else FindingStatus.FAILED,
            statement="Balance Sheet",
            details="18 monthly periods present in exact reverse chronological order"
            if bs_per_ok else f"Period sequence mismatch in Balance Sheet: {bs_periods}",
        )
    )

    # VAL-PER-02: Period Alignment between sheets
    aligned = (is_periods == bs_periods)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-PER-02",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if aligned else FindingStatus.FAILED,
            statement="Cross-Statement",
            details="Income Statement and Balance Sheet periods align 1:1"
            if aligned else "Statement periods do not align",
        )
    )

    # VAL-DIM-01: Trailing empty columns
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-DIM-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if is_stmt.trailing_empty_columns_verified else FindingStatus.FAILED,
            statement="Income Statement",
            details="Trailing columns U-Y contain 0 populated cells"
            if is_stmt.trailing_empty_columns_verified else "Trailing columns U-Y contain populated cells",
        )
    )
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-DIM-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if bs_stmt.trailing_empty_columns_verified else FindingStatus.FAILED,
            statement="Balance Sheet",
            details="Trailing columns V-Z contain 0 populated cells"
            if bs_stmt.trailing_empty_columns_verified else "Trailing columns V-Z contain populated cells",
        )
    )

    # VAL-ENG-01: Formula cache completeness (all 324 formula cells have cached values)
    missing_cache_is = []
    for r in IS_FORMULA_ROWS:
        item = is_stmt.get_item_by_row(r)
        for p in is_periods:
            cell = item.get_cell(p)
            if cell and cell.formula_text and cell.cached_value is None:
                missing_cache_is.append(f"Row {r} {p}")

    missing_cache_bs = []
    for r in BS_FORMULA_ROWS:
        item = bs_stmt.get_item_by_row(r)
        for p in bs_periods:
            cell = item.get_cell(p)
            if cell and cell.formula_text and cell.cached_value is None:
                missing_cache_bs.append(f"Row {r} {p}")

    is_cache_ok = (len(missing_cache_is) == 0)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-ENG-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if is_cache_ok else FindingStatus.FAILED,
            statement="Income Statement",
            details="All 144 formula cells contain valid cached precalculated values"
            if is_cache_ok else f"Missing formula cache in Income Statement: {missing_cache_is}",
        )
    )

    bs_cache_ok = (len(missing_cache_bs) == 0)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-ENG-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.PASSED if bs_cache_ok else FindingStatus.FAILED,
            statement="Balance Sheet",
            details="All 180 formula cells contain valid cached precalculated values"
            if bs_cache_ok else f"Missing formula cache in Balance Sheet: {missing_cache_bs}",
        )
    )

    # 2. Income Statement Independent Formula Calculations (across all 18 periods)
    for p in is_periods:
        # VAL-IS-04: Row 14 Total Income == SUM(Rows 8:13)
        actual_inc = is_stmt.get_item_by_row(14).get_value(p)
        expected_inc = _sum_rows(is_stmt, range(8, 14), p)
        _check_arithmetic(
            report, "VAL-IS-04", "Income Statement", p, 14, actual_inc, expected_inc, "Total Income formula"
        )

        # VAL-IS-05: Row 24 Total COGS == SUM(Rows 17:23)
        actual_cogs = is_stmt.get_item_by_row(24).get_value(p)
        expected_cogs = _sum_rows(is_stmt, range(17, 24), p)
        _check_arithmetic(
            report, "VAL-IS-05", "Income Statement", p, 24, actual_cogs, expected_cogs, "Total COGS formula"
        )

        # VAL-IS-01: Row 26 Gross Profit == Row 14 - Row 24
        actual_gp = is_stmt.get_item_by_row(26).get_value(p)
        expected_gp = (actual_inc - actual_cogs) if (actual_inc is not None and actual_cogs is not None) else None
        _check_arithmetic(
            report, "VAL-IS-01", "Income Statement", p, 26, actual_gp, expected_gp, "Gross Profit formula"
        )

        # VAL-IS-06: Row 59 Total S&M Payroll == SUM(Rows 48:58)
        actual_sm_pay = is_stmt.get_item_by_row(59).get_value(p)
        expected_sm_pay = _sum_rows(is_stmt, range(48, 59), p)
        _check_arithmetic(
            report, "VAL-IS-06", "Income Statement", p, 59, actual_sm_pay, expected_sm_pay, "Total S&M Payroll formula"
        )

        # VAL-IS-07: Row 71 Total Marketing == SUM(Rows 61:70)
        actual_mkt = is_stmt.get_item_by_row(71).get_value(p)
        expected_mkt = _sum_rows(is_stmt, range(61, 71), p)
        _check_arithmetic(
            report, "VAL-IS-07", "Income Statement", p, 71, actual_mkt, expected_mkt, "Total Marketing formula"
        )

        # VAL-IS-08: Row 103 Total OpEx == SUM(Rows 29:46) + SUM(Rows 72:102) + Row 59 + Row 71
        actual_opex = is_stmt.get_item_by_row(103).get_value(p)
        sum_direct = _sum_rows(is_stmt, range(29, 47), p)
        sum_other = _sum_rows(is_stmt, range(72, 103), p)
        if (
            sum_direct is not None
            and sum_other is not None
            and actual_sm_pay is not None
            and actual_mkt is not None
        ):
            expected_opex = sum_direct + sum_other + actual_sm_pay + actual_mkt
        else:
            expected_opex = None
        _check_arithmetic(
            report, "VAL-IS-08", "Income Statement", p, 103, actual_opex, expected_opex, "Total OpEx formula"
        )

        # VAL-IS-02: Row 105 Operating Income == Row 26 - Row 103
        actual_opinc = is_stmt.get_item_by_row(105).get_value(p)
        expected_opinc = (actual_gp - actual_opex) if (actual_gp is not None and actual_opex is not None) else None
        _check_arithmetic(
            report, "VAL-IS-02", "Income Statement", p, 105, actual_opinc, expected_opinc, "Operating Income formula"
        )

        # VAL-IS-03: Row 107 Net Income == Row 105 + 0
        actual_ni = is_stmt.get_item_by_row(107).get_value(p)
        expected_ni = actual_opinc
        _check_arithmetic(
            report, "VAL-IS-03", "Income Statement", p, 107, actual_ni, expected_ni, "Net Income formula"
        )

    # 3. Balance Sheet Independent Formula Calculations (across all 18 periods)
    for p in bs_periods:
        # VAL-BS-06: Row 15 Total Cash == SUM(Rows 10:14)
        actual_cash = bs_stmt.get_item_by_row(15).get_value(p)
        expected_cash = _sum_rows(bs_stmt, range(10, 15), p)
        _check_arithmetic(
            report, "VAL-BS-06", "Balance Sheet", p, 15, actual_cash, expected_cash, "Total Cash formula"
        )

        # VAL-BS-01: Row 27 Total Current Assets == SUM(Rows 16:26) + Row 15
        actual_ca = bs_stmt.get_item_by_row(27).get_value(p)
        sum_other_ca = _sum_rows(bs_stmt, range(16, 27), p)
        expected_ca = (sum_other_ca + actual_cash) if (sum_other_ca is not None and actual_cash is not None) else None
        _check_arithmetic(
            report, "VAL-BS-01", "Balance Sheet", p, 27, actual_ca, expected_ca, "Total Current Assets formula"
        )

        # VAL-BS-07: Row 33 Total Fixed Assets == SUM(Rows 29:32)
        actual_fa = bs_stmt.get_item_by_row(33).get_value(p)
        expected_fa = _sum_rows(bs_stmt, range(29, 33), p)
        _check_arithmetic(
            report, "VAL-BS-07", "Balance Sheet", p, 33, actual_fa, expected_fa, "Total Fixed Assets formula"
        )

        # VAL-BS-08: Row 36 Total Long Term Assets == Row 35
        actual_lta = bs_stmt.get_item_by_row(36).get_value(p)
        expected_lta = bs_stmt.get_item_by_row(35).get_value(p)
        _check_arithmetic(
            report, "VAL-BS-08", "Balance Sheet", p, 36, actual_lta, expected_lta, "Total Long Term Assets formula"
        )

        # VAL-BS-02: Row 37 Total Assets == Row 27 + Row 33 + Row 36
        actual_assets = bs_stmt.get_item_by_row(37).get_value(p)
        expected_assets = (
            (actual_ca + actual_fa + actual_lta)
            if (actual_ca is not None and actual_fa is not None and actual_lta is not None)
            else None
        )
        _check_arithmetic(
            report, "VAL-BS-02", "Balance Sheet", p, 37, actual_assets, expected_assets, "Total Assets formula"
        )

        # VAL-BS-09: Row 54 Total Current Liabilities == SUM(Rows 42:53)
        actual_cl = bs_stmt.get_item_by_row(54).get_value(p)
        expected_cl = _sum_rows(bs_stmt, range(42, 54), p)
        _check_arithmetic(
            report, "VAL-BS-09", "Balance Sheet", p, 54, actual_cl, expected_cl, "Total Current Liabilities formula"
        )

        # VAL-BS-10: Row 58 Total Long Term Liabilities == SUM(Rows 56:57)
        actual_ltl = bs_stmt.get_item_by_row(58).get_value(p)
        expected_ltl = _sum_rows(bs_stmt, range(56, 58), p)
        _check_arithmetic(
            report, "VAL-BS-10", "Balance Sheet", p, 58, actual_ltl, expected_ltl, "Total Long Term Liabilities formula"
        )

        # VAL-BS-03: Row 59 Total Liabilities == Row 54 + Row 58
        actual_liab = bs_stmt.get_item_by_row(59).get_value(p)
        expected_liab = (actual_cl + actual_ltl) if (actual_cl is not None and actual_ltl is not None) else None
        _check_arithmetic(
            report, "VAL-BS-03", "Balance Sheet", p, 59, actual_liab, expected_liab, "Total Liabilities formula"
        )

        # VAL-BS-11: Row 70 Total Equity == SUM(Rows 61:69)
        actual_eq = bs_stmt.get_item_by_row(70).get_value(p)
        expected_eq = _sum_rows(bs_stmt, range(61, 70), p)
        _check_arithmetic(
            report, "VAL-BS-11", "Balance Sheet", p, 70, actual_eq, expected_eq, "Total Equity formula"
        )

        # VAL-BS-04: Row 71 Total Liabilities & Equity == Row 59 + Row 70
        actual_le = bs_stmt.get_item_by_row(71).get_value(p)
        expected_le = (actual_liab + actual_eq) if (actual_liab is not None and actual_eq is not None) else None
        _check_arithmetic(
            report, "VAL-BS-04", "Balance Sheet", p, 71, actual_le, expected_le, "Total L&E formula"
        )

        # VAL-BS-05: Balance Sheet Full Reconciliation (Total Assets == Total Liabilities & Equity)
        _check_arithmetic(
            report, "VAL-BS-05", "Balance Sheet", p, 37, actual_assets, actual_le, "Balance Sheet Reconciliation (Assets == L&E)"
        )

    # 4. Source Anomaly and Integrity Verifications (Warning & Info findings)
    # VAL-ANOM-01: December 2025 Income Tax Benefit & Negative OpEx
    dec_tax_ben = is_stmt.get_item_by_row(101).get_value("2025-12")
    dec_opex = is_stmt.get_item_by_row(103).get_value("2025-12")
    dec_opinc = is_stmt.get_item_by_row(105).get_value("2025-12")
    if dec_tax_ben is not None and dec_tax_ben < -1000000:
        report.add_finding(
            ValidationFinding(
                rule_id="VAL-ANOM-01",
                severity=FindingSeverity.WARNING,
                status=FindingStatus.PASSED,
                statement="Income Statement",
                period="2025-12",
                row_number=101,
                details=(
                    f"Dec 2025 Income Tax Benefit is ${dec_tax_ben:,.2f}, "
                    f"driving OpEx negative (${dec_opex:,.2f}) and Operating Income positive (${dec_opinc:,.2f})"
                ),
                actual_value=dec_tax_ben,
            )
        )

    # VAL-ANOM-02: December 2025 Stock-Based Compensation
    dec_sbc = is_stmt.get_item_by_row(99).get_value("2025-12")
    if dec_sbc is not None and dec_sbc > 300000:
        report.add_finding(
            ValidationFinding(
                rule_id="VAL-ANOM-02",
                severity=FindingSeverity.WARNING,
                status=FindingStatus.PASSED,
                statement="Income Statement",
                period="2025-12",
                row_number=99,
                details=f"Dec 2025 Stock-Based Compensation isolated expense is ${dec_sbc:,.2f}",
                actual_value=dec_sbc,
            )
        )

    # VAL-ANOM-03: Debit balance in liability account (HSA Liability row 48)
    hsa_item = bs_stmt.get_item_by_row(48)
    hsa_neg_periods = [p for p in bs_periods if (hsa_item.get_value(p) or 0.0) < 0.0]
    if hsa_neg_periods:
        report.add_finding(
            ValidationFinding(
                rule_id="VAL-ANOM-03",
                severity=FindingSeverity.WARNING,
                status=FindingStatus.PASSED,
                statement="Balance Sheet",
                row_number=48,
                details=f"HSA Liability exhibits debit balance (negative) in {len(hsa_neg_periods)} periods",
            )
        )

    # VAL-ANOM-04: Dormant accounts (rows 89-92)
    dormant_rows = [89, 90, 91, 92]
    all_zero_dormant = True
    for r in dormant_rows:
        item = is_stmt.get_item_by_row(r)
        if any(item.get_value(p) not in (0.0, None) for p in is_periods):
            all_zero_dormant = False
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-ANOM-04",
            severity=FindingSeverity.INFO,
            status=FindingStatus.PASSED if all_zero_dormant else FindingStatus.FAILED,
            statement="Income Statement",
            details="Rows 89-92 correctly identified and preserved as dormant zero-valued detail accounts",
        )
    )

    # VAL-FMT-01: Document formatting anomalies
    bs_c35 = bs_stmt.get_item_by_row(35)
    bs_c53 = bs_stmt.get_item_by_row(53)
    bs_c68 = bs_stmt.get_item_by_row(68)
    has_dash_35 = "\u2013" in bs_c35.original_label
    has_dash_68 = "\u2013" in bs_c68.original_label
    has_trailing_53 = bs_c53.original_label.endswith(" ")
    fmt_ok = (has_dash_35 and has_dash_68 and has_trailing_53)
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-FMT-01",
            severity=FindingSeverity.INFO,
            status=FindingStatus.PASSED if fmt_ok else FindingStatus.FAILED,
            statement="Balance Sheet",
            details="Unicode U+2013 en-dashes preserved in C35/C68 and trailing space preserved in C53",
        )
    )

    # VAL-DUP-01: Duplicate account labels within sheet sections
    validate_duplicate_account_labels(is_stmt, report)
    validate_duplicate_account_labels(bs_stmt, report)

    return report


def validate_duplicate_account_labels(
    statement: FinancialStatement,
    report: ValidationReport,
) -> None:
    """Validate that detail account labels are unique within each relevant sheet section.
    
    Excludes non-detail rows (headings, subtotals, spacers) to avoid false positives on legitimate
    repeated headings. Reports relevant row numbers for any duplicate findings.
    """
    section_map: Dict[Tuple[str, ...], Dict[str, List[int]]] = {}

    for item in statement.items:
        if item.classification != RowClassification.DETAIL_ACCOUNT:
            continue
        norm_label = item.normalized_label.strip()
        if not norm_label:
            continue
        section = item.hierarchy_path
        section_map.setdefault(section, {}).setdefault(norm_label.lower(), []).append(item.row_number)

    has_duplicate = False
    for section, label_dict in section_map.items():
        section_display = " > ".join(section) if section else "Root"
        for label_key, row_nums in label_dict.items():
            if len(row_nums) > 1:
                has_duplicate = True
                display_label = statement.get_item_by_row(row_nums[0]).normalized_label
                report.add_finding(
                    ValidationFinding(
                        rule_id="VAL-DUP-01",
                        severity=FindingSeverity.WARNING,
                        status=FindingStatus.FAILED,
                        statement=statement.statement_name,
                        row_number=row_nums[0],
                        details=(
                            f"Duplicate detail account label '{display_label}' "
                            f"in section '{section_display}' at rows {row_nums}"
                        ),
                    )
                )

    if not has_duplicate:
        report.add_finding(
            ValidationFinding(
                rule_id="VAL-DUP-01",
                severity=FindingSeverity.INFO,
                status=FindingStatus.PASSED,
                statement=statement.statement_name,
                details=f"All detail account labels are unique within sections in {statement.statement_name}",
            )
        )
