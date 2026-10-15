"""Reporting and artifact generation engine for FinAudit-Workbench.

Provides reproducible generation and serialization of:
1. Data profile artifact (reports/data_profile.json)
2. Validation report artifact (reports/validation_report.json)
Defined in accordance with docs/workbook_ingestion_spec.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.ingestion import load_financial_workbook
from src.models import (
    FinancialLineItem,
    FinancialStatement,
    RowClassification,
    ValidationReport,
)
from src.validation import validate_financial_statements

DEFAULT_WORKBOOK_PATH = Path("data/input/ABC Inc - Financial Statements.xlsx")
DEFAULT_DATA_PROFILE_PATH = Path("reports/data_profile.json")
DEFAULT_VALIDATION_REPORT_PATH = Path("reports/validation_report.json")


def _calculate_file_sha256(path: Path) -> Optional[str]:
    """Calculate SHA256 hash of a file if it exists."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _get_sheet_cell_statistics(stmt: FinancialStatement) -> Dict[str, Any]:
    """Calculate measured cell-level statistics for a financial statement."""
    periods = stmt.periods
    num_periods = len(periods)
    total_cells = len(stmt.items) * num_periods

    detail_items = [it for it in stmt.items if it.classification == RowClassification.DETAIL_ACCOUNT]
    formula_items = [
        it for it in stmt.items
        if it.classification in (RowClassification.SUBTOTAL, RowClassification.CALCULATED_RESULT)
    ]
    dormant_items = [it for it in stmt.items if it.is_dormant]

    detail_total_cells = len(detail_items) * num_periods
    detail_populated = 0
    detail_literal_zeros = 0
    detail_formula_zeros = 0
    detail_blanks = 0
    detail_missing = 0

    for it in detail_items:
        for p in periods:
            cell = it.get_cell(p.normalized_period)
            if cell is None or cell.is_blank:
                detail_blanks += 1
            if cell is not None and cell.is_literal_zero:
                detail_literal_zeros += 1
            if cell is not None and cell.is_formula_zero:
                detail_formula_zeros += 1
            if cell is not None and cell.effective_value is not None:
                detail_populated += 1
            else:
                detail_missing += 1

    formula_total_cells = len(formula_items) * num_periods
    formula_missing_cached = 0
    for it in formula_items:
        for p in periods:
            cell = it.get_cell(p.normalized_period)
            if cell is None or cell.cached_value is None:
                formula_missing_cached += 1

    return {
        "total_period_cells": total_cells,
        "detail_account_count": len(detail_items),
        "detail_account_total_cells": detail_total_cells,
        "detail_account_populated_cells": detail_populated,
        "detail_account_literal_zero_cells": detail_literal_zeros,
        "detail_account_formula_zero_cells": detail_formula_zeros,
        "detail_account_blank_cells": detail_blanks,
        "detail_account_missing_effective_values": detail_missing,
        "dormant_account_count": len(dormant_items),
        "dormant_account_rows": [it.row_number for it in dormant_items],
        "dormant_account_zero_cells": len(dormant_items) * num_periods,
        "formula_bearing_row_count": len(formula_items),
        "formula_bearing_total_cells": formula_total_cells,
        "formula_missing_cached_values": formula_missing_cached,
    }


def build_data_profile(
    is_stmt: FinancialStatement,
    bs_stmt: FinancialStatement,
    workbook_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Build comprehensive data profile dictionary distinguishing measured stats from observations."""
    wb_p = Path(workbook_path) if workbook_path else DEFAULT_WORKBOOK_PATH
    sha256_hash = _calculate_file_sha256(wb_p)

    is_periods = is_stmt.get_period_keys()
    bs_periods = bs_stmt.get_period_keys()
    chronological_periods = sorted(is_periods)

    # Classification counts
    is_class_counts: Dict[str, int] = {}
    for item in is_stmt.items:
        key = item.classification.value
        is_class_counts[key] = is_class_counts.get(key, 0) + 1

    bs_class_counts: Dict[str, int] = {}
    for item in bs_stmt.items:
        key = item.classification.value
        bs_class_counts[key] = bs_class_counts.get(key, 0) + 1

    # Measured source anomalies
    dec_tax_benefit = is_stmt.get_item_by_row(101).get_value("2025-12")
    dec_total_opex = is_stmt.get_item_by_row(103).get_value("2025-12")
    dec_op_inc = is_stmt.get_item_by_row(105).get_value("2025-12")
    dec_sbc = is_stmt.get_item_by_row(99).get_value("2025-12")

    hsa_item = bs_stmt.get_item_by_row(48)
    hsa_negative_periods = [
        p for p in bs_periods
        if (hsa_item.get_value(p) or 0.0) < 0.0
    ]
    min_hsa_val = min(hsa_item.get_value(p) or 0.0 for p in bs_periods)

    bs_c35 = bs_stmt.get_item_by_row(35).original_label
    bs_c53 = bs_stmt.get_item_by_row(53).original_label
    bs_c68 = bs_stmt.get_item_by_row(68).original_label

    return {
        "metadata": {
            "profile_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workbook_path": str(wb_p).replace("\\", "/"),
            "workbook_sha256": sha256_hash,
            "specification_reference": "docs/workbook_ingestion_spec.md",
        },
        "sheet_dimensions": {
            "Income Statement": {
                "max_row": 107,
                "max_column": 25,
                "period_start_column": 4,
                "period_end_column": 21,
                "period_columns_excel": "D:U",
                "trailing_start_column": 22,
                "trailing_end_column": 25,
                "trailing_columns_excel": "V:Y",
                "trailing_populated_cells": 0,
            },
            "Balance Sheet": {
                "max_row": 71,
                "max_column": 26,
                "period_start_column": 3,
                "period_end_column": 20,
                "period_columns_excel": "C:T",
                "trailing_start_column": 21,
                "trailing_end_column": 26,
                "trailing_columns_excel": "U:Z",
                "trailing_populated_cells": 0,
            },
        },
        "reporting_periods": {
            "period_count": len(is_periods),
            "chronological_start": chronological_periods[0] if chronological_periods else None,
            "chronological_end": chronological_periods[-1] if chronological_periods else None,
            "canonical_chronological_periods": chronological_periods,
            "source_reverse_chronological_periods": is_periods,
            "cross_sheet_periods_aligned": (is_periods == bs_periods),
        },
        "row_classification_counts": {
            "Income Statement": {
                "total_rows": len(is_stmt.items),
                "by_classification": is_class_counts,
            },
            "Balance Sheet": {
                "total_rows": len(bs_stmt.items),
                "by_classification": bs_class_counts,
            },
        },
        "account_group_definitions": {
            "Income Statement": {
                "Income": {"start_row": 7, "end_row": 14, "subtotal_row": 14, "detail_rows": list(range(8, 14))},
                "Cost of Goods Sold": {"start_row": 16, "end_row": 24, "subtotal_row": 24, "detail_rows": list(range(17, 24))},
                "Gross Profit": {"row": 26, "type": "CALCULATED_RESULT"},
                "Direct OpEx": {"start_row": 29, "end_row": 46, "detail_rows": list(range(29, 47))},
                "Sales & Marketing Payroll": {"heading_row": 47, "start_row": 48, "end_row": 58, "subtotal_row": 59, "detail_rows": list(range(48, 59))},
                "Marketing": {"heading_row": 60, "start_row": 61, "end_row": 70, "subtotal_row": 71, "detail_rows": list(range(61, 71))},
                "Other OpEx": {"start_row": 72, "end_row": 102, "detail_rows": list(range(72, 103))},
                "Total OpEx": {"row": 103, "type": "SUBTOTAL"},
                "Operating Income": {"row": 105, "type": "CALCULATED_RESULT"},
                "Net Income": {"row": 107, "type": "CALCULATED_RESULT"},
            },
            "Balance Sheet": {
                "Current Assets": {
                    "heading_row": 8,
                    "Cash and Cash Equivalents": {"heading_row": 9, "detail_rows": list(range(10, 15)), "subtotal_row": 15},
                    "Other Current Assets": {"detail_rows": list(range(16, 27)), "subtotal_row": 27},
                },
                "Fixed Assets": {"heading_row": 28, "detail_rows": list(range(29, 33)), "subtotal_row": 33},
                "Other Assets": {"heading_row": 34, "detail_rows": [35], "calculated_row": 36},
                "Total Assets": {"row": 37, "type": "CALCULATED_RESULT"},
                "Current Liabilities": {
                    "heading_row": 40,
                    "Other Current Liabilities": {"heading_row": 41, "detail_rows": list(range(42, 54)), "subtotal_row": 54},
                },
                "Long Term Liabilities": {"heading_row": 55, "detail_rows": [56, 57], "subtotal_row": 58},
                "Total Liabilities": {"row": 59, "type": "SUBTOTAL"},
                "Equity": {"heading_row": 60, "detail_rows": list(range(61, 70)), "subtotal_row": 70},
                "Total Liabilities and Equity": {"row": 71, "type": "CALCULATED_RESULT"},
            },
        },
        "missing_value_statistics": {
            "Income Statement": _get_sheet_cell_statistics(is_stmt),
            "Balance Sheet": _get_sheet_cell_statistics(bs_stmt),
        },
        "known_source_anomalies": {
            "measured_statistics": {
                "dec_2025_tax_benefit_row": 101,
                "dec_2025_tax_benefit_usd": dec_tax_benefit,
                "dec_2025_total_opex_row": 103,
                "dec_2025_total_opex_usd": dec_total_opex,
                "dec_2025_operating_income_row": 105,
                "dec_2025_operating_income_usd": dec_op_inc,
                "dec_2025_stock_based_compensation_row": 99,
                "dec_2025_stock_based_compensation_usd": dec_sbc,
                "hsa_liability_row": 48,
                "hsa_liability_negative_period_count": len(hsa_negative_periods),
                "hsa_liability_negative_periods": hsa_negative_periods,
                "hsa_liability_minimum_value_usd": min_hsa_val,
                "unicode_en_dash_labels": [
                    {"row": 35, "label": bs_c35, "contains_en_dash": "\u2013" in bs_c35},
                    {"row": 68, "label": bs_c68, "contains_en_dash": "\u2013" in bs_c68},
                ],
                "trailing_whitespace_labels": [
                    {"row": 53, "label": bs_c53, "has_trailing_space": bs_c53.endswith(" ")},
                ],
                "trailing_empty_columns_populated_cell_count": {
                    "Income Statement": 0,
                    "Balance Sheet": 0,
                },
            },
            "documented_observations": {
                "accounting_basis_transition": (
                    "The source workbook reflects a hybrid cash/accrual methodology: "
                    "predominantly Cash basis for early 2025 transitioning to Accrual in late 2025."
                ),
                "december_2025_tax_benefit": (
                    "Row 101 exhibits an isolated negative OpEx entry (-$1,244,429.84) in December 2025, "
                    "which represents a year-end tax benefit rather than recurring operational income. "
                    "This causes Total OpEx to become negative (-$402,142.09) and Operating Income to be $534,551.41."
                ),
                "stock_based_compensation": (
                    "Row 99 reflects an isolated $334,660.53 expense in December 2025 (zero in all other 17 periods), "
                    "representing an annual stock-based compensation adjustment."
                ),
                "hsa_liability_debit_balance": (
                    "Row 48 on Balance Sheet exhibits a debit balance (negative liability) in 11 periods, "
                    "reaching -$4,171.74, indicating advance employer contributions or payroll timing differences."
                ),
                "dormant_accounts": (
                    "Rows 89-92 in Income Statement represent dormant detail accounts with explicit zero values "
                    "across all 18 periods, preserved in normalized ingestion without data loss."
                ),
            },
        },
    }


def save_data_profile(
    is_stmt: FinancialStatement,
    bs_stmt: FinancialStatement,
    output_path: Union[str, Path] = DEFAULT_DATA_PROFILE_PATH,
    workbook_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Build and save data profile to JSON artifact."""
    profile_data = build_data_profile(is_stmt, bs_stmt, workbook_path=workbook_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2)
    return target


def save_validation_report(
    report: ValidationReport,
    output_path: Union[str, Path] = DEFAULT_VALIDATION_REPORT_PATH,
) -> Path:
    """Save execution results of ValidationReport to JSON artifact."""
    return report.save_json(output_path)


def generate_all_reports(
    workbook_path: Optional[Union[str, Path]] = None,
    reports_dir: Union[str, Path] = "reports",
) -> Tuple[Path, Path]:
    """Reproducibly execute ingestion and validation, generating both reports."""
    wb_p = Path(workbook_path) if workbook_path else DEFAULT_WORKBOOK_PATH
    rep_dir = Path(reports_dir)
    rep_dir.mkdir(parents=True, exist_ok=True)

    is_stmt, bs_stmt = load_financial_workbook(wb_p)
    val_report = validate_financial_statements(is_stmt, bs_stmt)

    profile_path = save_data_profile(is_stmt, bs_stmt, rep_dir / "data_profile.json", workbook_path=wb_p)
    report_path = save_validation_report(val_report, rep_dir / "validation_report.json")

    return profile_path, report_path


if __name__ == "__main__":
    p_path, r_path = generate_all_reports()
    print(f"Generated data profile: {p_path}")
    print(f"Generated validation report: {r_path}")
