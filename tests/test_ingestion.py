"""Automated tests for Phase 1 workbook ingestion.

Verifies workbook structure, period normalization, value provenance, explicit
row classifications, and source anomaly preservation against the physical workbook.
"""

from pathlib import Path
import pytest

from src.ingestion import load_financial_workbook
from src.models import RowClassification

WORKBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "input" / "ABC Inc - Financial Statements.xlsx"
EXPECTED_FILE_SIZE = 42273


@pytest.fixture(scope="module")
def statements():
    """Load both financial statements once for the module."""
    is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
    return is_stmt, bs_stmt


def test_workbook_file_presence_and_immutability():
    """Assert source workbook exists, is readable, and has expected size."""
    assert WORKBOOK_PATH.exists(), f"Source workbook missing at {WORKBOOK_PATH}"
    assert WORKBOOK_PATH.is_file(), f"Path {WORKBOOK_PATH} is not a regular file"
    assert WORKBOOK_PATH.stat().st_size == EXPECTED_FILE_SIZE, (
        f"Workbook size changed! Expected {EXPECTED_FILE_SIZE}, got {WORKBOOK_PATH.stat().st_size}"
    )


def test_structural_dimensions_and_trailing_empty(statements):
    """Assert exact row counts and that trailing columns are 100% empty."""
    is_stmt, bs_stmt = statements

    assert len(is_stmt.items) == 107, f"Expected 107 IS rows, got {len(is_stmt.items)}"
    assert len(bs_stmt.items) == 71, f"Expected 71 BS rows, got {len(bs_stmt.items)}"

    assert is_stmt.trailing_empty_columns_verified is True, "Income Statement trailing columns U-Y are not empty"
    assert bs_stmt.trailing_empty_columns_verified is True, "Balance Sheet trailing columns V-Z are not empty"


def test_period_extraction_and_chronology(statements):
    """Verify exactly 18 periods in descending chronological order matching 1:1."""
    is_stmt, bs_stmt = statements

    expected_periods = [
        "2026-06", "2026-05", "2026-04", "2026-03", "2026-02", "2026-01",
        "2025-12", "2025-11", "2025-10", "2025-09", "2025-08", "2025-07",
        "2025-06", "2025-05", "2025-04", "2025-03", "2025-02", "2025-01",
    ]

    is_keys = is_stmt.get_period_keys()
    bs_keys = bs_stmt.get_period_keys()

    assert len(is_keys) == 18
    assert len(bs_keys) == 18
    assert is_keys == expected_periods
    assert bs_keys == expected_periods
    assert is_keys == bs_keys


def test_dual_loading_parity(statements):
    """Assert 144 IS formula cells, 180 BS formula cells, and 0 missing cached values."""
    is_stmt, bs_stmt = statements

    is_formula_cells = 0
    is_missing_cache = 0
    for item in is_stmt.items:
        for p in is_stmt.get_period_keys():
            cell = item.get_cell(p)
            if cell and cell.formula_text:
                is_formula_cells += 1
                if cell.cached_value is None:
                    is_missing_cache += 1

    bs_formula_cells = 0
    bs_missing_cache = 0
    for item in bs_stmt.items:
        for p in bs_stmt.get_period_keys():
            cell = item.get_cell(p)
            if cell and cell.formula_text:
                bs_formula_cells += 1
                if cell.cached_value is None:
                    bs_missing_cache += 1

    assert is_formula_cells == 144, f"Expected 144 IS formulas (8 rows x 18 cols), got {is_formula_cells}"
    assert bs_formula_cells == 180, f"Expected 180 BS formulas (10 rows x 18 cols), got {bs_formula_cells}"
    assert is_missing_cache == 0, f"Found {is_missing_cache} missing cached values in Income Statement"
    assert bs_missing_cache == 0, f"Found {bs_missing_cache} missing cached values in Balance Sheet"


def test_row_classification_explicit_map(statements):
    """Verify non-overlapping row classification breakdown for both statements."""
    is_stmt, bs_stmt = statements

    # Income Statement classification counts
    is_counts = {}
    for item in is_stmt.items:
        is_counts[item.classification] = is_counts.get(item.classification, 0) + 1

    assert is_counts.get(RowClassification.METADATA) == 3
    assert is_counts.get(RowClassification.HEADER) == 1
    assert is_counts.get(RowClassification.SPACER) == 7
    assert is_counts.get(RowClassification.SECTION_HEADING) == 3
    assert is_counts.get(RowClassification.SUBSECTION_HEADING) == 2
    assert is_counts.get(RowClassification.DETAIL_ACCOUNT) == 83
    assert is_counts.get(RowClassification.SUBTOTAL) == 5
    assert is_counts.get(RowClassification.CALCULATED_RESULT) == 3
    assert sum(is_counts.values()) == 107

    # Balance Sheet classification counts
    bs_counts = {}
    for item in bs_stmt.items:
        bs_counts[item.classification] = bs_counts.get(item.classification, 0) + 1

    assert bs_counts.get(RowClassification.METADATA) == 3
    assert bs_counts.get(RowClassification.HEADER) == 1
    assert bs_counts.get(RowClassification.SPACER) == 3
    assert bs_counts.get(RowClassification.SECTION_HEADING) == 2
    assert bs_counts.get(RowClassification.SUBSECTION_HEADING) == 8
    assert bs_counts.get(RowClassification.DETAIL_ACCOUNT) == 44
    assert bs_counts.get(RowClassification.SUBTOTAL) == 6
    assert bs_counts.get(RowClassification.CALCULATED_RESULT) == 4
    assert sum(bs_counts.values()) == 71


def test_january_2025_period_integrity(statements):
    """Verify January 2025 (2025-01) data is fully populated with values and formulas where expected."""
    is_stmt, bs_stmt = statements

    # IS Col T (Jan 2025): row 8 (literal), row 14 (subtotal), row 24 (subtotal), row 26 (calculated)
    t8_val = is_stmt.get_item_by_row(8).get_value("2025-01")
    t14_val = is_stmt.get_item_by_row(14).get_value("2025-01")
    t24_val = is_stmt.get_item_by_row(24).get_value("2025-01")
    t26_val = is_stmt.get_item_by_row(26).get_value("2025-01")

    assert t8_val == 62312.5
    assert t14_val == 167587.5
    assert t24_val == 36950.54
    assert abs(t26_val - 130636.96) < 0.01

    # Row 8 is a literal DETAIL_ACCOUNT, not a formula
    t8_cell = is_stmt.get_item_by_row(8).get_cell("2025-01")
    assert t8_cell.formula_text is None
    assert t8_cell.literal_value == 62312.5

    # Row 14 has formula and cached value
    t14_cell = is_stmt.get_item_by_row(14).get_cell("2025-01")
    assert t14_cell.formula_text == "=SUM(T8:T13)"
    assert t14_cell.cached_value == 167587.5

    # BS Col U (31 Jan 2025): Total Assets and Total L&E
    u37_val = bs_stmt.get_item_by_row(37).get_value("2025-01")
    u71_val = bs_stmt.get_item_by_row(71).get_value("2025-01")
    assert u37_val is not None
    assert u71_val is not None
    assert abs(u37_val - 8592996.83) < 0.01
    assert abs(u37_val - u71_val) < 0.01


def test_blank_vs_zero_representation(statements):
    """Verify differentiation between blank cells, literal zeros, and formula zeros."""
    is_stmt, _ = statements

    # Spacer row 4 has blank cells
    spacer_cell = is_stmt.get_item_by_row(4).get_cell("2026-06")
    assert spacer_cell.is_blank is True
    assert spacer_cell.is_literal_zero is False
    assert spacer_cell.is_formula_zero is False

    # Row 89 (S&M Workers Comp Insurance) has literal numeric zeros
    zero_cell = is_stmt.get_item_by_row(89).get_cell("2026-06")
    assert zero_cell.is_blank is False
    assert zero_cell.is_literal_zero is True
    assert zero_cell.is_formula_zero is False
    assert zero_cell.effective_value == 0.0


def test_dormant_accounts_preserved(statements):
    """Verify rows 89-92 are flagged as dormant, preserved in source model with zero values."""
    is_stmt, _ = statements

    for r in [89, 90, 91, 92]:
        item = is_stmt.get_item_by_row(r)
        assert item.is_dormant is True
        for p in is_stmt.get_period_keys():
            val = item.get_value(p)
            assert val == 0.0, f"Row {r} period {p} was expected to be 0.0, got {val}"


def test_source_anomalies_preserved(statements):
    """Verify Dec 2025 tax benefit, SBC, HSA negative, and label formatting anomalies."""
    is_stmt, bs_stmt = statements

    # 1. Dec 2025 Tax Benefit in I101
    tax_ben_cell = is_stmt.get_item_by_row(101).get_cell("2025-12")
    assert tax_ben_cell.effective_value == -1244429.84

    # Resulting negative OpEx in I103
    opex_cell = is_stmt.get_item_by_row(103).get_cell("2025-12")
    assert abs(opex_cell.effective_value - (-402142.09)) < 0.01

    # 2. Dec 2025 SBC in I99
    sbc_cell = is_stmt.get_item_by_row(99).get_cell("2025-12")
    assert sbc_cell.effective_value == 334660.53

    # 3. HSA liability row 48 holds negative balances
    hsa_item = bs_stmt.get_item_by_row(48)
    assert hsa_item.get_value("2026-06") == -1290.0
    assert hsa_item.get_value("2025-08") == -1450.0
    assert all((hsa_item.get_value(p) or 0.0) <= 0.0 for p in bs_stmt.get_period_keys())

    # 4. Unicode U+2013 en-dash and trailing whitespace preserved
    c35_item = bs_stmt.get_item_by_row(35)
    c68_item = bs_stmt.get_item_by_row(68)
    c53_item = bs_stmt.get_item_by_row(53)

    assert "\u2013" in c35_item.original_label
    assert "\u2013" in c35_item.normalized_label
    assert "\u2013" in c68_item.original_label
    assert "\u2013" in c68_item.normalized_label
    assert c53_item.original_label == "Credit Card 2 "
    assert c53_item.normalized_label == "Credit Card 2"
