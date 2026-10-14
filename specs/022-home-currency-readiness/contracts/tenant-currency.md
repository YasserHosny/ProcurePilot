# Contract: tenant home currency

`PATCH /api/v1/tenant` (owner only, unchanged path/auth)
- Request: `{ "currency": "EGP" }` — MUST be in `supported_currency`; otherwise 422 with the standard error envelope.
- Response: `Tenant` (includes `currency`). Non-owner: 403 (existing). Cross-tenant: not applicable (tenant from JWT).
- Side effect: `audit_event` with old and new currency.

`GET /api/v1/tenant` — unchanged; `currency` is the home currency.
