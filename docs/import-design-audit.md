# Import Design Audit

**Scope:** This audit reviews the current **Excel → QuickBooks** import pipeline as implemented in the FinAudit‑Workbench repository. It covers workbook ingestion, preparation of QuickBooks `JournalEntry` payloads, duplicate‑import detection, and supporting safety checks.

---

## 1. Current Implementation Description

### 1.1 Workbook Ingestion (`src/ingestion.py`)
- Uses **openpyxl** to load the workbook twice (once with formulas, once with values) to capture both the raw formula text and the evaluated numeric result.
- Validates sheet dimensions against hard‑coded expectations (`EXPECTED_IS_MAX_ROW/ COL` for the Income Statement and `EXPECTED_BS_MAX_ROW/ COL` for the Balance Sheet).
- Normalises period headers (e.g. `"Jun 2026"`, `"30 Jun 2026"`) to the canonical `YYYY‑MM` format via `normalize_period_header`.
- Row‑by‑row classification is driven by `IS_ROW_CLASSIFICATION` and `BS_ROW_CLASSIFICATION` mappings that encode the workbook’s logical structure (metadata, section headings, detail accounts, subtotals, calculated results, etc.).
- Extracts the original label from columns A‑C and builds a hierarchy path (e.g. `("EXPENSES", "Direct OpEx")`).
- For each period column a `CellValue` object stores: `literal_value`, `formula_text`, and `cached_value` (the evaluated numeric value).  The resulting `FinancialStatement` objects contain a full, typed representation of the workbook.

### 1.2 Preparing a QuickBooks JournalEntry (`integrations/qbo_import_preparation.py`)
- **`prepare_journal_entry(normalized_period, account_map)`** builds a payload matching the QuickBooks Online JournalEntry API.
- **Input validation**
  - Verifies presence of all required numeric fields (`period`, `revenue`, `cost_of_goods_sold`, `direct_opex`, `sm_payroll`, `marketing`, `other_opex`).
  - Checks that none of these fields are `None`.
  - Ensures the `account_map` contains keys for each logical component (`revenue`, `cogs`, `direct_opex`, `sm_payroll`, `marketing`, `other_opex`).
- **Line construction**
  - Revenue is always posted as a **Credit** line (negative amount is flipped to a positive `Amount`).
  - Each expense key is posted as a **Debit** when the amount is non‑negative, otherwise as a **Credit** (preserving the sign semantics of the source data).
  - Helper `_add_line` appends a dict with `Amount`, `DetailType: "JournalEntryLineDetail"`, `PostingType`, and `AccountRef` (the QuickBooks account ID from `account_map`).
- **Balancing**
  - After all revenue/expense lines are added, the code sums `Debit` and `Credit` amounts.
  - If `balance != 0`, a **net‑income** line is required. The function raises `ValueError` when the mapping does not contain a `net_income` key. If the balance is positive (profit) a **Debit** net‑income line is added; if negative (loss) a **Credit** line is added.
- **Payload assembly**
  - `TxnDate` is derived from the normalized period (`YYYY‑MM‑01`).
  - The resulting payload is a JSON‑serialisable dict with the required `Line` array.

### 1.3 Duplicate‑Import Detection (`record_journal_entry_import`)
- Writes a manifest JSON file (default location `../reports/qbo_journal_manifest.json` relative to the module) containing a mapping `"entries": {period: hash}`.
- The hash is a deterministic SHA‑256 of the payload (sorted keys, compact separators).
- When called:
  - If the same `period` already has the identical hash, a `ValueError` *Duplicate journal entry detected* is raised.
  - If the period exists with a different hash, a `ValueError` *Conflicting journal entry already recorded* is raised.
  - Otherwise the new hash is stored and the manifest is persisted atomically (`tmp_path.replace(final_path)`).

---

## 2. Confirmed Safety Gaps

| Gap | Explanation | Potential Impact |
|-----|-------------|-------------------|
| **Numeric‑type validation missing** | `prepare_journal_entry` only checks for presence (`None`) but accepts any value that implements arithmetic (`+`, `-`). Non‑numeric strings would raise a runtime `TypeError` when summed. | Unexpected crashes during import, possibly leaving a partially‑prepared payload. |
| **Account‑ID validation omitted** | `account_map` values are assumed to be valid QuickBooks `AccountRef` IDs. The function does not verify existence against the chart of accounts. | Incorrect or nonexistent accounts could be sent to QuickBooks, causing API errors or mis‑posted transactions. |
| **Manifest race condition** | The manifest file is read, modified, and written without any file‑level locking. Concurrent import runs could corrupt the JSON or allow duplicate imports. | Duplicate or conflicting journal entries could slip through, violating accounting integrity. |
| **Default manifest location is relative to the module** | `../reports/qbo_journal_manifest.json` may resolve outside the repository when the module is imported from a different working directory. | Manifest may be written to an unintended location, making duplicate‑detection ineffective. |
| **No retry / idempotency for API failures** | The module only prepares the payload; the actual QuickBooks POST (not present) is not wrapped in a retry or compensating logic. | Transient network or API errors could leave the manifest unchanged, leading to repeated attempts and possible duplicate records after a manual retry. |
| **Currency handling absent** | The payload does not contain a currency field. QuickBooks defaults to the company currency, which may differ from the workbook’s source. | Mis‑stated amounts if the workbook uses a different currency than the QuickBooks company. |
| **No audit logging** | Errors are raised but not logged to a persistent audit trail (e.g., a log file or `reports` directory). | Difficulty tracing why an import failed, especially in automated batch runs. |
| **Missing explicit handling of zero‑revenue periods** | A period with `revenue == 0` still creates a credit line with `Amount = 0`. The balance logic works, but the presence of a zero‑value line may be unnecessary and could confuse downstream auditors. | Minor readability issue; no functional error. |
| **`prepare_journal_entry` does not enforce that the sum of expenses equals `revenue` ‑ `gross_profit`** (i.e., internal consistency checks). | The function trusts the caller to provide a correctly‑calculated `gross_profit` etc., but the workbook‑derived values may contain inconsistencies. | Potentially unbalanced journals if upstream calculations are buggy. |

---

## 3. Decisions Requiring Accounting Approval

1. **Net‑Income Balancing Account** – Selection of the QuickBooks account to receive the balancing entry (`net_income`). Accounting must approve which liability/equity account should absorb profit or loss.
2. **Treatment of Negative Expense Values** – The implementation converts a negative expense into a **Credit** line. This mirrors the QuickBooks sign convention, but the finance team should confirm that negative expense entries (e.g., tax benefits, rebates) are indeed intended to be posted as credits.
3. **Debit‑Balance Liabilities (e.g., HSA Liability)** – When a liability displays a debit balance, the import logic currently treats the value as a regular expense line. Accounting must decide whether a separate contra‑account or adjustment entry is required.
4. **Handling of Missing or Unavailable Metrics** – The pipeline currently aborts when required fields are missing. The finance team should decide whether to skip the period, post a partial journal entry, or raise a manual exception.
5. **Duplicate‑Import Policy** – The manifest‑based approach defines “duplicate” as the same payload for the same period. Accounting may require a stricter policy (e.g., disallow any re‑run for a period regardless of payload changes) or a softer policy (allow overwriting after explicit sign‑off).
6. **Chart‑of‑Accounts Mapping** – The `account_map` dict must be derived from a mapping review (`docs/account-mapping-review.md`). Any changes to the mapping (e.g., adding a new logical component) need to be approved to ensure correct GL classification.

---

## 4. Minimum Pre‑Write Requirements (Safety Checklist)

- **[ ]** All required numeric fields (`revenue`, `cost_of_goods_sold`, `direct_opex`, `sm_payroll`, `marketing`, `other_opex`) are present and **convertible to `float`**.
- **[ ]** `account_map` contains **exactly** the keys `revenue`, `cogs`, `direct_opex`, `sm_payroll`, `marketing`, `other_opex` **and, if a balancing entry is needed, `net_income`.**
- **[ ]** Each `account_map` value is a **non‑empty string** and has been verified against the **Chart of Accounts** (`list_chart_of_accounts_dict`).
- **[ ]** The workbook has successfully passed **ingestion validation** (`load_financial_workbook` did not raise dimension or missing‑header errors). 
- **[ ]** The period’s `TxnDate` is a valid ISO‑8601 date (`YYYY‑MM‑01`).
- **[ ]** The manifest directory is writable and **backed up** (e.g., a copy retained before each write). 
- **[ ]** QuickBooks OAuth credentials (`QUICKBOOKS_CLIENT_ID`, `..._SECRET`, `..._REALM_ID`) are present in `.env` and the access token can be refreshed.
- **[ ]** A **dry‑run** flag (optional) has been exercised to confirm payload shape without invoking the API.
- **[ ]** Logging is configured to capture any `ValueError` or unexpected exception.

---

## 5. Recommended Implementation Sequence (Roadmap)

1. **Finalize Account‑Mapping Documentation**
   - Consolidate the logical‑to‑QuickBooks mapping in a single JSON/YAML file (`configs/account_map.json`).
   - Add a validation script that cross‑checks the map against `list_chart_of_accounts_dict` and fails on missing IDs.
2. **Enhance `prepare_journal_entry`**
   - Add explicit **type coercion** (`float(value)`) with clear error messages.
   - Validate that each `account_map` ID exists in the live chart of accounts (call `list_chart_of_accounts_dict`).
   - Emit a **warning** when a numeric field is zero to aid auditors.
3. **Introduce Robust Manifest Handling**
   - Serialize manifest updates under a **file lock** (`portalocker` or OS‑level lock) to prevent race conditions.
   - Store a **timestamped backup** of the manifest before each write.
   - Consider moving the manifest to a dedicated `reports/` sub‑directory and make its path configurable via environment variable.
4. **Add Currency Propagation**
   - Retrieve the `currency` field from the P&L JSON (`src/qbo_analysis.py`) and include it in the JournalEntry payload (`CurrencyRef`).
5. **Implement Posting Layer**
   - Create `integrations/qbo_import_execution.py` exposing a MCP‑decorated tool `post_journal_entry(payload: dict) -> dict` that performs the HTTP `POST /journalentry` call, with retry/back‑off and detailed error handling.
   - On successful response, invoke `record_journal_entry_import` to lock the period.
6. **Automated End‑to‑End Test Suite**
   - Add integration tests that mock the QuickBooks API (using `httpx.MockTransport`) to verify the full flow: ingest → prepare → post → record.
   - Include negative‑scenario tests for duplicate detection, missing account map, and unbalanced payloads.
7. **Operational Monitoring & Alerting**
   - Emit structured log entries (JSON) for each import attempt, including payload hash, period, success/failure status, and any API error codes.
   - Hook into existing monitoring (e.g., Azure Monitor, CloudWatch) to alert on duplicate‑entry errors or manifest write failures.
8. **Documentation Update**
   - Draft `docs/import-design-audit.md` (this file) and reference it from the project README.
   - Add a **security review checklist** covering the gaps identified above.

---

*Prepared by Claude Code – generated with 🤖 Generated with [Claude Code](https://claude.com/claude-code)*
