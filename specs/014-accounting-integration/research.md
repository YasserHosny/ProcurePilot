# Phase 0 Research: Accounting Integration & Reconciliation Foundation

## R1: QuickBooks API access — SDK vs. direct HTTP

**Decision**: Direct HTTP via the existing `httpx` dependency, not a third-party SDK
(`python-quickbooks`, `intuit-oauth`, etc.).

**Rationale**: This codebase has a standing, twice-established precedent
(`billing`/stub-provider, `EXTRACTION_PROVIDER_MODE`) of avoiding a real third-party SDK
dependency in favor of a thin, testable abstraction with a stub implementation — confirmed
directly: `test_no_stripe_dependency_is_imported` exists specifically to guard this for billing.
QuickBooks Online's API is a plain OAuth2 + REST/JSON API with a documented, stable shape (Bill,
Vendor, CompanyInfo entities via `/v3/company/{realmId}/query` and `/v3/company/{realmId}/bill`
etc.) — nothing about it requires a heavyweight SDK, and `python-quickbooks`'s own dependency
chain (it wraps `intuit-oauth` and adds its own ORM-like entity layer) is more surface area than
this feature needs for a read-only sync. Building directly on `httpx` keeps the connector as thin
and swappable as `webhook_security.py`'s own provider-mode split.

**Alternatives considered**: `python-quickbooks` (rejected — unnecessary ORM layer and dependency
weight for a read-only, three-entity-type integration); Intuit's official `intuit-oauth` package
alone for just the OAuth dance (rejected — the OAuth2 authorization-code + refresh-token flow is
standard enough to implement directly with `httpx`, matching how this codebase already hand-rolls
Mailgun's HMAC scheme rather than pulling in a Mailgun SDK for one function).

## R2: QuickBooks entity mapping — "Bill" vs "Invoice"

**Decision**: Sync QuickBooks's **Bill** entity (accounts payable — money this business owes its
suppliers), not its **Invoice** entity (accounts receivable — money owed *to* this business by
its own customers).

**Rationale**: The roadmap's own phrasing ("invoice and supplier sync") is imprecise in QuickBooks
terminology and led to an initial ambiguity worth resolving explicitly here rather than carrying
into the data model: ProcurePilot is a procurement platform reconciling *what this tenant was
billed by its suppliers* against *what this tenant purchased* — that is QuickBooks's `Bill`
entity by definition. `Invoice` in QuickBooks represents this tenant's own sales to its
customers, which has no relationship to procurement reconciliation at all and would be a real
product-scope error if synced instead. The spec's own "Synced Bill" entity name (chosen during
`/speckit.specify`, before this research) already anticipated the correct mapping.

**Alternatives considered**: Syncing both Bill and Invoice (rejected — Invoice is out of scope
for a procurement-side reconciliation feature and would need its own, entirely different
reconciliation logic against sales/revenue data ProcurePilot has no other model of).

## R3: Vendor identity matching — QuickBooks Vendor ↔ ProcurePilot Supplier

**Decision**: Match by exact, case-insensitive vendor display-name on first sync; store the
QuickBooks `Vendor.Id` alongside the matched `supplier.id` once matched, so subsequent syncs use
the stored link directly rather than re-matching by name every time. An unmatched vendor (no
name match) surfaces the same way an unmatched bill does — visible, not silently dropped — since
forcing every QuickBooks vendor to already exist as a ProcurePilot supplier before any of its
bills can be synced would be an unreasonable onboarding burden.

**Rationale**: Name-based first-match with a persisted link afterward mirrors this feature's own
email-ingestion sibling's supplier-matching cascade (`address history → domain → thread →
unmatched`, 013-automated-ingestion T009) — cascading specificity with an explicit unmatched
terminal state, not a forced 1:1 pre-registration requirement. A fuzzy/trigram match was
considered and rejected for v1: `pg_trgm` is already available in this codebase (product
matching, 002-catalogue-suppliers) but introducing fuzzy vendor matching risks silently linking
two different real-world suppliers with similar names, which is a worse failure mode for
financial reconciliation than leaving a vendor unmatched for a human to link manually once.

**Alternatives considered**: Trigram/fuzzy matching (rejected for v1, see above — candidate for a
later refinement once real false-negative rates from exact matching are observed); requiring
suppliers to be pre-linked before any bill sync (rejected — poor onboarding experience, blocks
the very first sync on manual data entry this feature exists to avoid).

## R4: OAuth token storage and refresh

**Decision**: Store the QuickBooks refresh token as an encrypted-at-rest column (same
`SecretStr`-at-the-application-layer / encrypted-column-at-the-database-layer pattern already
used for `smtp_password`), refreshed proactively on a schedule (QuickBooks refresh tokens are
long-lived — 100 days — but access tokens expire hourly; the sync worker refreshes the access
token at the start of every sync run rather than caching it across runs, avoiding a separate
token-refresh scheduler for a once-daily job).

**Rationale**: A once-daily sync makes token lifetime management simple — there is no need for a
background refresh scheduler independent of the sync itself, since the access token is only ever
needed for the few minutes a sync actually runs. If the refresh token itself has expired or been
revoked (FR's own "needs re-authorization" state, spec Acceptance Scenario 1.4), the sync worker
marks the connection accordingly rather than retrying indefinitely.

**Alternatives considered**: A separate token-refresh worker on a tighter schedule (rejected as
unnecessary complexity for a once-daily consumer — this is exactly the kind of unjustified
complexity Constitution Principle VI's Complexity Tracking gate would flag).

## R5: Sandbox / development environment

**Decision**: `ACCOUNTING_PROVIDER_MODE` setting (`stub` default / `quickbooks`), mirroring
`EXTRACTION_PROVIDER_MODE` and `INGESTION_EMAIL_PROVIDER` exactly. All sync/matching/discrepancy
logic is built and tested against a `StubConnector` returning fixture bill/vendor data — no real
QuickBooks sandbox account is a prerequisite for implementing or testing this feature. A real
QuickBooks Developer sandbox account is needed only for the final manual end-to-end verification
pass before this ships, the same way `INGESTION_EMAIL_PROVIDER=stub` let 013-automated-ingestion's
entire test suite pass without a live Mailgun/SES account.

**Rationale**: Matches this codebase's own established practice exactly, twice over. Removes a
real external dependency (obtaining Intuit developer credentials) from the critical path of
writing and testing the feature.

**Open item for whoever picks up implementation**: a real QuickBooks Developer account
(Intuit developer portal, free to create) and a sandbox company are needed before the
`quickbooks` provider mode can be manually verified end-to-end — this is an account-creation
task for a human, not something to fake or skip silently when that verification step is reached.

## R6: Rate limits

**Decision**: No special client-side rate-limiting logic beyond standard retry-with-backoff on a
429 response. QuickBooks Online's documented limit (500 requests/minute per realm, as of current
public API documentation) is far above what a once-daily, single-workspace sync needs — a full
sync fetches bills and vendors in a handful of paginated queries, not one request per record.

**Rationale**: Building bespoke rate-limit handling for a ceiling this feature cannot realistically
approach would be exactly the unjustified complexity Principle VI warns against. A simple
retry-with-backoff on 429 (standard `httpx` transport-level retry, no new dependency) is
sufficient and matches the effort level the actual risk warrants.

**Alternatives considered**: A token-bucket rate limiter (rejected — no evidence this feature's
request volume gets anywhere near the documented ceiling).

## R7: `purchase_record` has no `(tenant_id, id)` composite key — a real, pre-existing gap

**Finding**: `purchase_record` (`supabase/migrations/20260821000031_purchase_saving_records.sql`)
has no `unique (tenant_id, id)` constraint — only a bare primary key on `id`. Every prior feature
that references a tenant-scoped table cross-module pins its FK to that table's own
`(tenant_id, id)` composite key specifically so a cross-tenant reference can never be inserted
even from a service-role path that bypasses RLS (established explicitly in
013-automated-ingestion's `ingestion_email_log_supplier_fkey`/`catalogue_imports_supplier_fkey`,
themselves following `supplier_commercial_term`'s own precedent from 011-optimisation-supplier-iq).
`purchase_record` predates that convention and was never retrofitted — this is also named
directly in a standing memory note from a prior PR follow-up ("missing composite tenant FK,"
deferred at merge, not yet remediated).

**Decision**: This feature's own migration adds
`alter table purchase_record add constraint purchase_record_tenant_id_key unique (tenant_id, id);`
as a small companion change before adding `purchase_bill_match`'s own FK into it, rather than
either (a) using a bare, weaker FK for the new table (repeating the exact gap this codebase has
spent two features actively closing) or (b) silently working around it. This is a pure additive
constraint on an existing table — no existing row can violate a uniqueness constraint on its own
primary key paired with a non-null column already present on every row, so it is safe to add
without a backfill.

**Rationale**: Fixing the actual root gap here is proportionate (one line) and directly in scope,
since this feature is the first to need a real cross-module FK into `purchase_record` at all —
deferring it again would be choosing to reintroduce a known, already-flagged weakness into new
code on the very first opportunity to close it.
