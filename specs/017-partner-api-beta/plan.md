# R3.4 Partner API Beta Plan

## Architecture

The beta adds a small `partner` module containing a router and read facade. It delegates to the
existing order and catalogue services, preserving their tenant-scoped PostgREST queries, domain
models, and error behavior. Authentication remains the verified Supabase JWT path already used by
the application; no alternate API-key tenancy mechanism is introduced.

## Components

- `partner/router.py`: three GET routes under `/api/v1/partner`.
- `partner/service.py`: provider-neutral read facade with no mutation methods.
- `partner/schemas.py`: explicit exports of existing order and catalogue projections.
- `main.py`: router registration.
- Unit and contract tests: delegation behavior and route shape.

## Constitution Check

- Tenant isolation: delegated services use tenant-scoped database access and existing RLS.
- Verified tenancy: routes require `bearer_token` and `current_member`; no tenant parameter is
  accepted.
- Evidence and money: existing order projections retain lifecycle evidence and currencies.
- Human authority: the beta is read-only and cannot execute purchasing mutations.
- Secrets: no new credential material is stored or committed.
