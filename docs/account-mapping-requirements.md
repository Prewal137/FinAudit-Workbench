# QuickBooks Account Mapping – Read‑Only Requirements

This document records the **account‑mapping expectations** for the read‑only journal‑entry preparation step in the FinAudit‑Workbench project. It is deliberately kept separate from the source code so that the mapping can be updated without touching production files.

---

## 1. Which QuickBooks account IDs and account types must be retrieved from the sandbox?

The `prepare_journal_entry` function expects a **dictionary** (`account_map`) that maps logical category names to **QuickBooks `AccountRef` IDs** (the numeric string values used by the QBO API). The required keys are:

| Logical key (used in the code) | QuickBooks account **type** | Typical meaning in the financial model |
|-------------------------------|-----------------------------|----------------------------------------|
| `revenue`                     | **Income** (Revenue)        | Aggregate of all revenue sub‑lines (e.g., Platform Revenue, Partnership Income, etc.) |
| `cogs`                        | **Cost of Goods Sold**      | Direct cost of delivering goods/services – items listed under the “Cost of Goods Sold” section of the Income Statement |
| `direct_opex`                 | **Expense** (Operating)     | Direct operating expenses that are not COGS (e.g., Development Payroll, Hosting, etc.) |
| `sm_payroll`                  | **Expense** (S&M Payroll)  | Sales & Marketing payroll expenses |
| `marketing`                   | **Expense** (Marketing)    | Marketing‑related expenses (advertising, campaigns, etc.) |
| `other_opex`                  | **Expense** (Other Opex)   | All remaining operating expense categories not captured by the above buckets |
| `net_income` *[optional]*      | **Equity** (Retained Earnings / Net Income Summary) | Balancing line that closes the journal entry; required only when the period’s debits ≠ credits |

### Retrieval strategy (read‑only)

1. **List accounts** – `GET /v3/company/{realmId}/account`.
2. **Filter** by `accountType` as shown above.
3. **Select** the account whose `Name` best matches the logical category (e.g., an account named “Revenue – Aggregated” for `revenue`).
4. **Record** the `Id` field (`"value"` in the API) and build the mapping dictionary, e.g.:
   ```python
   account_map = {
       "revenue": "123",  # Income account ID
       "cogs": "124",      # Cost of Goods Sold account ID
       "direct_opex": "125",
       "sm_payroll": "126",
       "marketing": "127",
       "other_opex": "128",
       # "net_income": "129",  # Only needed for balancing periods
   }
   ```

> **Never hard‑code IDs** in source files. Sandbox IDs differ per environment, and hard‑coded values will break when the sandbox is refreshed or when the integration is deployed to a different tenant.

---

## 2. Mapping logical categories to actual account IDs

| Logical category | Example QBO account name | Why the mapping is needed |
|------------------|--------------------------|---------------------------|
| `revenue`        | `Revenue – Aggregated`   | The preparation step posts **one** credit line representing the total of all revenue sub‑lines.
| `cogs`           | `Cost of Goods Sold`     | Required to correctly debit the cost side of the income statement.
| `direct_opex`    | `Operating Expenses – Direct` | Groups expense items that are directly tied to product delivery.
| `sm_payroll`    | `Sales & Marketing Payroll` | Separates payroll that is specifically for sales/marketing activities.
| `marketing`      | `Marketing Expenses`     | Captures advertising, campaign, and related costs.
| `other_opex`     | `Other Operating Expenses` | All remaining expense categories that do not fall under the above buckets.
| `net_income`     | `Retained Earnings` or `Net Income Summary` | The equity account that receives the balancing entry.

The exact QBO **account IDs** (`"value"`) must be fetched from the sandbox using the steps above; the mapping file is **not** generated automatically – a developer or finance stakeholder must create it after confirming the correct accounts exist.

---

## 3. Why IDs must never be guessed or hard‑coded

* **Sandbox volatility** – Each sandbox instance receives a fresh set of UUID‑style IDs. A hard‑coded integer such as `"1"` will only work for the author’s personal sandbox and will break for anyone else.
* **Security & compliance** – Hard‑coding IDs can inadvertently expose internal account structures when the repository is shared publicly.
* **Future migration** – When moving from sandbox to production, the IDs will inevitably change; a dynamic lookup makes the integration portable.

---

## 4. Unresolved accounting decisions (from Phase 5 audit)

| Decision point | Open question | Suggested next step |
|----------------|---------------|--------------------|
| **Net‑income posting direction** – profit should be a **Credit** to equity, loss a **Debit**. The current implementation uses the opposite logic. | Confirm with the finance team whether the balancing line should affect **Retained Earnings** (typical) or a custom “Net Income” equity placeholder. | Update `prepare_journal_entry` to emit the correct posting type based on profit/loss once the accountant signs off. |
| **Expense classification** – some expense rows in the workbook have negative values (e.g., a negative “Direct Opex” entry). The current code treats a negative expense as a **Credit** line. | Determine whether negative expenses should be reported as credits (e.g., refunds) or re‑categorized. | Document the rule in this file once clarified. |
| **Opening‑balance handling** – how to represent the opening equity for the first imported period. | Decide whether to create a one‑time “Opening Balance Equity” journal entry or to rely on existing QBO balances. | Add a separate read‑only utility (outside the scope of this test suite) after accountant approval. |
| **Account aggregation** – whether multiple revenue sub‑categories should be posted to a single revenue account or to distinct QBO revenue accounts. | Depends on reporting requirements (segment reporting vs. high‑level view). | If segmentation is required, extend `account_map` to include multiple revenue keys and adjust `prepare_journal_entry` accordingly. |

---

## 5. Reference URLs (read‑only)

* QuickBooks Online API – JournalEntry payload definition: <https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/journalentry>
* OAuth scopes required for **write** operations (not used here): `com.intuit.quickbooks.accounting` – documented on the same developer portal.
* Example **account list** endpoint: `GET /v3/company/{realmId}/account` (see the API reference above).

---

*This document is part of the read‑only audit artifacts. No code changes are required to reference it.*
