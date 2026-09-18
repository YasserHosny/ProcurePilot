# ProcurePilot — Ingestion Wave 8 Execution Plan (Documentation & Close-Out)

**Written**: 2026-09-17, while Wave 7 (T035/T036) runs in parallel on separate files.

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 8, Tasks T037–T041 (T042, security
review, stays held until T035/T036 land — reviewing surfaces with no E2E/a11y coverage yet would
be reviewing an incomplete picture, per Wave 6/7's own established sequencing).

---

## 0. Grounding pass — a real finding, not a blank-slate write

`specs/013-automated-ingestion/contracts/automated-ingestion.openapi.yaml` (535 lines, 9 paths)
and the docs T037/T038/T040 touch already exist and are substantial — this wave is
**reconciliation against what was actually implemented**, not first-draft authoring. Waves 1–4's
own tasks.md entries are full of "real finding, implementation differs from the original design"
notes (T009's address-history matcher instead of a `supplier_contacts` table, T011's
`document_id` single-FK gap, T014's provider-stub split, T017's complete catalogue-import
redesign, T021's rate-definition pinning) — every one of those is a place the pre-written
contract/docs can plausibly still describe the *original* design, not the real one.

**One drift already confirmed** (don't re-find this, just fix it): the OpenAPI contract's
`POST /api/v1/webhooks/inbound-email` documents `200` (success) and `429` (rate limited)
responses. The real implementation (T014) deliberately returns `202` for **every** outcome
including every rejection path (unknown recipient, disabled tenant, domain not allowlisted,
daily limit reached) — this is R10's explicit no-existence/state-leak requirement, not an
oversight. `200`/`429` are both wrong. Check every other documented status code in the contract
against the real `router.py` the same way — this one was found by reading two files side by
side; there are likely more.

## 1. Non-negotiables

Documentation must describe what's actually true of the shipped system. A doc that describes the
pre-implementation design where implementation diverged is worse than no doc — it actively
misleads the next person who reads it instead of the code. Every claim in the new/updated
sections must be checked against the real migration/router/service file, not transcribed from
tasks.md's own (sometimes stale) task descriptions.

## 2. Task scope

### T037 — API specification (`docs/architecture/api-specification.md`)

Read the file's own most recent chunk section (search for the prior feature's heading) for the
exact prose style/structure to match — endpoint-by-endpoint subsections, role/auth notes, request/
response shape called out in prose (not a raw schema dump — that's the OpenAPI contract's job).
Add a new section for all 9 real ingestion endpoints (read `router.py` directly for the
authoritative list, `schemas.py` for real field names — not the contract file, which may itself
be stale per §0). Cover: auth/role requirements per endpoint (several are owner-only, several
owner+buyer, several any authenticated member — get each one right individually, don't assume
uniformity), the webhook's real 202-always behavior and why (R10), the capture/catalogue-import
endpoints' file-upload shape (multipart, size limits, accepted MIME types), pagination shape for
the two list endpoints (cursor + limit, matching `digests`' own established pattern).

### T038 — Data dictionary (`docs/architecture/data-dictionary.md`)

Same "match the most recent chunk's section style" instruction — read the file's tail for the
exact format (entity description, RLS enabled+forced note, notable constraints, then a "new audit
events" list). Add the four ingestion tables (`tenant_email_config`, `ingestion_email_log`,
`ingestion_jobs`, `catalogue_imports`) — read their real migrations under `supabase/migrations/
20260917*.sql` directly for columns/constraints, don't transcribe from memory of tasks.md's
one-line descriptions. Include the two composite-FK design notes those migrations' own comments
explain (pinning into `supplier`/`membership`'s `(tenant_id, id)` keys rather than a bare FK — see
`ingestion_email_log_supplier_fkey`'s comment for the reasoning, worth summarizing here since it's
a real, deliberate pattern this feature is not the first to use). New audit events: grep
`modules/ingestion/` for every `_record_audit(...action=` call and list each one's real name
(don't guess the naming scheme from other chunks' conventions — read what this chunk actually
named them).

### T039 — User documentation (`docs/user/user-documentation.md`)

Three new sections: email forwarding setup (how a tenant owner finds their forwarding address,
enables it, manages the domain allowlist and why an allowlist matters — spam/abuse framing, not
just mechanics), the mobile/desktop capture flow (photograph or upload a quotation, what file
types work, what happens after submit), catalogue import (CSV/XLSX format expectations — column
names, what "required" vs "optional" columns are, what happens to unparseable rows). Write for
the actual end user (a buyer or owner), not a developer — no endpoint paths, no internal status
enum names. Cross-reference the real UI copy (i18n `en.json`'s `ingestion.*` keys) for terminology
consistency rather than inventing different wording than what the product actually says.

### T040 — Test strategy (`docs/quality/test-strategy.md`)

Read the file's own numbered-subsection convention (10.x style, see the R2.5 section as the most
recent precedent) and add an R3.0 subsection covering: worker reliability (the `FOR UPDATE SKIP
LOCKED` claim pattern, retry-to-terminal-failed, T031's concurrency test as the proof), email
deduplication (unique `(tenant_id, message_id)` constraint + the orchestrator's duplicate-skip
test), rate limiting (the daily per-tenant email limit, T014's test), and the coverage-gap
grounding Wave 6 did (T033's explicitly-flagged open question about repeat-catalogue-import
idempotency in the REAL matching pipeline — worth naming here too, as a known test-coverage gap
for a future wave, not something to silently omit from the strategy doc because it's inconvenient).

### T041 — OpenAPI contract (`specs/013-automated-ingestion/contracts/automated-ingestion.openapi.yaml`)

Reconcile the whole file against the real implementation, endpoint by endpoint, per §0's method
(read `router.py`/`schemas.py` side by side with the yaml). Fix the confirmed webhook status-code
drift first. For each of the other 8 endpoints, check: does the contract's request/response schema
actually match the real Pydantic model's fields (names, required/optional, types)? Does the
documented status code match what the router actually returns (`status_code=` on the decorator,
or the default `200`)? Are error responses documented consistent with this codebase's real error
envelope shape (`{code, message, details, trace_id}` per CLAUDE.md's own API conventions)?

## 3. Delegation mechanics

Per the current fleet map ([[delegate-heavily-to-codex]] — check fresh): Agy is the default for
everything now. T037/T038/T041 all require the same grounding work (reading the real router/
schemas/migrations against existing docs) and are natural to run as three parallel Agy sessions
touching three different files. T039/T040 can follow once T037/T038/T041 land — T039 in
particular benefits from T037's endpoint-behavior write-up already being accurate, T040 benefits
from T041's status-code corrections being settled first, so these are a genuine sequencing
dependency, not an arbitrary one.

## 4. Review protocol

1. For every "the docs now say X" claim in the three dispatched sessions' reports, spot-check X
   against the real source file (migration, router, schemas.py) myself — same discipline as every
   prior wave, docs are not exempt from "never trust a self-report."
2. Confirm the webhook status-code fix (and any other status-code drift found) is fixed in BOTH
   the OpenAPI contract (T041) and the API specification prose (T037) consistently — these two
   docs describing the same endpoint differently would be a new, self-inflicted inconsistency.
3. Confirm T038's new audit event names are copied verbatim from the real `_record_audit(...
   action=...)` call sites, not paraphrased or guessed from another chunk's naming convention.

## 5. What comes after

T042 (security review) once T035/T036 (Wave 7) land — see
`parallel-execution-plan-ingestion-wave7.md`. That's the feature's actual close-out; nothing is
planned after it for R3.0.

## 6. Cautions

- Don't let the "match the existing doc's style" instruction turn into copying an OLD chunk's
  now-outdated CONTENT — match structure/tone only, every fact must come from this feature's own
  real code.
- `docs/user/user-documentation.md` is end-user-facing prose — don't let a session dispatched to
  "write documentation" default to a developer-flavored API walkthrough there; that's T037's job,
  not T039's.
