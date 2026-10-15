# FinAudit-Workbench: Verified Workbook Ingestion Specification

**Workbook Target:** `data/input/ABC Inc - Financial Statements.xlsx`  
**Status:** Final Verified Specification (Audited against source workbook and verification script)  
**Scope:** Phase 1 Ingestion, Data Modeling, and Validation Architecture  

---

## 1. Workbook Structure & Layout

### 1.1 Sheet Definitions & Spatial Coordinates
* **Source File:** `data/input/ABC Inc - Financial Statements.xlsx` (Strictly read-only; source file must remain immutable).
* **Income Statement Sheet:**
  * Exact Sheet Name: `'Income Statement'`
  * Allocated Dimensions: 107 rows × 25 columns (`A1:Y107`).
  * Header Row: Row 5.
  * Metadata Rows: Rows 1–3 (`Row 1: ABC Inc.`, `Row 2: Income Statement`, `Row 3: For the month ended June 30, 2026`).
  * Active Period Columns: Columns C through T (18 distinct monthly columns, indices 3 through 20).
  * Trailing Columns: Columns U through Y (5 columns, indices 21 through 25). Executed check confirmed: exactly 0 populated cells across all 107 rows.
  * Primary Label Columns:
    * Column A: Top-level section headings (`INCOME`, `COST OF GOODS SOLD`, `EXPENSES`) and summary calculated results (`Gross Profit`, `Operating Income`, `Net Income`).
    * Column B: Transactional accounts, subsection headings, and intermediate subtotals.
* **Balance Sheet Sheet:**
  * Exact Sheet Name: `'Balance Sheet'`
  * Allocated Dimensions: 71 rows × 26 columns (`A1:Z71`).
  * Header Row: Row 5.
  * Metadata Rows: Rows 1–3 (`Row 1: ABC Inc.`, `Row 2: Balance Sheet`, `Row 3: As of June 30, 2026`).
  * Active Period Columns: Columns D through U (18 distinct monthly columns, indices 4 through 21).
  * Trailing Columns: Columns V through Z (5 columns, indices 22 through 26). Executed check confirmed: exactly 0 populated cells across all 71 rows.
  * Primary Label Columns:
    * Column A: Top-level section headings (`ASSETS`, `LIABILITIES & EQUITY`) and aggregate calculated totals (`Total Assets`, `Total Liabilities & Equity`).
    * Column B: Major category headings (`Current Assets`, `Fixed Assets`, `Long Term Assets`, `Current Liabilities`, `Equity`), category subtotals (`Total Current Assets`, `Total Fixed Assets`, `Total Current Liabilities`, `Total Long Term Liabilities`, `Total Equity`), and calculated result `Total Liabilities`.
    * Column C: Detail account labels, subsection headers (`Cash and Cash Equivalents`, `Other Current Liabilities`, `Long Term Liabilities`), and group subtotal `Total Cash and Cash Equivalents`.

### 1.2 Monthly Reporting Periods
* **Total Period Count:** Exactly 18 calendar months per sheet.
* **Period Ordering:** Reverse chronological sequence (newest month at leftmost column, oldest month at rightmost column).
* **Observed Row 5 Headers:**
  * Income Statement (Cols C–T): `['Jun 2026', 'May 2026', 'Apr 2026', 'Mar 2026', 'Feb 2026', 'Jan 2026', 'Dec 2025', 'Nov 2025', 'Oct 2025', 'Sep 2025', 'Aug 2025', 'Jul 2025', 'Jun 2025', 'May 2025', 'Apr 2025', 'Mar 2025', 'Feb 2025', 'Jan 2025']`
  * Balance Sheet (Cols D–U): `['30 Jun 2026', '31 May 2026', '30 Apr 2026', '31 Mar 2026', '28 Feb 2026', '31 Jan 2026', '31 Dec 2025', '30 Nov 2025', '31 Oct 2025', '30 Sep 2025', '31 Aug 2025', '31 Jul 2025', '30 Jun 2025', '31 May 2025', '30 Apr 2025', '31 Mar 2025', '28 Feb 2025', '31 Jan 2025']`
* **Canonical Period Representation:**
  * All periods use standardized ISO year-month strings (`'YYYY-MM'`) as canonical dictionary and mapping keys (`'2026-06'` down to `'2025-01'`).
  * Explicit date objects (`datetime.date`, e.g. `2026-06-30`) are parsed on-demand only for chronological calculations, sorting, and delta math.
  * Cross-Sheet Parity: All 18 periods align 1:1 between Income Statement and Balance Sheet.

---

## 2. Row Classification Taxonomy & Explicit Workbook Mapping

### 2.1 Taxonomy Definition
Each workbook row is classified into exactly one mutually exclusive taxonomic type:
1. `METADATA`: Descriptive header lines in rows 1–3.
2. `HEADER`: Column header row (row 5) defining period names.
3. `SPACER`: Structural blank rows containing neither labels nor values.
4. `SECTION_HEADING`: Top-level financial statement partition (Col A text, no numeric values, no formulas).
5. `SUBSECTION_HEADING`: Intermediate grouping header (Col B in IS, Col B/C in BS; text label, no values, no formulas).
6. `DETAIL_ACCOUNT`: Individual transactional general ledger account containing literal numbers (or inactive zero balances).
7. `SUBTOTAL`: Intermediate additive rollup computed via `=SUM(...)` or additive subtotal references.
8. `CALCULATED_RESULT`: Derived net metric computed via arithmetic relationships (e.g., Gross Profit, Operating Income, Net Income, Total Assets).

### 2.2 Workbook-Specific Explicit Row Map
The ingestion engine applies an explicit, workbook-specific row map. Structural assertions verify row labels, formula presence, and column layout during ingestion to detect unexpected layout modifications.

#### Income Statement Explicit Map (107 Rows Total)
* **Metadata & Structural Spacers:**
  * Rows 1–3: `METADATA` (3 rows)
  * Rows 4, 6, 15, 25, 27, 104, 106: `SPACER` (7 rows)
  * Row 5: `HEADER` (1 row)
* **Income Partition:**
  * Row 7: `SECTION_HEADING` (`INCOME`, Col A)
  * Rows 8–13: `DETAIL_ACCOUNT` (6 accounts; Cols C–T populated)
  * Row 14: `SUBTOTAL` (`Total Income`, Col B; formula `=SUM(Col8:Col13)`)
* **COGS Partition:**
  * Row 16: `SECTION_HEADING` (`COST OF GOODS SOLD`, Col A)
  * Rows 17–23: `DETAIL_ACCOUNT` (7 accounts; Cols C–T populated)
  * Row 24: `SUBTOTAL` (`Total Cost of Goods Sold`, Col B; formula `=SUM(Col17:Col23)`)
* **Gross Profit Metric:**
  * Row 26: `CALCULATED_RESULT` (`Gross Profit`, Col A; formula `=(Col14 - Col24)`)
* **Operating Expenses Partition:**
  * Row 28: `SECTION_HEADING` (`EXPENSES`, Col A)
  * Rows 29–46: `DETAIL_ACCOUNT` (18 Direct OpEx accounts)
  * Row 47: `SUBSECTION_HEADING` (`Sales & Marketing Payroll`, Col B)
  * Rows 48–58: `DETAIL_ACCOUNT` (11 S&M Payroll accounts)
  * Row 59: `SUBTOTAL` (`Total Sales & Marketing Payroll`, Col B; formula `=SUM(Col48:Col58)`)
  * Row 60: `SUBSECTION_HEADING` (`Marketing`, Col B)
  * Rows 61–70: `DETAIL_ACCOUNT` (10 Marketing accounts)
  * Row 71: `SUBTOTAL` (`Total Marketing`, Col B; formula `=SUM(Col61:Col70)`)
  * Rows 72–102: `DETAIL_ACCOUNT` (31 Other OpEx accounts, including dormant rows 89–92 and Dec 2025 entries in rows 99 and 101)
  * Row 103: `SUBTOTAL` (`Total Operating Expenses`, Col B; formula `=(SUM(Col29:Col46,Col72:Col102) + (Col59 + Col71))`)
* **Operating & Net Results:**
  * Row 105: `CALCULATED_RESULT` (`Operating Income`, Col A; formula `=(Col26 - Col103)`)
  * Row 107: `CALCULATED_RESULT` (`Net Income`, Col A; formula `=(Col105 + 0)`)
* **Income Statement Classification Summary:**
  * `METADATA`: 3 rows (Rows 1–3)
  * `HEADER`: 1 row (Row 5)
  * `SPACER`: 7 rows (Rows 4, 6, 15, 25, 27, 104, 106)
  * `SECTION_HEADING`: 3 rows (Rows 7, 16, 28)
  * `SUBSECTION_HEADING`: 2 rows (Rows 47, 60)
  * `DETAIL_ACCOUNT`: 83 rows (Rows 8–13, 17–23, 29–46, 48–58, 61–70, 72–102)
  * `SUBTOTAL`: 5 rows (Rows 14, 24, 59, 71, 103)
  * `CALCULATED_RESULT`: 3 rows (Rows 26, 105, 107)
  * **Total Income Statement Rows:** 3 + 1 + 7 + 3 + 2 + 83 + 5 + 3 = **107 Rows**.

#### Balance Sheet Explicit Map (71 Rows Total)
* **Metadata & Structural Spacers:**
  * Rows 1–3: `METADATA` (3 rows: 1, 2, 3)
  * Rows 4, 6, 38: `SPACER` (3 rows: 4, 6, 38)
  * Row 5: `HEADER` (1 row: 5)
* **Assets Partition:**
  * Row 7: `SECTION_HEADING` (`ASSETS`, Col A)
  * Row 8: `SUBSECTION_HEADING` (`Current Assets`, Col B)
  * Row 9: `SUBSECTION_HEADING` (`Cash and Cash Equivalents`, Col C)
  * Rows 10–14: `DETAIL_ACCOUNT` (5 detail cash accounts, Col C)
  * Row 15: `SUBTOTAL` (`Total Cash and Cash Equivalents`, Col C; formula `=SUM(Col10:Col14)`)
  * Rows 16–26: `DETAIL_ACCOUNT` (11 current asset accounts, Col C)
  * Row 27: `SUBTOTAL` (`Total Current Assets`, Col B; formula `=(SUM(Col16:Col26) + Col15)`)
  * Row 28: `SUBSECTION_HEADING` (`Fixed Assets`, Col B)
  * Rows 29–32: `DETAIL_ACCOUNT` (4 fixed asset accounts, Col C)
  * Row 33: `SUBTOTAL` (`Total Fixed Assets`, Col B; formula `=SUM(Col29:Col32)`)
  * Row 34: `SUBSECTION_HEADING` (`Long Term Assets`, Col B)
  * Row 35: `DETAIL_ACCOUNT` (`Deferred Tax Asset – NOL`, Col C)
  * Row 36: `CALCULATED_RESULT` (`Total Long Term Assets`, Col B; formula `=Col35`)
  * Row 37: `CALCULATED_RESULT` (`Total Assets`, Col A; formula `=(0 + ((Col27 + Col33) + Col36))`)
* **Liabilities & Equity Partition:**
  * Row 39: `SECTION_HEADING` (`LIABILITIES & EQUITY`, Col A)
  * Row 40: `SUBSECTION_HEADING` (`Current Liabilities`, Col B)
  * Row 41: `SUBSECTION_HEADING` (`Other Current Liabilities`, Col C)
  * Rows 42–53: `DETAIL_ACCOUNT` (12 current liability accounts, Col C)
  * Row 54: `SUBTOTAL` (`Total Current Liabilities`, Col B; formula `=SUM(Col42:Col53)`)
  * Row 55: `SUBSECTION_HEADING` (`Long Term Liabilities`, Col C)
  * Rows 56–57: `DETAIL_ACCOUNT` (2 long-term liability accounts, Col C)
  * Row 58: `SUBTOTAL` (`Total Long Term Liabilities`, Col B; formula `=SUM(Col56:Col57)`)
  * Row 59: `CALCULATED_RESULT` (`Total Liabilities`, Col B; formula `=(0 + (Col54 + Col58))`)
  * Row 60: `SUBSECTION_HEADING` (`Equity`, Col B)
  * Rows 61–69: `DETAIL_ACCOUNT` (9 equity accounts, Col C)
  * Row 70: `SUBTOTAL` (`Total Equity`, Col B; formula `=SUM(Col61:Col69)`)
  * Row 71: `CALCULATED_RESULT` (`Total Liabilities & Equity`, Col A; formula `=(0 + (Col59 + Col70))`)
* **Balance Sheet Classification Summary:**
  * `METADATA`: 3 rows (Rows 1, 2, 3)
  * `HEADER`: 1 row (Row 5)
  * `SPACER`: 3 rows (Rows 4, 6, 38)
  * `SECTION_HEADING`: 2 rows (Rows 7, 39)
  * `SUBSECTION_HEADING`: 8 rows (Rows 8, 9, 28, 34, 40, 41, 55, 60)
  * `DETAIL_ACCOUNT`: 44 rows (Rows 10–14, 16–26, 29–32, 35, 42–53, 56–57, 61–69)
  * `SUBTOTAL`: 6 rows (Rows 15, 27, 33, 54, 58, 70)
  * `CALCULATED_RESULT`: 4 rows (Rows 36, 37, 59, 71)
  * **Total Balance Sheet Rows:** 3 + 1 + 3 + 2 + 8 + 44 + 6 + 4 = **71 Rows**.

---

## 3. Data Model Requirements (`src/models.py`)

### 3.1 Cell Value Provenance (`CellValue`)
Cell provenance strictly separates literal stored content, formula text, and cached results:
* `literal_value`: `Optional[Union[float, int, str]]` — Literal constant stored in the cell when no formula exists.
* `formula_text`: `Optional[str]` — Exact Excel formula string (e.g. `'=SUM(C8:C13)'`), or `None`.
* `cached_value`: `Optional[Union[float, int, str]]` — Evaluated result retrieved from Excel cache via `data_only=True`.
* `is_blank`: `bool` — Evaluates to `True` strictly when the cell contains neither literal content nor a formula (`literal_value is None and formula_text is None and cached_value is None`).
* `is_literal_zero`: `bool` — Evaluates to `True` strictly when `literal_value in (0, 0.0)`.
* `is_formula_zero`: `bool` — Evaluates to `True` strictly when `formula_text is not None` and `cached_value == 0.0`.
* `effective_value`: `Optional[float]` — Helper property returning `cached_value` if a formula exists, else `literal_value` if numeric, else `None`.

### 3.2 Financial Line Item (`FinancialLineItem`)
* `sheet_name`: `'Income Statement'` or `'Balance Sheet'`.
* `row_number`: 1-indexed Excel row coordinate (1 to 107 or 1 to 71).
* `original_label`: Exact string as stored in workbook (retains exact Unicode en-dashes and trailing whitespace).
* `normalized_label`: Sanitized string with trimmed whitespace while preserving Unicode characters.
* `classification`: Literal taxonomy enum (`METADATA`, `HEADER`, `SPACER`, `SECTION_HEADING`, `SUBSECTION_HEADING`, `DETAIL_ACCOUNT`, `SUBTOTAL`, `CALCULATED_RESULT`).
* `hierarchy_path`: Tuple of parent category strings (e.g. `('EXPENSES', 'Marketing')`).
* `is_dormant`: `bool` — Evaluates to `True` if all 18 period values are numeric zeros (e.g., IS rows 89–92).
  * **Preservation Rule:** Dormant accounts and all their monthly zero values are preserved in full within the source model; the flag is strictly descriptive.
* `values_by_period`: Dictionary mapping normalized canonical period string (`'YYYY-MM'`) to `CellValue`.

### 3.3 Period Header (`PeriodHeader`)
* `original_header`: Exact header string from row 5 (e.g., `'Jun 2026'`, `'30 Jun 2026'`).
* `normalized_period`: Standardized canonical period key `'YYYY-MM'` (e.g., `'2026-06'`).
* `column_index`: Integer column position (1-indexed: 3–20 for IS, 4–21 for BS).
* `column_letter`: Coordinate letter (`C`–`T` for IS, `D`–`U` for BS).

### 3.4 Financial Statement (`FinancialStatement`)
* `statement_name`: `'Income Statement'` or `'Balance Sheet'`.
* `periods`: Ordered list of `PeriodHeader` objects (18 periods, `2026-06` down to `2025-01`).
* `items`: Ordered list of `FinancialLineItem` objects.
* Lookup methods:
  * `get_item_by_row(row_number: int) -> FinancialLineItem`
  * `get_item_by_label(normalized_label: str) -> Optional[FinancialLineItem]`
  * `get_detail_accounts() -> List[FinancialLineItem]`

---

## 4. Complete Formula Validation Coverage & Loading Strategy

### 4.1 Coordinated Dual-Pass Loading
`openpyxl` requires dual-pass loading over the immutable source file:
1. **Pass A (`data_only=False`):** Ingests cell formulas (`cell.value` as string starting with `'='`) and literal non-formula values.
2. **Pass B (`data_only=True`):** Ingests Excel's cached precalculated results.
3. **Coordinate Pairing:** Matches cells 1:1 on `(sheet_name, row, col)`. Populates `literal_value`, `formula_text`, and `cached_value` accordingly.

### 4.2 Complete Inventory of All 18 Formula Rows & Independent Calculations
The workbook contains exactly 324 formula cells (18 formula rows × 18 columns). Each of the 18 formula rows has a specified independent calculation rule defined below. These rules represent the required verification criteria and become formally verified only after the Phase 1 test suite (`tests/test_validation.py`) executes successfully against the source workbook across all 18 periods.

#### Income Statement Formula Rows (8 Rows × 18 Columns = 144 Formula Cells)
1. **Row 14 — Total Income (`SUBTOTAL`):**
   * *Source Formula Pattern (Col C):* `=SUM(C8:C13)`
   * *Independent Calculation:* `SUM(Row 8 through Row 13)` across all 18 periods.
2. **Row 24 — Total Cost of Goods Sold (`SUBTOTAL`):**
   * *Source Formula Pattern (Col C):* `=SUM(C17:C23)`
   * *Independent Calculation:* `SUM(Row 17 through Row 23)` across all 18 periods.
3. **Row 26 — Gross Profit (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col C):* `=(C14 - C24)`
   * *Independent Calculation:* `Row 14 - Row 24` across all 18 periods.
4. **Row 59 — Total Sales & Marketing Payroll (`SUBTOTAL`):**
   * *Source Formula Pattern (Col C):* `=SUM(C48:C58)`
   * *Independent Calculation:* `SUM(Row 48 through Row 58)` across all 18 periods.
5. **Row 71 — Total Marketing (`SUBTOTAL`):**
   * *Source Formula Pattern (Col C):* `=SUM(C61:C70)`
   * *Independent Calculation:* `SUM(Row 61 through Row 70)` across all 18 periods.
6. **Row 103 — Total Operating Expenses (`SUBTOTAL`):**
   * *Source Formula Pattern (Col C):* `=(SUM(C29:C46,C72:C102) + (C59 + C71))`
   * *Independent Calculation:* `SUM(Row 29:Row 46) + SUM(Row 72:Row 102) + Row 59 + Row 71`.
   * *Double-Counting Safeguard:* Note that nested detail rows 48–58 (S&M Payroll) and rows 61–70 (Marketing) are explicitly omitted from the `SUM` ranges and enter solely through subtotals Row 59 and Row 71.
7. **Row 105 — Operating Income (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col C):* `=(C26 - C103)`
   * *Independent Calculation:* `Row 26 - Row 103` across all 18 periods.
8. **Row 107 — Net Income (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col C):* `=(C105 + 0)`
   * *Independent Calculation:* `Row 105 + 0.0` across all 18 periods.

#### Balance Sheet Formula Rows (10 Rows × 18 Columns = 180 Formula Cells)
1. **Row 15 — Total Cash and Cash Equivalents (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=SUM(D10:D14)`
   * *Independent Calculation:* `SUM(Row 10 through Row 14)` across all 18 periods.
2. **Row 27 — Total Current Assets (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=(SUM(D16:D26) + D15)`
   * *Independent Calculation:* `SUM(Row 16 through Row 26) + Row 15`. Detail cash rows 10–14 enter solely via subtotal Row 15.
3. **Row 33 — Total Fixed Assets (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=SUM(D29:D32)`
   * *Independent Calculation:* `SUM(Row 29 through Row 32)` across all 18 periods.
4. **Row 36 — Total Long Term Assets (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col D):* `=D35`
   * *Independent Calculation:* Value of Row 35 (`Deferred Tax Asset – NOL`) across all 18 periods.
5. **Row 37 — Total Assets (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col D):* `=(0 + ((D27 + D33) + D36))`
   * *Independent Calculation:* `Row 27 + Row 33 + Row 36` across all 18 periods.
6. **Row 54 — Total Current Liabilities (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=SUM(D42:D53)`
   * *Independent Calculation:* `SUM(Row 42 through Row 53)` across all 18 periods.
7. **Row 58 — Total Long Term Liabilities (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=SUM(D56:D57)`
   * *Independent Calculation:* `SUM(Row 56 through Row 57)` across all 18 periods.
8. **Row 59 — Total Liabilities (`CALCULATED_RESULT`):**
   * *Source Formula Pattern (Col D):* `=(0 + (D54 + D58))`
   * *Independent Calculation:* `Row 54 + Row 58` across all 18 periods.
9. **Row 70 — Total Equity (`SUBTOTAL`):**
   * *Source Formula Pattern (Col D):* `=SUM(D61:D69)`
   * *Independent Calculation:* `SUM(Row 61 through Row 69)` across all 18 periods.
10. **Row 71 — Total Liabilities & Equity (`CALCULATED_RESULT`):**
    * *Source Formula Pattern (Col D):* `=(0 + (D59 + D70))`
    * *Independent Calculation:* `Row 59 + Row 70` across all 18 periods.

### 4.3 Missing Formula Cache & Input Handling Policy
* If any formula cell yields `cached_value is None` or a required input is missing/unpopulated, the engine records a `CRITICAL` finding (`VAL-ENG-01`).
* The engine preserves the raw formula text and all available literal cell contents.
* Any dependent validation checks requiring the missing cached value or input are explicitly recorded as `UNABLE_TO_EVALUATE` (and never marked as passed), with explanatory context captured in the finding.
* Independent mathematical evaluations continue executing across all remaining unaffected rules to compile a complete audit report.
* **Downstream Gating:** The presence of any `CRITICAL` finding strictly blocks financial metrics calculations, reviewer commentary generation, and final report export, while preserving the serialized validation report for inspection.

---

## 5. Validation Rules & Verification Status

### 5.1 Pipeline Execution Architecture
* All validation checks are executed unconditionally across all 18 periods.
* When a required input coordinate, dependency, or cached result is unavailable, the validator records a finding with evaluation status `UNABLE_TO_EVALUATE` rather than recording a pass or aborting early.
* Every check generates a structured `ValidationFinding` containing `rule_id`, `severity` (`CRITICAL`, `WARNING`, `INFO`), `status` (`PASSED`, `FAILED`, `UNABLE_TO_EVALUATE`), `period`, `statement`, `details`, `actual_value`, and `expected_value`.
* A consolidated `ValidationReport` collects all findings.
* **Gating Policy:** If any `CRITICAL` finding exists (whether from a failed check or an unresolvable prerequisite), downstream phases (financial metrics engine, LLM reviewer commentary, and report export) are strictly blocked. The `ValidationReport` remains fully serialized and inspectable.

### 5.2 Validation Rules with Explicit Verification Status
Numeric comparisons use floating-point tolerance `abs(actual - expected) < 0.01`.

| Rule ID | Severity | Description & Target Rows | Verification Status |
|---|---|---|---|
| `VAL-PER-01` | `CRITICAL` | Exactly 18 periods per sheet in reverse chronological order | **Verified by script** (`verify_workbook.py` Section 2) |
| `VAL-PER-02` | `CRITICAL` | IS and BS periods align 1:1 by normalized year-month | **Verified by script** (`verify_workbook.py` Section 2) |
| `VAL-DIM-01` | `CRITICAL` | Trailing columns (IS U–Y, BS V–Z) contain 0 populated cells | **Verified by script** (`verify_workbook.py` Section 7) |
| `VAL-ENG-01` | `CRITICAL` | All 324 formula cells contain valid cached values | **Verified by script** (`verify_workbook.py` Section 3; 0 missing) |
| `VAL-IS-01` | `CRITICAL` | `Gross Profit (Row 26) == Row 14 - Row 24` across all 18 months | **Verified by script** (`verify_workbook.py` Section 4; 18 PASS) |
| `VAL-IS-02` | `CRITICAL` | `Operating Income (Row 105) == Row 26 - Row 103` across all 18 months | **Verified by script** (`verify_workbook.py` Section 4; 18 PASS) |
| `VAL-IS-03` | `CRITICAL` | `Net Income (Row 107) == Row 105` across all 18 months | **Verified by script** (`verify_workbook.py` Section 4; 18 PASS) |
| `VAL-IS-04` | `CRITICAL` | `Total Income (Row 14) == SUM(Rows 8:13)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-IS-05` | `CRITICAL` | `Total COGS (Row 24) == SUM(Rows 17:23)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-IS-06` | `CRITICAL` | `Total S&M Payroll (Row 59) == SUM(Rows 48:58)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-IS-07` | `CRITICAL` | `Total Marketing (Row 71) == SUM(Rows 61:70)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-IS-08` | `CRITICAL` | `Total OpEx (Row 103) == SUM(29:46, 72:102) + Row 59 + Row 71` | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-01` | `CRITICAL` | `Total Current Assets (Row 27) == SUM(Rows 16:26) + Row 15` | **Verified by script** (`verify_workbook.py` Section 5; 18 PASS) |
| `VAL-BS-02` | `CRITICAL` | `Total Assets (Row 37) == Row 27 + Row 33 + Row 36` | **Verified by script** (`verify_workbook.py` Section 5; 18 PASS) |
| `VAL-BS-03` | `CRITICAL` | `Total Liabilities (Row 59) == Row 54 + Row 58` | **Verified by script** (`verify_workbook.py` Section 5; 18 PASS) |
| `VAL-BS-04` | `CRITICAL` | `Total L&E (Row 71) == Row 59 + Row 70` | **Verified by script** (`verify_workbook.py` Section 5; 18 PASS) |
| `VAL-BS-05` | `CRITICAL` | `Total Assets (Row 37) == Total L&E (Row 71)` across all 18 months | **Verified by script** (`verify_workbook.py` Section 5; 18 PASS) |
| `VAL-BS-06` | `CRITICAL` | `Total Cash (Row 15) == SUM(Rows 10:14)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-07` | `CRITICAL` | `Total Fixed Assets (Row 33) == SUM(Rows 29:32)` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-08` | `CRITICAL` | `Total Long Term Assets (Row 36) == Row 35` across all 18 months | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-09` | `CRITICAL` | `Total Current Liabilities (Row 54) == SUM(Rows 42:53)` | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-10` | `CRITICAL` | `Total Long Term Liabilities (Row 58) == SUM(Rows 56:57)` | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-BS-11` | `CRITICAL` | `Total Equity (Row 70) == SUM(Rows 61:69)` | **Proposed Phase 1 Check** (to be tested in `tests/test_validation.py`) |
| `VAL-ANOM-01` | `WARNING` | Flag December 2025 Income Tax Benefit (`-$1,244,429.84` in I101) | **Script-verified cell** (`verify_workbook.py` Section 6) |
| `VAL-ANOM-02` | `WARNING` | Flag December 2025 Stock-Based Compensation (`$334,660.53` in I99) | **Script-verified cell** (`verify_workbook.py` Section 6) |
| `VAL-ANOM-03` | `WARNING` | Flag debit balance in liability account (HSA Liability Row 48 negative) | Inspection report finding (to be tested in Phase 1) |
| `VAL-FMT-01` | `INFO` | Document Unicode en-dash in BS C35, C68 and trailing space in BS C53 | **Script-verified cells** (`verify_workbook.py` Section 6) |

---

## 6. Known Source Anomalies to Preserve and Flag

The pipeline strictly preserves the following workbook characteristics without data mutation:

### 6.1 Script-Verified Source Cells
1. **December 2025 Income Tax Benefit (`IS-ANOM-01`):**
   * Cell `I101` verified: literal value `-1244429.84` (all other months are `0.0`).
   * Cell `I103` verified: Total OpEx turns negative (`-$402,142.09`).
   * Cell `I105` verified: Operating Income turns positive (`+$534,551.41`).
   * *Preservation Rule:* Preserved in source model; validator emits `WARNING`.
2. **December 2025 Stock-Based Compensation (`IS-ANOM-02`):**
   * Cell `I99` verified: literal value `334660.53` (all other months are `0.0`).
   * Matches step-change in Balance Sheet APIC - Stock Options (`C68`). Preserved; validator emits `WARNING`.
3. **January 2025 Values and Formulas:**
   * Cells `T8` (`62312.5`), `T14` (`=SUM(T8:T13)` / `167587.5`), `T24` (`=SUM(T17:T23)` / `36950.54`), `T26` (`=(T14-T24)` / `130636.96`) verified intact.
4. **Unicode Characters & Trailing Whitespace (`FMT-ANOM-01`):**
   * Balance Sheet C35: `'Deferred Tax Asset – NOL'` (Unicode `U+2013` EN DASH verified).
   * Balance Sheet C68: `'Additional Paid-in Capital – Stock Options'` (Unicode `U+2013` EN DASH verified).
   * Balance Sheet C53: `'Credit Card 2 '` (trailing whitespace verified; `len=14`).
   * *Preservation Rule:* Both `original_label` (exact) and `normalized_label` (trimmed) are retained.

### 6.2 Inspection Report Anomalies (To be Verified by Phase 1 Test Suite)
1. **All-Zero Detail Rows (`IS-ANOM-03`):**
   * Rows 89–92 (S&M Workers Comp Insurance, S&M Payroll, S&M Payroll Taxes, S&M Payroll benefits) hold `0.0` values across all 18 periods.
   * Model flags them as `is_dormant=True` and retains all monthly zero values.
2. **Debit Balance in HSA Liability (`BS-ANOM-01`):**
   * Row 48 holds negative/zero values across all 18 periods (`-$1,450.00` to `$0.00`). Preserved; validator emits `WARNING`.
3. **Isolated Negative Accounts (`IS-ANOM-04`):**
   * Cells `F9` (`-$1,608.09`), `R22` (`-$1,800.00`), `G23` (`-$3,629.87`), `C31` (`-$1,806.24`), `T87` (`-$98.50`). Preserved as literal values.

---

## 7. Required Ingestion Verification Tests (`tests/test_ingestion.py` & `tests/test_validation.py`)

Ingestion is complete only when an automated pytest suite passes the following tests against the actual workbook:
1. `test_workbook_file_presence_and_immutability()`: Asserts source path exists and remains unchanged.
2. `test_structural_dimensions_and_trailing_empty()`: Asserts 107 rows, 71 rows, and empty trailing columns.
3. `test_period_extraction_and_chronology()`: Verifies 18 normalized periods (`2026-06` to `2025-01`).
4. `test_dual_loading_parity()`: Asserts 144 IS formulas, 180 BS formulas, and 0 missing cached values.
5. `test_row_classification_explicit_map()`: Verifies all 107 IS and 71 BS rows match expected taxonomy and label text.
6. `test_january_2025_period_integrity()`: Verifies Col T (IS) and Col U (BS) data representation and cached results where applicable, without requiring detail rows to contain formulas.
7. `test_blank_vs_zero_representation()`: Asserts distinct representation of blank cells, literal zeros, and formula zeros.
8. `test_dormant_accounts_preserved()`: Asserts rows 89–92 remain in models with all monthly zero values and `is_dormant=True`.
9. `test_source_anomalies_flagged()`: Asserts Dec 2025 tax benefit, SBC, HSA negative, and label formatting produce correct model properties and validation findings.
10. `test_all_18_formula_rows_mathematical_integrity()`: Independently evaluates all 8 IS formula rows and all 10 BS formula rows against component detail accounts with tolerance `< 0.01`.
11. `test_validation_pipeline_blocking()`: Verifies all checks run, findings are collected, and simulated critical failures block downstream execution while preserving the validation report.

---

## 8. Phase 2 Financial Metrics Alignment Specification

To avoid ambiguity in Phase 2 metrics calculations:
* **Operating Expenses Grouping:** Strict adherence to source workbook structure:
  * **Direct OpEx:** Rows 29–46 (18 accounts).
  * **Sales & Marketing Payroll:** Rows 48–58 (11 accounts) rolling into Subtotal row 59.
  * **Marketing:** Rows 61–70 (10 accounts) rolling into Subtotal row 71.
  * **Other OpEx:** Rows 72–102 (31 accounts).
  * *Rule:* In the absence of an explicit chart-of-accounts mapping in the source workbook, the engine will not infer R&D or G&A categories.
