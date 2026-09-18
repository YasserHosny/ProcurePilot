# Feature Specification: POS & Inventory Integration — Usage Signals

**Feature Branch**: `015-pos-inventory-integration`
**Created**: 2026-09-18
**Status**: Draft
**Input**: User description: "R3.2 — POS and inventory integration plus usage signals. Per docs/roadmap/procurepilot_roadmap.md section 8 (Phase 3, Connected Operations): one POS provider integration feeding sales-velocity usage signals into purchasing recommendations, plus inventory integration (stock-on-hand sync) where a system exists. Builds on the connector and sync architecture established in R3.0 (email ingestion) and R3.1 (accounting integration) rather than inventing a new integration pattern. Per the roadmap integration principles: CSV and email before APIs where a spreadsheet can satisfy early customers, one connector framework across many providers with no provider schema leaking into the domain, integrations must be revocable and degrade gracefully to manual input rather than blocking purchasing, and provider choice should be driven by actual pilot demand rather than market size."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect a POS account and see real demand signal (Priority: P1) 🎯 MVP

A buyer or owner connects the workspace's point-of-sale system. Once connected, each product in
the catalogue shows how quickly it has actually been selling — not a guess, a real number pulled
from the register — so a reorder decision is grounded in demand instead of instinct or a stale
memory of "we usually order this much."

**Why this priority**: Everything else in this feature (inventory context, any later forecasting
in Phase 4) depends on a working, trustworthy connection existing first. Without it, there is
nothing to show and nothing to build on. This mirrors R3.1's own priority order: connect first,
demonstrated independently of what's synced later.

**Independent Test**: Connect a POS account (or fail to connect one) using a stub/sandbox
provider and verify the connection lifecycle — connect, see status, disconnect — works correctly
on its own, with no sales-velocity or inventory data involved yet.

**Acceptance Scenarios**:

1. **Given** no POS connection exists for the workspace, **When** an owner starts the connect
   flow and authorizes access, **Then** the workspace shows an active connection with the
   connected account's name.
2. **Given** an active connection, **When** the owner disconnects it, **Then** the connection
   status becomes disconnected and previously-synced sales-velocity data remains visible and
   correctly labelled as no longer updating, rather than disappearing.
3. **Given** a connection attempt is declined or fails partway through, **When** the owner
   returns to the connection screen, **Then** no partial or broken connection record exists —
   only a clean "not connected" state.
4. **Given** an active connection whose access has been revoked on the provider's side (e.g. the
   owner disconnected ProcurePilot from within the POS system itself), **When** the next sync
   runs, **Then** the connection is marked as needing re-authorization rather than silently
   failing or showing stale data as if it were current.

---

### User Story 2 - See stock-on-hand before deciding how much to order (Priority: P2)

With inventory sync active, a buyer comparing supplier offers or building a purchase request sees
the current stock-on-hand for a product right where they're making the decision, so they don't
order more of something that's already sitting on the shelf, or under-order something that's
about to run out.

**Why this priority**: This is the second half of "usage signals" and depends on User Story 1's
connection existing — it delivers its own, separable value once a connection is live (a buyer
benefits from seeing stock levels even before any velocity-based logic is built on top of it in a
later release), matching this codebase's own precedent of layering sync-derived read models on
top of a connection story before any matching/reconciliation logic (R3.1 did the same: connect,
then sync + match, as two separate releases' worth of stories, but within one release here since
inventory and sales data typically come from the same underlying POS system).

**Independent Test**: With a stub-connector connection already established, trigger a sync and
verify stock-on-hand appears correctly against the right products, independent of whether any
sales-velocity number is also showing.

**Acceptance Scenarios**:

1. **Given** an active connection with inventory sync, **When** a sync completes, **Then** each
   matched product shows its current stock-on-hand figure and when it was last updated.
2. **Given** a product with no matching item in the connected POS/inventory system, **When** a
   buyer views that product, **Then** no stock figure is shown and the product behaves exactly as
   it did before this feature existed — never a misleading zero or blank implying "no stock."
3. **Given** a stock-on-hand figure that is more than one sync cycle old, **When** a buyer views
   it, **Then** its "last updated" label makes the staleness visible rather than presenting it as
   live.

---

### User Story 3 - Purchasing keeps working exactly as before if the integration is disconnected or was never connected (Priority: P3)

An owner disconnects the POS/inventory integration, or a tenant simply never connects one at all.
Every purchasing workflow — comparing offers, building requests, recording purchases — continues
to work exactly as it did before this feature existed, with manual quantity entry, and with zero
loss of previously recorded data.

**Why this priority**: This is the direct expression of the roadmap's own non-negotiable
integration principle ("integrations must be revocable... must degrade gracefully to manual
input, never block purchasing") and of Constitution Principle VI (modular monolith, no
hard dependency between unrelated capabilities). It is lower priority to build as its own
user-facing feature only because it is largely a *constraint* on how Stories 1 and 2 are built,
not new functionality of its own — but it must be independently verifiable, because a
regression here (purchasing breaking because an integration went away) is a severe,
trust-destroying failure mode for every tenant who never opted in, and confirming it keeps this
feature genuinely additive infrastructure rather than a new point of failure for the core
purchasing flow every tenant already depends on.

**Independent Test**: With no POS connection ever created (the default state for every existing
tenant), verify every purchasing screen behaves identically to how it did before this feature
shipped — no errors, no missing controls, no broken layout waiting for data that will never
arrive.

**Acceptance Scenarios**:

1. **Given** a tenant that has never connected a POS/inventory integration, **When** they use any
   purchasing screen, **Then** the screen looks and behaves exactly as it did before this feature
   existed, with no error states, loading spinners that never resolve, or broken layout.
2. **Given** a tenant with an active connection that then disconnects it, **When** they continue
   using purchasing screens immediately afterward, **Then** manual quantity entry and comparison
   continue to work with no interruption, and no in-progress purchase request or comparison is
   lost or blocked.

### Edge Cases

- What happens when the connected POS account's catalogue uses different product identifiers or
  names than ProcurePilot's own catalogue, and nothing matches automatically? (Mirrors R3.1's own
  vendor-matching edge case — an unmatched item must be visible and correctable, never silently
  dropped.)
- How does the system handle a POS/inventory provider that only supports fetching a stock
  snapshot (a instantaneous "as of now" state) with no historical sales data at all — can sales
  velocity still be computed over time from repeated snapshots, or does that provider only ever
  support inventory sync, not usage signals?
- What happens if two products in ProcurePilot's own catalogue both plausibly match the same
  single item in the connected system (e.g. a bundle vs. its component)? Per the matching
  precedent from R3.1, an ambiguous match must be left unmatched for manual resolution, never
  auto-picked.
- How does the system behave the first time a connection is made and there is no sync history yet
  — is a "not enough data yet" state shown for sales velocity specifically, distinct from "not
  connected" and from "connected but nothing sold yet"? Resolved by FR-013: a velocity figure
  based on less than a full window is shown as provisional with its actual basis stated, not
  withheld entirely and not presented as equivalent to a full-window figure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let an owner authorize a connection to one external POS/inventory
  provider per workspace, following the same connect/status/disconnect lifecycle already
  established for the accounting integration (R3.1): connecting requires explicit owner
  authorization, the current connection status is visible to any authenticated member at all
  times, and disconnecting never deletes previously synced data.
- **FR-002**: The system MUST sync sales transaction data from the connected provider on a daily
  recurring schedule and support an on-demand manual sync trigger, refusing a manual trigger if a
  sync for that connection is already in progress rather than queueing a second one (matching
  R3.1's own concurrency rule and daily cadence).
- **FR-003**: The system MUST compute a sales-velocity figure per matched product from synced
  transaction data over a defined rolling window and display it as read-only context wherever a
  buyer already makes purchasing decisions today (Smart Compare, product catalogue). It MUST NOT
  alter Smart Compare's recommendation scoring, ranking, or any other automated purchasing logic —
  demand forecasting and predictive reorder proposals remain explicitly out of scope for this
  feature and belong to the separate, later Phase 4 (predictive procurement), which requires 6+
  months of accumulated history before it is viable.
- **FR-004**: The system MUST sync stock-on-hand data from the connected provider for every
  product the provider tracks inventory for, and display it against the matching ProcurePilot
  catalogue product with a visible "last synced" timestamp.
- **FR-005**: A product with no confidently-matched counterpart in the connected system MUST
  display no stock or velocity data at all, and MUST NOT be treated differently from a product in
  a workspace with no integration connected — the absence of a signal must never look like "zero"
  or otherwise mislead a buyer into a wrong decision.
- **FR-006**: The system MUST leave an ambiguous match (more than one equally-plausible candidate)
  unresolved for manual review rather than automatically selecting one, matching the tie-breaking
  rule already established for accounting-bill matching (R3.1).
- **FR-007**: Disconnecting the integration, or a tenant never having connected one, MUST NOT
  degrade, block, or alter any purchasing workflow (comparison, purchase requests, recording a
  purchase) in any way — every such workflow must remain fully manual-entry-capable independent
  of this feature's presence.
- **FR-008**: A connection whose access has been revoked on the provider's own side MUST be
  detected on the next sync attempt and marked as needing re-authorization, rather than failing
  silently or continuing to display increasingly stale data as if it were current.
- **FR-009**: The system MUST enforce tenant isolation on all connection, sales-velocity, and
  inventory data with the same database-level guarantee (row-level security, forced) already
  required of every tenant-scoped table in this codebase.
- **FR-010**: The system MUST record an audit trail entry for connecting, disconnecting, and each
  sync attempt (started/completed/failed), matching the audit-event conventions already
  established for every other integration in this codebase.
- **FR-011**: The connector abstraction MUST be provider-agnostic at the domain boundary — no
  provider-specific field name, identifier shape, or API quirk may leak into ProcurePilot's own
  data model or user-facing screens, so a second provider can be added later without reshaping
  this feature's own schema (matching the roadmap's own "one connector framework, many providers"
  principle).
- **FR-012**: The first POS/inventory provider integrated MUST be Square. Square's unified
  POS+inventory API lets one connection satisfy both FR-002 (sales) and FR-004 (stock) from a
  single account, mirroring R3.1's own one-connection-covers-everything shape, and its
  small/mid-market fit matches this codebase's target customer profile better than the
  alternatives considered (Shopify POS, Lightspeed).
- **FR-013**: A sales-velocity figure computed from less than a full rolling window of history
  (e.g. a product matched only 6 days ago, against a 30-day window) MUST be visibly marked as
  provisional and state how much history it is actually based on, rather than being displayed
  indistinguishably from a figure computed over the full window — per Constitution Principle I,
  insufficient data must be disclosed explicitly, never silently presented as if it were as
  reliable as a complete figure.

### Key Entities *(include if feature involves data)*

- **POS Connection**: One workspace's authorized link to one external POS/inventory account.
  Tracks provider, connection status (active / needs re-authorization / disconnected), who
  authorized it, when it last synced. At most one active connection per workspace at a time,
  mirroring the accounting connection's own shape.
- **Synced Product Signal**: The most recent sales-velocity and/or stock-on-hand figures for one
  external catalogue item as of the last successful sync, linked to a ProcurePilot catalogue
  product once matched. An unmatched signal is visible for manual resolution, never silently
  dropped.
- **Product Match**: The link between a Synced Product Signal and a ProcurePilot catalogue
  product — automatic where confident and unambiguous, left for manual resolution otherwise.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An owner can connect their POS/inventory account and see the connection reflected
  as active, from clicking "Connect" to seeing the active state, in under 2 minutes — the same
  connect-flow budget already proven for the accounting integration.
- **SC-002**: After a successful sync, at least 90% of a pilot workspace's top-selling products
  (by transaction count) show a computed sales-velocity figure, with the remainder visibly listed
  as unmatched for manual review rather than silently missing.
- **SC-003**: Stock-on-hand figures shown to a buyer are never more than one full sync cycle out
  of date, and that staleness is always visible on the figure itself, not just discoverable by
  cross-referencing the connection's own last-synced timestamp elsewhere.
- **SC-004**: 100% of purchasing workflows (compare, request, record purchase) function
  identically with and without an active POS/inventory connection, verified directly rather than
  assumed — a tenant that disconnects mid-session never sees a broken screen or loses in-progress
  work.
- **SC-005**: Disconnecting the integration and reconnecting it (to the same or a different
  account) never produces duplicate or conflicting product-signal records for the same
  ProcurePilot catalogue product.
