"""Local preparation layer for QuickBooks JournalEntry payloads.

This module defines a pure‑Python function that converts a *normalized* financial
period (derived from the Excel Income Statement) into a JSON payload matching the
QuickBooks JournalEntry API contract.  No network calls are performed – the
function only validates input, builds the payload, and optionally records a hash
in a local manifest to detect duplicate imports.

If the required account mappings are missing, or the payload cannot be balanced
without an explicit ``net_income`` line, the function raises ``ValueError``.
"""

from __future__ import annotations

import json
import hashlib
import os
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Helper utilities for deterministic hashing and manifest handling
# ---------------------------------------------------------------------------

def _hash_entry(entry: Dict[str, Any]) -> str:
    """Return a SHA‑256 hash of a JSON‑serialisable entry.

    The entry is serialized with sorted keys and ``separators`` to ensure a
    stable representation irrespective of whitespace ordering.
    """
    serialized = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_manifest(manifest_path: str) -> Dict[str, Any]:
    """Load the JSON manifest containing previously generated entry hashes.

    Returns ``{"hashes": []}`` if the file does not exist or is empty.
    """
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "hashes" in data:
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"hashes": []}


def _save_manifest(manifest_path: str, manifest: Dict[str, Any]) -> None:
    """Write the manifest back to disk, creating parent directories as needed."""
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Core preparation function
# ---------------------------------------------------------------------------

def prepare_journal_entry(
    normalized_period: Dict[str, Any],
    account_map: Dict[str, str],
) -> Dict[str, Any]:
    """Prepare a QuickBooks ``JournalEntry`` payload for a single period.

    Parameters
    ----------
    normalized_period:
        Mapping containing at least the following keys (all numeric values must
        be provided, ``None`` is not accepted):

        - ``period`` (``YYYY‑MM`` string – used for the ``TxnDate`` field)
        - ``revenue``
        - ``cost_of_goods_sold``
        - ``direct_opex``
        - ``sm_payroll``
        - ``marketing``
        - ``other_opex``

        Optional ``net_income`` may be supplied but is **only** used when a
        balancing line is required and the caller explicitly provides an account
        mapping for ``net_income``.

    account_map:
        Mapping from logical component names to QuickBooks ``AccountRef`` IDs.
        Expected keys are ``revenue``, ``cogs``, ``direct_opex``, ``sm_payroll``,
        ``marketing``, ``other_opex`` and optionally ``net_income`` (required only
        when the revenue‑expenses difference is non‑zero).


    Returns
    -------
    dict
        A JSON‑serialisable dictionary matching the QuickBooks JournalEntry API
        payload structure (see note below).

    Raises
    ------
    ValueError
        If required fields are missing, any field is ``None``, a required account
        mapping is absent, or the entry would be unbalanced without a ``net_income``
        mapping.
    """
    # -------------------------------------------------------------------
    # Input validation
    # -------------------------------------------------------------------
    required_fields = [
        "period",
        "revenue",
        "cost_of_goods_sold",
        "direct_opex",
        "sm_payroll",
        "marketing",
        "other_opex",
    ]
    for field in required_fields:
        if field not in normalized_period:
            raise ValueError(f"Missing required field '{field}' in normalized period")
        if normalized_period[field] is None:
            raise ValueError(f"Field '{field}' cannot be None for period {normalized_period.get('period')}")

    # -------------------------------------------------------------------
    # Account mapping validation
    # -------------------------------------------------------------------
    required_accounts = [
        "revenue",
        "cogs",
        "direct_opex",
        "sm_payroll",
        "marketing",
        "other_opex",
    ]
    for acct in required_accounts:
        if acct not in account_map:
            raise ValueError(f"Missing account mapping for '{acct}'")

    # -------------------------------------------------------------------
    # Build journal lines – amounts are always positive; direction is encoded via
    # the ``PostingType`` field as required by the QuickBooks API.
    # -------------------------------------------------------------------
    def _add_line(amount: float, posting_type: str, acct_key: str, lines_acc: List[Dict[str, Any]]):
        # QuickBooks expects the amount as a number; sign is implied by PostingType.
        lines_acc.append(
            {
                "Amount": round(abs(amount), 2),
                "DetailType": "JournalEntryLineDetail",
                "PostingType": posting_type,
                "AccountRef": {"value": str(account_map[acct_key])},
            }
        )

    lines: List[Dict[str, Any]] = []
    # Revenue is a credit (negative posting relative to the accounting equation).
    _add_line(-normalized_period["revenue"], "Credit", "revenue", lines)
    # Expenses: handle sign – positive amounts are debits, negative amounts are credits.
    expense_mapping = {
        "cost_of_goods_sold": "cogs",
        "direct_opex": "direct_opex",
        "sm_payroll": "sm_payroll",
        "marketing": "marketing",
        "other_opex": "other_opex",
    }
    for period_key, acct_key in expense_mapping.items():
        amount = normalized_period[period_key]
        if amount >= 0:
            _add_line(amount, "Debit", acct_key, lines)
        else:
            _add_line(-amount, "Credit", acct_key, lines)
    # _add_line(normalized_period["cost_of_goods_sold"], "Debit", "cogs", lines)
    # _add_line(normalized_period["direct_opex"], "Debit", "direct_opex", lines)
    # _add_line(normalized_period["sm_payroll"], "Debit", "sm_payroll", lines)
    # _add_line(normalized_period["marketing"], "Debit", "marketing", lines)
    # _add_line(normalized_period["other_opex"], "Debit", "other_opex", lines)

    # -------------------------------------------------------------------
    # Balancing – if total debits != total credits we need a net‑income line.
    # -------------------------------------------------------------------
        # Compute totals from constructed lines to determine any balancing requirement.
        total_debits = sum(line["Amount"] for line in lines if line["PostingType"] == "Debit")
        total_credits = sum(line["Amount"] for line in lines if line["PostingType"] == "Credit")
        balance = round(total_credits - total_debits, 2)
    # total_credits = normalized_period["revenue"]
    # balance = round(total_credits - total_debits, 2)
    if balance != 0:
        # A balancing entry is required. The caller must provide a mapping.
            if "net_income" not in account_map:
                raise ValueError(
                    "Balancing entry required but no 'net_income' account mapping provided"
                )
            if balance > 0:
                # Positive balance (profit): add a Debit net_income line to offset
                _add_line(balance, "Debit", "net_income", lines)
            else:
                # Negative balance (loss): add a Credit net_income line to offset
                _add_line(abs(balance), "Credit", "net_income", lines)

    # -------------------------------------------------------------------
    # Assemble payload – QuickBooks expects a ``TxnDate`` (ISO‑8601 date).  We
    # use the first day of the period.
    # -------------------------------------------------------------------
    payload: Dict[str, Any] = {
        "TxnDate": f"{normalized_period['period']}-01",
        "Line": lines,
        # Additional optional fields (e.g., "domain", "sparse") are omitted
        # because they are not required for the local preparation step.
    }

    # -------------------------------------------------------------------
    # The preparation step does NOT record the import. Use `record_journal_entry_import`
    # to store a hash of the successful payload after the QuickBooks write succeeds.

    return payload

# ---------------------------------------------------------------------------
# NOTE – QuickBooks JournalEntry API payload structure
# ---------------------------------------------------------------------------
# The exact field names and supported ``AccountRef`` formats are defined by the
# QuickBooks Online API specification.  The repository does not contain the
# official reference, so the precise contract is marked as NOT VERIFIED.
# The payload produced above follows the commonly‑documented shape:
#
# {
#   "TxnDate": "YYYY‑MM‑DD",
#   "Line": [
#     {
#       "Amount": <number>,
#       "DetailType": "JournalEntryLineDetail",
#       "PostingType": "Credit" | "Debit",
#       "AccountRef": {"value": "<account‑id>"}
#     },
#     ...
#   ]
# }
#
# If the official API differs, this implementation would need adjustment.


def record_journal_entry_import(
    payload: Dict[str, Any],
    period: str,
    manifest_path: str | None = None,
) -> None:
    """Record a successful QuickBooks import in the local manifest.

    This function should be called *after* the caller receives a confirmed
    successful response from the QuickBooks ``JournalEntry`` write endpoint.
    It stores a deterministic hash of the payload together with the period
    identifier. If the same period is recorded again, a ``ValueError`` is raised
    to signal a duplicate import. If a different payload is recorded for the
    same period, a ``ValueError`` is raised to indicate a conflict.

    Parameters
    ----------
    payload:
        The JSON‑serialisable payload that was sent to QuickBooks.
    period:
        The period identifier (e.g., "2026-01") used as a unique key.
    manifest_path:
        Optional path to the manifest file. If omitted the default location is
        ``../reports/qbo_journal_manifest.json`` relative to this module.
    """
    if manifest_path is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        manifest_path = os.path.join(base_dir, "reports", "qbo_journal_manifest.json")
    manifest = _load_manifest(manifest_path)
    entries = manifest.setdefault("entries", {})
    entry_hash = _hash_entry(payload)
    if period in entries:
        if entries[period] == entry_hash:
            raise ValueError(f"Duplicate journal entry detected for period {period}")
        raise ValueError(f"Conflicting journal entry already recorded for period {period}")
    entries[period] = entry_hash
    _save_manifest(manifest_path, manifest)

# If the official API differs, this implementation would need adjustment.
