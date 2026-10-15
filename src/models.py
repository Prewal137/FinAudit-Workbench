"""Data models for FinAudit-Workbench workbook ingestion and validation.

Defined in accordance with docs/workbook_ingestion_spec.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class RowClassification(str, Enum):
    """Mutually exclusive taxonomic classification for each workbook row."""
    METADATA = "METADATA"
    HEADER = "HEADER"
    SPACER = "SPACER"
    SECTION_HEADING = "SECTION_HEADING"
    SUBSECTION_HEADING = "SUBSECTION_HEADING"
    DETAIL_ACCOUNT = "DETAIL_ACCOUNT"
    SUBTOTAL = "SUBTOTAL"
    CALCULATED_RESULT = "CALCULATED_RESULT"


class FindingSeverity(str, Enum):
    """Validation finding severity levels."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class FindingStatus(str, Enum):
    """Validation finding evaluation status."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNABLE_TO_EVALUATE = "UNABLE_TO_EVALUATE"


@dataclass
class CellValue:
    """Cell value provenance tracking literal content, formula text, and cached results."""
    literal_value: Optional[Union[float, int, str]] = None
    formula_text: Optional[str] = None
    cached_value: Optional[Union[float, int, str]] = None

    @property
    def is_blank(self) -> bool:
        """True strictly when cell contains neither literal content nor formula."""
        return (
            self.literal_value is None
            and self.formula_text is None
            and self.cached_value is None
        )

    @property
    def is_literal_zero(self) -> bool:
        """True strictly when literal stored value is numeric zero."""
        if self.formula_text is not None:
            return False
        return self.literal_value in (0, 0.0)

    @property
    def is_formula_zero(self) -> bool:
        """True strictly when cell has a formula that evaluates to zero."""
        if self.formula_text is None:
            return False
        return self.cached_value in (0, 0.0)

    @property
    def effective_value(self) -> Optional[float]:
        """Numeric value to use in financial calculations."""
        val = self.cached_value if self.formula_text is not None else self.literal_value
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


@dataclass
class PeriodHeader:
    """Header information for a monthly reporting period."""
    original_header: str
    normalized_period: str  # Format: 'YYYY-MM'
    column_index: int       # 1-indexed Excel column index
    column_letter: str      # Coordinate letter (e.g., 'C')


@dataclass
class FinancialLineItem:
    """Single financial line item representing an entire Excel row."""
    sheet_name: str
    row_number: int
    original_label: str
    normalized_label: str
    classification: RowClassification
    hierarchy_path: Tuple[str, ...] = field(default_factory=tuple)
    is_dormant: bool = False
    values_by_period: Dict[str, CellValue] = field(default_factory=dict)

    def get_value(self, period: str) -> Optional[float]:
        """Retrieve effective numeric value for a given canonical period."""
        cell = self.values_by_period.get(period)
        return cell.effective_value if cell is not None else None

    def get_cell(self, period: str) -> Optional[CellValue]:
        """Retrieve CellValue object for a given canonical period."""
        return self.values_by_period.get(period)


@dataclass
class FinancialStatement:
    """Represents an entire ingested financial statement worksheet."""
    statement_name: str
    periods: List[PeriodHeader] = field(default_factory=list)
    items: List[FinancialLineItem] = field(default_factory=list)
    trailing_empty_columns_verified: bool = False

    def get_item_by_row(self, row_number: int) -> FinancialLineItem:
        """Retrieve line item by 1-indexed Excel row number."""
        for item in self.items:
            if item.row_number == row_number:
                return item
        raise KeyError(f"Row {row_number} not found in statement {self.statement_name}")

    def get_item_by_label(self, normalized_label: str) -> Optional[FinancialLineItem]:
        """Retrieve line item by normalized label string."""
        for item in self.items:
            if item.normalized_label == normalized_label:
                return item
        return None

    def get_detail_accounts(self) -> List[FinancialLineItem]:
        """Retrieve all line items classified as DETAIL_ACCOUNT."""
        return [item for item in self.items if item.classification == RowClassification.DETAIL_ACCOUNT]

    def get_period_keys(self) -> List[str]:
        """List of normalized period strings in order."""
        return [p.normalized_period for p in self.periods]


@dataclass
class ValidationFinding:
    """Individual finding produced by a validation rule check."""
    rule_id: str
    severity: FindingSeverity
    status: FindingStatus
    statement: str
    period: Optional[str] = None
    details: str = ""
    actual_value: Optional[float] = None
    expected_value: Optional[float] = None
    row_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize finding to dictionary."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "status": self.status.value,
            "statement": self.statement,
            "period": self.period,
            "details": self.details,
            "actual_value": self.actual_value,
            "expected_value": self.expected_value,
            "row_number": self.row_number,
        }


@dataclass
class ValidationReport:
    """Consolidated audit report containing all validation findings."""
    findings: List[ValidationFinding] = field(default_factory=list)

    def add_finding(self, finding: ValidationFinding) -> None:
        """Append a validation finding to the report."""
        self.findings.append(finding)

    @property
    def is_valid(self) -> bool:
        """True if and only if no CRITICAL finding has FAILED or UNABLE_TO_EVALUATE status."""
        for f in self.findings:
            if f.severity == FindingSeverity.CRITICAL and f.status in (
                FindingStatus.FAILED,
                FindingStatus.UNABLE_TO_EVALUATE,
            ):
                return False
        return True

    @property
    def can_proceed_to_downstream(self) -> bool:
        """Gate check: downstream phases may proceed only when is_valid is True."""
        return self.is_valid

    @property
    def critical_findings(self) -> List[ValidationFinding]:
        """Filter findings with CRITICAL severity."""
        return [f for f in self.findings if f.severity == FindingSeverity.CRITICAL]

    @property
    def warning_findings(self) -> List[ValidationFinding]:
        """Filter findings with WARNING severity."""
        return [f for f in self.findings if f.severity == FindingSeverity.WARNING]

    @property
    def info_findings(self) -> List[ValidationFinding]:
        """Filter findings with INFO severity."""
        return [f for f in self.findings if f.severity == FindingSeverity.INFO]

    @property
    def failed_findings(self) -> List[ValidationFinding]:
        """Filter findings with FAILED status."""
        return [f for f in self.findings if f.status == FindingStatus.FAILED]

    def summary(self) -> Dict[str, Any]:
        """Summary statistics of findings."""
        return {
            "total_findings": len(self.findings),
            "passed": len([f for f in self.findings if f.status == FindingStatus.PASSED]),
            "failed": len([f for f in self.findings if f.status == FindingStatus.FAILED]),
            "unable_to_evaluate": len([f for f in self.findings if f.status == FindingStatus.UNABLE_TO_EVALUATE]),
            "critical_issues": len([
                f for f in self.critical_findings
                if f.status in (FindingStatus.FAILED, FindingStatus.UNABLE_TO_EVALUATE)
            ]),
            "warnings": len(self.warning_findings),
            "is_valid": self.is_valid,
            "can_proceed": self.can_proceed_to_downstream,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete validation report including summary and findings."""
        return {
            "summary": self.summary(),
            "findings": [f.to_dict() for f in self.findings],
        }

    def save_json(self, path: Union[str, Path]) -> Path:
        """Reproducibly save validation results to a JSON file."""
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return target_path
