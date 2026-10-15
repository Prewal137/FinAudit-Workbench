"""Automated tests for Phase 1 validation engine.

Verifies independent mathematical calculations for all 18 formula rows, Balance
Sheet reconciliation, missing-cache handling, and downstream execution gating.
"""

import json
from pathlib import Path
import pytest

from src.ingestion import load_financial_workbook
from src.models import (
    CellValue,
    FinancialLineItem,
    FinancialStatement,
    FindingSeverity,
    FindingStatus,
    PeriodHeader,
    RowClassification,
    ValidationFinding,
    ValidationReport,
)
from src.reporting import (
    DEFAULT_DATA_PROFILE_PATH,
    DEFAULT_VALIDATION_REPORT_PATH,
    build_data_profile,
    save_data_profile,
    save_validation_report,
)
from src.validation import validate_duplicate_account_labels, validate_financial_statements

WORKBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "input" / "ABC Inc - Financial Statements.xlsx"


@pytest.fixture(scope="module")
def validation_report():
    """Run full validation once on the ingested statements."""
    is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
    return validate_financial_statements(is_stmt, bs_stmt)


def test_full_validation_passes_on_real_workbook(validation_report):
    """Verify that the actual source workbook passes all critical validation checks."""
    assert validation_report.is_valid is True, "Validation failed on real workbook"
    assert validation_report.can_proceed_to_downstream is True

    # Critical findings should have zero FAILED or UNABLE_TO_EVALUATE
    failing_critical = [
        f for f in validation_report.critical_findings
        if f.status in (FindingStatus.FAILED, FindingStatus.UNABLE_TO_EVALUATE)
    ]
    assert len(failing_critical) == 0, f"Critical failures found: {failing_critical}"

    # Verify expected warnings and info findings exist
    warning_rules = {f.rule_id for f in validation_report.warning_findings}
    assert "VAL-ANOM-01" in warning_rules  # Dec 2025 Tax Benefit
    assert "VAL-ANOM-02" in warning_rules  # Dec 2025 SBC
    assert "VAL-ANOM-03" in warning_rules  # HSA Liability negative

    info_rules = {f.rule_id for f in validation_report.info_findings}
    assert "VAL-ANOM-04" in info_rules  # Dormant rows 89-92
    assert "VAL-FMT-01" in info_rules   # Unicode & trailing space


def test_all_18_formula_rows_mathematical_integrity(validation_report):
    """Assert all 18 formula rows (8 IS + 10 BS) pass independent calculations across all 18 periods."""
    is_formula_rules = [
        "VAL-IS-04",  # Row 14 Total Income
        "VAL-IS-05",  # Row 24 Total COGS
        "VAL-IS-01",  # Row 26 Gross Profit
        "VAL-IS-06",  # Row 59 Total S&M Payroll
        "VAL-IS-07",  # Row 71 Total Marketing
        "VAL-IS-08",  # Row 103 Total OpEx (avoids double-counting nested groups)
        "VAL-IS-02",  # Row 105 Operating Income
        "VAL-IS-03",  # Row 107 Net Income
    ]

    bs_formula_rules = [
        "VAL-BS-06",  # Row 15 Total Cash
        "VAL-BS-01",  # Row 27 Total Current Assets
        "VAL-BS-07",  # Row 33 Total Fixed Assets
        "VAL-BS-08",  # Row 36 Total Long Term Assets
        "VAL-BS-02",  # Row 37 Total Assets
        "VAL-BS-09",  # Row 54 Total Current Liabilities
        "VAL-BS-10",  # Row 58 Total Long Term Liabilities
        "VAL-BS-03",  # Row 59 Total Liabilities
        "VAL-BS-11",  # Row 70 Total Equity
        "VAL-BS-04",  # Row 71 Total L&E
    ]

    all_18_rules = is_formula_rules + bs_formula_rules
    assert len(all_18_rules) == 18

    for rule_id in all_18_rules:
        rule_findings = [f for f in validation_report.findings if f.rule_id == rule_id]
        assert len(rule_findings) == 18, (
            f"Rule {rule_id} expected 18 findings (one per period), got {len(rule_findings)}"
        )
        for f in rule_findings:
            assert f.status == FindingStatus.PASSED, (
                f"Rule {rule_id} failed for period {f.period}: {f.details}"
            )


def test_balance_sheet_full_reconciliation(validation_report):
    """Assert Total Assets == Total Liabilities & Equity across all 18 months."""
    reconciliation_findings = [f for f in validation_report.findings if f.rule_id == "VAL-BS-05"]
    assert len(reconciliation_findings) == 18

    for f in reconciliation_findings:
        assert f.status == FindingStatus.PASSED, f"BS balance reconciliation failed for {f.period}: {f.details}"
        assert abs(f.actual_value - f.expected_value) < 0.01


def test_validation_pipeline_blocking():
    """Verify that any CRITICAL failure blocks downstream pipeline while preserving findings."""
    report = ValidationReport()
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-TEST-01",
            severity=FindingSeverity.INFO,
            status=FindingStatus.PASSED,
            statement="Test",
        )
    )
    assert report.is_valid is True
    assert report.can_proceed_to_downstream is True

    # Inject critical failure
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-BS-05",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.FAILED,
            statement="Balance Sheet",
            period="2026-06",
            details="Simulated imbalance between Assets and L&E",
        )
    )

    # Downstream execution must be strictly blocked
    assert report.is_valid is False
    assert report.can_proceed_to_downstream is False
    assert len(report.findings) == 2


def test_missing_cache_unable_to_evaluate_handling():
    """Verify that missing inputs or cached values yield UNABLE_TO_EVALUATE and block pipeline."""
    report = ValidationReport()
    report.add_finding(
        ValidationFinding(
            rule_id="VAL-ENG-01",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.UNABLE_TO_EVALUATE,
            statement="Income Statement",
            details="Formula cache missing for Row 14 2026-06",
        )
    )

    assert report.is_valid is False
    assert report.can_proceed_to_downstream is False
    assert len(report.critical_findings) == 1
    assert report.critical_findings[0].status == FindingStatus.UNABLE_TO_EVALUATE


def test_duplicate_account_labels_rule_on_real_workbook(validation_report):
    """Verify that the actual source workbook has zero duplicate detail account labels."""
    dup_findings = [f for f in validation_report.findings if f.rule_id == "VAL-DUP-01"]
    assert len(dup_findings) == 2, "Expected 2 VAL-DUP-01 findings (one for IS, one for BS)"

    for f in dup_findings:
        assert f.status == FindingStatus.PASSED, f"Unexpected duplicate label failure: {f.details}"
        assert "All detail account labels are unique" in f.details


def test_duplicate_account_labels_rule_detects_duplicates_in_test_data():
    """Verify that duplicate detail account labels within a section are detected and report row numbers."""
    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=[PeriodHeader("Month 1", "2026-01", 4, "D")],
        items=[
            FinancialLineItem(
                sheet_name="Income Statement",
                row_number=34,
                original_label="Consulting",
                normalized_label="Consulting",
                classification=RowClassification.DETAIL_ACCOUNT,
                hierarchy_path=("EXPENSES", "Direct OpEx"),
                values_by_period={"2026-01": CellValue(literal_value=5000.0)},
            ),
            FinancialLineItem(
                sheet_name="Income Statement",
                row_number=45,
                original_label="Consulting",
                normalized_label="Consulting",
                classification=RowClassification.DETAIL_ACCOUNT,
                hierarchy_path=("EXPENSES", "Direct OpEx"),
                values_by_period={"2026-01": CellValue(literal_value=7000.0)},
            ),
        ],
    )

    report = ValidationReport()
    validate_duplicate_account_labels(stmt, report)

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.rule_id == "VAL-DUP-01"
    assert finding.status == FindingStatus.FAILED
    assert finding.severity == FindingSeverity.WARNING
    assert finding.row_number == 34
    assert "rows [34, 45]" in finding.details
    assert "EXPENSES > Direct OpEx" in finding.details


def test_duplicate_account_labels_rule_ignores_legitimate_repeated_headings():
    """Verify that headings sharing the same text as detail accounts (e.g. Marketing/Advertising) do not trigger false positives."""
    stmt = FinancialStatement(
        statement_name="Income Statement",
        periods=[PeriodHeader("Month 1", "2026-01", 4, "D")],
        items=[
            # Row 60 is a subsection heading
            FinancialLineItem(
                sheet_name="Income Statement",
                row_number=60,
                original_label="Marketing/Advertising",
                normalized_label="Marketing/Advertising",
                classification=RowClassification.SUBSECTION_HEADING,
                hierarchy_path=("EXPENSES",),
                values_by_period={},
            ),
            # Row 61 is a detail account in that subsection
            FinancialLineItem(
                sheet_name="Income Statement",
                row_number=61,
                original_label="Marketing/Advertising",
                normalized_label="Marketing/Advertising",
                classification=RowClassification.DETAIL_ACCOUNT,
                hierarchy_path=("EXPENSES", "Marketing"),
                values_by_period={"2026-01": CellValue(literal_value=12000.0)},
            ),
            # Row 71 is a subtotal
            FinancialLineItem(
                sheet_name="Income Statement",
                row_number=71,
                original_label="Total Marketing/Advertising",
                normalized_label="Total Marketing/Advertising",
                classification=RowClassification.SUBTOTAL,
                hierarchy_path=("EXPENSES", "Marketing"),
                values_by_period={"2026-01": CellValue(cached_value=12000.0, formula_text="=SUM(D61:D70)")},
            ),
        ],
    )

    report = ValidationReport()
    validate_duplicate_account_labels(stmt, report)

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.rule_id == "VAL-DUP-01"
    assert finding.status == FindingStatus.PASSED, "Legitimate repeated headings must not be flagged as duplicate accounts"


def test_data_profile_artifact_content_and_structure():
    """Verify data_profile.json artifact is valid, reproducible, and distinguishes measured vs documented anomalies."""
    is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
    profile = build_data_profile(is_stmt, bs_stmt, workbook_path=WORKBOOK_PATH)

    # Core required sections
    assert "metadata" in profile
    assert profile["metadata"]["workbook_sha256"] == "75da8d679a89551f9e46b3563b7cfc724d9aaeabe0444b0214d455a0b335a0ea"

    assert "sheet_dimensions" in profile
    assert profile["sheet_dimensions"]["Income Statement"]["max_row"] == 107
    assert profile["sheet_dimensions"]["Income Statement"]["max_column"] == 25
    assert profile["sheet_dimensions"]["Balance Sheet"]["max_row"] == 71
    assert profile["sheet_dimensions"]["Balance Sheet"]["max_column"] == 26

    assert "reporting_periods" in profile
    assert profile["reporting_periods"]["period_count"] == 18
    assert profile["reporting_periods"]["chronological_start"] == "2025-01"
    assert profile["reporting_periods"]["chronological_end"] == "2026-06"

    assert "row_classification_counts" in profile
    assert profile["row_classification_counts"]["Income Statement"]["total_rows"] == 107
    assert profile["row_classification_counts"]["Balance Sheet"]["total_rows"] == 71

    assert "missing_value_statistics" in profile
    is_stats = profile["missing_value_statistics"]["Income Statement"]
    assert is_stats["detail_account_count"] == 83
    assert is_stats["dormant_account_count"] == 4
    assert is_stats["dormant_account_zero_cells"] == 72
    assert is_stats["detail_account_missing_effective_values"] == 0

    # Distinguish measured statistics from documented observations
    assert "known_source_anomalies" in profile
    anomalies = profile["known_source_anomalies"]
    assert "measured_statistics" in anomalies
    assert "documented_observations" in anomalies

    measured = anomalies["measured_statistics"]
    assert measured["dec_2025_tax_benefit_usd"] == -1244429.84
    assert measured["dec_2025_stock_based_compensation_usd"] == 334660.53
    assert measured["hsa_liability_negative_period_count"] > 0
    assert measured["trailing_empty_columns_populated_cell_count"]["Income Statement"] == 0
    assert measured["trailing_empty_columns_populated_cell_count"]["Balance Sheet"] == 0

    documented = anomalies["documented_observations"]
    assert "december_2025_tax_benefit" in documented
    assert "stock_based_compensation" in documented
    assert "hsa_liability_debit_balance" in documented


def test_validation_report_artifact_content_and_structure(tmp_path):
    """Verify validation_report.json artifact is saved reproducibly with real check results."""
    is_stmt, bs_stmt = load_financial_workbook(WORKBOOK_PATH)
    val_report = validate_financial_statements(is_stmt, bs_stmt)

    out_file = tmp_path / "validation_report.json"
    saved_path = save_validation_report(val_report, out_file)
    assert saved_path.exists()

    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "summary" in data
    summary = data["summary"]
    assert summary["total_findings"] >= 356
    assert summary["passed"] >= 356
    assert summary["failed"] == 0
    assert summary["is_valid"] is True
    assert summary["can_proceed"] is True

    assert "findings" in data
    assert len(data["findings"]) == summary["total_findings"]
    # Check that check names (rule_id), severities, and statuses are recorded
    first_finding = data["findings"][0]
    assert "rule_id" in first_finding
    assert "severity" in first_finding
    assert "status" in first_finding
    assert "statement" in first_finding
