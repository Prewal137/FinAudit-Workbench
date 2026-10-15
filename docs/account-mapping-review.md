# QuickBooks Account Mapping Review

**Purpose**: Align the revenue, COGS, and operating‑expense line items from the financial‑statement workbook `ABC Inc - Financial Statements.xlsx` with the chart of accounts retrieved from the QuickBooks sandbox. This review does **not** create journal entries; balanced entries with appropriate counterpart accounts must still be designed before any import.

---

| Workbook Category | QuickBooks Account (ID & Name) | Mapping Status | Reason & Evidence | Confirmation Required |
|---|---|---|---|---|
| Platform Revenue | *NO MATCH* | NO MATCH | No account name directly references “Platform Revenue”. Closest candidates are generic Income accounts (e.g., Services, Sales of Product Income) but the mapping is uncertain. | Yes |
| Accrued Revenue | *NO MATCH* | AMBIGUOUS | Could be recorded against **Accounts Receivable (A/R)** (ID 84) but the workbook treats it as a separate revenue line. | Yes |
| Deferred Revenue | *NO MATCH* | NO MATCH | No liability account for deferred revenue is present in the chart. | Yes |
| Cost of Goods Sold | ID 80 – Cost of Goods Sold | PROPOSED | Exact name match (type *Cost of Goods Sold*). | No |
| Accounting & Tax | ID 69 – Accounting | PROPOSED | Direct name match for accounting‑related expenses. | No |
| Advertising | ID 7 – Advertising | PROPOSED | Exact name match for advertising expense. | No |
| Depreciation | ID 40 – Depreciation *(Other Expense)* | AMBIGUOUS | Two accounts named “Depreciation” exist (ID 40 – Other Expense, ID 39 – Fixed Asset). Need to decide if this is expense or accumulated depreciation. | Yes |
| Health Insurance | ID 11 – Insurance | PROPOSED | “Insurance” covers health insurance expense in the chart. | No |
| Insurance (general) | ID 11 – Insurance | PROPOSED | Same as above; the generic insurance account can be used. | No |
| Legal & Professional Fees | ID 12 – Legal & Professional Fees | PROPOSED | Exact match for legal fees. | No |
| Marketing - Payroll | *NO MATCH* | NO MATCH | No payroll‑specific expense account in the chart. | Yes |
| Marketing - Payroll benefits | *NO MATCH* | NO MATCH | Same as above. | Yes |
| Marketing - Payroll Taxes | *NO MATCH* | NO MATCH | No dedicated tax‑payroll expense account. | Yes |
| Marketing - Workers Comp Insurance | ID 57 – Workers Compensation | PROPOSED | Workers Compensation expense covers workers‑comp insurance. | No |
| Sales - Payroll Taxes | *NO MATCH* | NO MATCH | No payroll tax expense account. | Yes |
| Sales - Workers Comp Insurance | ID 57 – Workers Compensation | PROPOSED | Same reasoning as Marketing workers‑comp. | No |
| Marketing (general) | ID 7 – Advertising | AMBIGUOUS | “Marketing” could map to Advertising, but the scope differs. | Yes |
| Marketing/Advertising | ID 7 – Advertising | PROPOSED | Direct match to Advertising expense. | No |
| Marketing/Advertising: Ad Spend | ID 7 – Advertising | PROPOSED | Sub‑category of Advertising; can be tracked via class/sub‑account if needed. | No |
| Marketing/Advertising: Print & Digital | ID 7 – Advertising | PROPOSED | Same as above. | No |
| Marketing/Advertising: 3rd Party Content Syndication | ID 7 – Advertising | PROPOSED | Same as above. | No |
| Marketing/Advertising: Content | ID 7 – Advertising | PROPOSED | Same as above. | No |
| Marketing/Advertising: Membership Dues/Subscriptions | ID 15 – Office Expenses | AMBIGUOUS | Could be office/general expenses; no dedicated “Membership” account. | Yes |
| Marketing/Advertising: Miscellaneous | ID 7 – Advertising | PROPOSED | Broad category fits under Advertising expense. | No |
| Marketing/Advertising: Website | ID 7 – Advertising | PROPOSED | Website costs are marketing‑related. | No |
| Marketing/Advertising: Partner Marketing | ID 7 – Advertising | PROPOSED | Partner marketing falls under Advertising. | No |
| Office Expenses | ID 15 – Office Expenses | PROPOSED | Exact match. | No |
| Operating Payroll | *NO MATCH* | NO MATCH | No payroll expense account present. | Yes |
| Operations - Workers Comp Insurance | ID 57 – Workers Compensation | PROPOSED | Same generic workers‑comp account. | No |
| Operations Payroll Taxes | *NO MATCH* | NO MATCH | No dedicated account. | Yes |
| Product - Workers Comp Insurance | ID 57 – Workers Compensation | PROPOSED | Same as above. | No |
| Product Payroll Taxes | *NO MATCH* | NO MATCH | No dedicated account. | Yes |
| Recruiting Expense | *NO MATCH* | NO MATCH | No recruiting‑specific expense account. | Yes |
| Rent | ID 17 – Rent or Lease | PROPOSED | Exact match for rent expense. | No |
| Sales & Marketing - Contractor | *NO MATCH* | NO MATCH | No contractor expense account. | Yes |
| Sales & Marketing - Workers Comp Insurance | ID 57 – Workers Compensation | PROPOSED | Same generic account. | No |
| Sales & Marketing Payroll | *NO MATCH* | NO MATCH | No payroll expense account. | Yes |
| Sales & Marketing Payroll Taxes | *NO MATCH* | NO MATCH | No dedicated account. | Yes |
| Sales and Marketing - Payroll benefits | *NO MATCH* | NO MATCH | No benefit expense account. | Yes |
| Workers Compensation Insurance | ID 57 – Workers Compensation | PROPOSED | Direct match. | No |
| Stock‑Based Compensation Expense | *NO MATCH* | NO MATCH | No stock‑based compensation expense account. | Yes |
| Sales & Marketing - Travel, Meals & Entertainment | ID 23 – Travel Meals | PROPOSED | Travel Meals account covers travel‑related meals. | No |
| Income Tax Benefit | *NO MATCH* | NO MATCH | No tax‑benefit account in chart. | Yes |
| Operating Income | *NO MATCH* | NO MATCH | This is a subtotal, not a leaf expense. | Yes |
| Current Assets | *NO MATCH* | NO MATCH | Group heading, not an expense. | Yes |
| Prepaid Expense | ID 3 – Prepaid Expenses | PROPOSED | Exact match for prepaid expense asset. | No |
| Less Accumulated Depreciation on Computer Equipment | ID 39 – Depreciation (Fixed Asset) | PROPOSED | Accumulated depreciation matches Fixed Asset depreciation entry. | No |
| Less Accumulated Depreciation on Other Equipment | ID 39 – Depreciation (Fixed Asset) | PROPOSED | Same as above for other equipment. | No |
| Deferred Tax Asset – NOL | *NO MATCH* | NO MATCH | No deferred tax asset account present. | Yes |
| Current Liabilities | *NO MATCH* | NO MATCH | Group heading. | Yes |
| Accrual Expense | *NO MATCH* | NO MATCH | No generic accrual expense account. | Yes |
| Current Year Earnings | *NO MATCH* | NO MATCH | Not an expense line. | Yes |

**Notes**

- The mapping table purposefully avoids assuming equivalence based solely on name similarity. Where uncertainty exists, the status is marked **AMBIGUOUS** and a confirmation is required.
- Several workbook categories represent payroll, taxes, or contractor costs that lack direct counterparts in the current QuickBooks chart; these are marked **NO MATCH** and will need new accounts or alternative handling.
- Even for **PROPOSED** mappings, creating journal entries requires a corresponding **counterpart account** (e.g., a debit to an expense and a credit to a revenue or liability account). This review does not address that balancing requirement.
- Before importing any mappings, the finance team should review and approve each **YES** confirmation entry, possibly creating additional sub‑accounts or adjusting the chart of accounts to accommodate missing categories.
