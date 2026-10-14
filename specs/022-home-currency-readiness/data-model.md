# Data Model: Home Currency Readiness

**No schema change.**

| Entity | Change |
|---|---|
| `tenant.currency` | Existing column; it *is* the home currency. Add: PATCH validates against `supported_currency`; PATCH writes an `audit_event` (action `tenant.currency_changed`, before/after). |
| `audit_event` | New event type only (append-only, unchanged). |
| Extracted `currency` field | Existing field-extraction record. When the document does not evidence a currency the `currency` field is **absent** (money values carry `currency: null`, so no amount is stored on `quotation`/`quotation_line`), and a `suggested_currency` field (tenant home currency, confidence 0) is stored for the reviewer. Review reason `currency_unresolved` (new `review_task_reason` enum value, migration `20261014000002`). |
| Stored amounts/currencies | Never rewritten (FR-006). |
