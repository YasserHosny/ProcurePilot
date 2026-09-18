# Research: POS & Inventory Integration — Usage Signals (015)

All items below were resolved during `/speckit.specify` (Q1/Q2, both now reflected directly in
spec.md's FR-003 and FR-012) or by direct inspection of the existing codebase. No
`NEEDS CLARIFICATION` markers remain in the Technical Context.

## R1: Provider and API surface

**Decision**: Square is the first (and only, this release) POS/inventory provider. Integrate via
plain `httpx` REST calls against Square's Orders API (sales transactions) and Inventory API
(stock counts), OAuth 2.0 for authorization — no Square SDK dependency.

**Rationale**: Square exposes both sales and inventory data from one connected account, so one
connection satisfies FR-002 and FR-004 together, mirroring the accounting integration's (014)
one-connection-covers-everything shape. `httpx` is already a direct dependency
(`procurepilot_api`'s own HTTP client for the QuickBooks connector, R3.1) and Square's REST API is
plain JSON over HTTPS — no new dependency is justified for what is, in practice, `GET` calls
against two endpoints plus a token refresh call.

**Alternatives considered**: Shopify POS (also unified POS+inventory, but this codebase has no
existing pilot signal favoring it over Square); Lightspeed (API fragmented across separate Retail
and Restaurant product lines, more integration surface for less unified benefit); a Square SDK
(rejected for the same reason `python-quickbooks` was rejected in 014 research.md — an SDK adds a
dependency and its own abstraction over an API surface small enough that direct `httpx` calls are
simpler to reason about, test against a stub, and keep read-only).

## R2: Connector abstraction — reuse the 014 shape, don't invent a new one

**Decision**: `PosConnector` Protocol (analogous to `AccountingConnector`) exposing
`list_sales_transactions(since)`, `list_inventory_levels()`, `get_account_info()` — no write
method defined at all, so a write-back is a type error, not just a convention (mirrors 014's
`AccountingConnector` design, which is itself how Constitution Principle III's "never write to a
connected provider" gets enforced at the type level rather than by code review vigilance). A
`StubConnector` backs every test; `SquareConnector` is the real implementation. Selected via a
`pos_provider_mode` setting (`stub` | `square`), following the exact `accounting_provider_mode` /
`extraction_provider_mode` / `ingestion_email_provider_mode` precedent already established for
every other external integration in this codebase.

**Rationale**: FR-011 ("one connector framework across many providers, no provider schema leaking
into the domain") is a direct, literal restatement of this codebase's own already-proven pattern.
Inventing a different shape for POS specifically would violate FR-011's own intent before writing
a line of provider-specific code.

## R3: Token storage and encryption — extract, don't duplicate

**Decision**: Move `apps/api/src/procurepilot_api/modules/accounting/token_crypto.py`'s
`encrypt_token()`/`decrypt_token()` (Fernet-based, no-op passthrough when unset) to
`apps/api/src/procurepilot_api/shared/token_crypto.py`, and have both the accounting and the new
`pos` module import it from there. `pos_connection.access_token`/`refresh_token` reuse the same
`accounting_token_encryption_key`-style pattern: a dedicated `pos_token_encryption_key` setting
(distinct key from accounting's — a Square token compromise must not also expose QuickBooks
tokens, or vice versa), read/written only from a literal `service_role` connection exactly as
`accounting_connection`'s tokens already are.

**Rationale**: the crypto helper itself (Fernet wrap/unwrap of an opaque string) has no
accounting-specific logic in it at all — leaving it in `modules/accounting/` and duplicating it
verbatim into `modules/pos/` would be the exact kind of premature-but-silent duplication this
codebase's own conventions argue against, and would leave a future third provider guessing which
copy to import. Extracting it now, while there are exactly two call sites, is the point at which
this is still a mechanical, low-risk move rather than a larger refactor later.

**Alternatives considered**: Duplicate the file into `modules/pos/token_crypto.py` unchanged
(rejected — real duplication, not "three similar lines," and directly contradicts FR-011's spirit
of a single connector framework); use Postgres `pgcrypto` (`pgp_sym_encrypt`) instead of
application-layer Fernet (rejected for the same reason 014 rejected it: the plaintext key would
have to pass as a SQL query parameter on every read/write, risking exposure via query logs).

## R4: Product matching — reuse the existing similarity-search pipeline, not a new algorithm

**Decision**: Match a Square inventory/catalog item to a `workspace_product` using the same
similarity-candidate infrastructure quotation-line matching already uses
(`modules/matching/search.py`'s `build_similarity_candidates`, `modules/matching/embeddings.py`),
scored against `workspace_product.tenant_name` (and `canonical_product.name`/`brand` via the join
already used there) rather than the amount+date heuristic 014 used for bills. A match at or above
the existing auto-accept confidence threshold is applied automatically (`pos_product_match`,
`match_method='automatic'`); anything below it, or with more than one equally-strong candidate, is
left unmatched (FR-006) for manual resolution — the same automatic/manual split
`purchase_bill_match` already established, applied here with a different scoring input.

**Rationale**: this codebase already solved "confidently link an external record to a
`workspace_product`" once, with a scoring pipeline that is itself covered by the constitution's own
quality gate (≥92% precision at auto-accept, ≤8% review band). A POS item name is much closer in
shape to a quotation line's free-text product description than to an accounting bill's
vendor+amount+date triple, so the *quotation-matching* pipeline is the closer precedent to reuse,
not the *bill-matching* one, even though `purchase_bill_match`'s automatic/manual table shape is
still the right one to copy for the join table itself.

**Alternatives considered**: A bespoke Square-specific matcher keyed on SKU/GTIN exact match only
(rejected as too narrow — real Square catalogs frequently lack a clean SKU↔GTIN mapping to
ProcurePilot's own canonical product spine, per the edge case already documented in spec.md);
reusing `matching_service.select_match`'s amount+date heuristic (rejected — nothing about a POS
catalog item resembles an invoice line with an amount and a date to match on).

## R5: Sales-velocity computation window

**Decision**: Sales velocity is computed as units sold per day, averaged over a trailing 30-day
window, recomputed on every sync from the transaction data synced within that window (not a
running counter). Displayed to the buyer as e.g. "≈4.2 units/day (30-day avg)" alongside the
existing stock-on-hand figure.

**Rationale**: a 30-day window is long enough to smooth day-to-day and weekly noise (weekday vs.
weekend sales patterns) while staying short enough to reflect a real, current reordering signal —
consistent with Constitution Principle I's requirement that a derived figure state what it's
based on, not just a bare number. Recomputing from stored transactions each time (rather than
maintaining an incrementally-updated running average) keeps the figure deterministic and
replayable per Principle II: given the same 30 days of transaction data, the same average always
comes out, with no drift from incremental floating-point updates.

**Alternatives considered**: 7-day window (rejected — too noisy for typical B2B/retail purchase
cadences, which often reorder on a multi-week cycle); 90-day window (rejected — too slow to
reflect a real recent shift, e.g. a product going out of season); a running/incremental average
updated per-sync (rejected for the replayability reason above).

## R6: Worker and concurrency pattern

**Decision**: `pos_sync_worker.py` on the existing RQ/Redis queue, triggered daily plus on-demand
(same as `accounting_sync_worker.py`), using a `pg_try_advisory_lock(hashtext(connection_id))` on
a dedicated connection for the duration of the sync (guards against overlapping manual + scheduled
syncs for the same connection, FR-002's "refuse a concurrent manual trigger" rule) — identical
mechanism to 014's `SyncService.sync()`, for the identical reason (a slow external API call must
not hold a DB row lock, established precedent from `email_ingestion_worker.py`).

Worker-initiated writes (upserting `synced_product_signal` rows, recomputing velocity) use the
same tenant-scoped-session-as-`authenticated`-without-member-claims convention as every other
worker in this codebase (`_act_as_tenant_sync`-style helper), **not** a literal `service_role`
connection — the one exception remains token read/write, which alone uses `service_role` exactly
as 014 established for `accounting_connection`'s tokens.

**Rationale**: this is a mechanical reuse of an already-proven, already-tested pattern; inventing
a different concurrency or RLS-write approach for POS specifically would be unjustified complexity
under Constitution Principle VI.

## R7: Reconciling FR-003's "read-only display" with Constitution Principle IV

**Decision**: sales-velocity and stock-on-hand are surfaced as inline context attached to an
existing purchasing-decision action (Smart Compare's `offers/compare` screen, and the catalogue
product view a buyer already opens before creating a purchase request) — not as a new,
standalone dashboard route.

**Rationale**: Principle IV prohibits a "read-only dashboard as a feature in its own right," but
this feature's own User Story 2 explicitly frames the data as inline decision context ("right
where they're making the decision"), the same shape 014 used for `synced_bill`/discrepancy detail
surfaced inside the reconciliation action, not as a separate accounting dashboard. FR-003 (this
release, per the user's clarification) forbids the figure from *automatically* driving Smart
Compare's own recommendation score — but a human buyer reading it and then manually adjusting an
order quantity is itself the "executable next step" Principle IV requires; the action is human
judgment applied at an existing decision point, not the absence of one.

## R8: Signal identity survives disconnect/reconnect (analysis-time fix, SC-005)

**Decision**: `synced_product_signal` is keyed uniquely on `(tenant_id, external_item_id)`, not on
`(tenant_id, pos_connection_id, external_item_id)`. `pos_connection_id` on the row is updated to
whichever connection most recently synced it, rather than being fixed at the row's creation.

**Rationale**: `pos_connection` never reactivates a disconnected row — a reconnect always inserts a
new connection id (data-model.md). If the signal table's uniqueness included `pos_connection_id`,
the first sync after any reconnect would insert a second row for every external item already
known from before the disconnect, which is precisely the duplicate SC-005 forbids. Keying on the
external item alone, and letting the connection pointer float to "most recent," makes a reconnect
idempotent with respect to signal identity and lets existing `pos_product_match` rows (which point
at `synced_product_signal_id`) survive the reconnect with no re-matching required. Found during
`/speckit.analyze`, not during initial design — recorded here as the correction, not silently
folded into R5/R6 as if it had been the plan from the start.

**Alternatives considered**: Reactivating the original `pos_connection` row on reconnect instead
(rejected — connection history, e.g. "connected 2026-09-01, disconnected 2026-10-01," is itself a
useful audit trail (FR-010) that reactivation would erase); a separate reconciliation job to merge
duplicate signal rows post-reconnect (rejected — treats a foreseeable design flaw as a cleanup
problem rather than preventing it at the schema level).

## R9: Disclosing a partial-window velocity figure (analysis-time fix, FR-013)

**Decision**: `synced_product_signal.velocity_window_days_observed` records how many days of
actual transaction history the current `sales_velocity_per_day` is based on. The frontend shows a
figure whose `velocity_window_days_observed < velocity_window_days` as provisional (e.g. "≈4.2
units/day, based on 6 of 30 days") rather than identically to a full-window figure.

**Rationale**: Constitution Principle I (NON-NEGOTIABLE) requires insufficient data to be
disclosed explicitly, never emitted as a silent low-confidence number. A product matched only a
few days ago would otherwise show a velocity figure computed from a handful of transactions with
no visual distinction from one backed by a full 30 days — a real instance of exactly what this
principle forbids. Found during `/speckit.analyze`.

## Technical Context resolution

| Item | Resolution |
|---|---|
| Language/Version | Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) — unchanged |
| Primary Dependencies | FastAPI, `httpx` (existing), RQ/Redis (existing) — no new dependency |
| Storage | Supabase Postgres 17 (unchanged). New tables: `pos_connection`, `synced_product_signal`, `pos_product_match` |
| Testing | pytest + pytest-asyncio, Karma/Jasmine, Playwright — unchanged; `SquareConnector` tested only against `StubConnector` in the suite |
| Target Platform | Linux server (Docker), unchanged modular-monolith deployment |
| Project Type | Web application (existing `apps/api` + `apps/web`), no new deployable |
| Performance Goals | SC-001 connect in <2 min; otherwise a low-QPS daily-batch feature, no new request-path latency target |
| Constraints | Read-only against Square (no write method on `PosConnector` at all); tokens encrypted at rest via extracted `shared/token_crypto.py`; one active connection per workspace; velocity never feeds automated recommendation logic (FR-003) |
| Scale/Scope | One provider (Square) this release; 30-day trailing velocity window; daily recurring sync + on-demand manual trigger |
