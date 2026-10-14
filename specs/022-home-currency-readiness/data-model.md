# Data Model: Home Currency Readiness

**No schema change.**

| Entity | Change |
|---|---|
| `tenant.currency` | Existing column; it *is* the home currency. Add: PATCH validates against `supported_currency`; PATCH writes an `audit_event` (action `tenant.currency_changed`, before/after). |
| `audit_event` | New event type only (append-only, unchanged). |
| Extracted `currency` field | Existing field-extraction record; defaulted values carry low confidence + reason `currency_fallback` so review surfaces them. Cleared when a reviewer confirms/edits. |
| Stored amounts/currencies | Never rewritten (FR-006). |
