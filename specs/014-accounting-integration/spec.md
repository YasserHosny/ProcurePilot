# Feature Specification: Accounting Integration & Reconciliation Foundation

**Feature Branch**: `014-accounting-integration`
**Created**: 2026-09-17
**Status**: Draft
**Input**: User description: "R3.1 — Accounting integration #1 + reconciliation foundation. Per
docs/roadmap/procurepilot_roadmap.md §8 (Phase 3, Connected Operations): the first of two planned
accounting-provider integrations (invoice and supplier sync, spend reconciliation), laying the
reconciliation foundation that R3.3 will later extend with order tracking and a three-way match
(PO → confirmation → delivery note → invoice) and a second accounting provider. Establishes the
connector/sync architecture, the reconciliation data model, and the first real accounting
connection ProcurePilot has ever had — everything before this release has been procurement-side
only, with no visibility into what actually gets invoiced or paid."

## Clarifications

### Session 2026-09-17

- Q: What counts as an automatic match between a synced bill and a purchase record? → A: Exact
  amount (or within rounding, e.g. $0.01) plus within a 14-day date window.
- Q: How long after a purchase record has no matching bill before it's flagged as a discrepancy?
  → A: 30 days, aligned with common net-30 supplier payment terms.
- Q: How often does the recurring sync run? → A: Daily.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect an accounting account (Priority: P1)

A workspace owner connects the business's accounting software to ProcurePilot, so that supplier
bills and invoices recorded there become visible for reconciliation against what was actually
ordered and received.

**Why this priority**: Every other capability in this release depends on a live, authorized
connection existing first. Without it, there is nothing to reconcile.

**Independent Test**: Can be fully tested by an owner completing the connection flow and seeing
the connection show as active, with no reconciliation logic involved yet — delivers standalone
value as proof the two systems can talk to each other at all.

**Acceptance Scenarios**:

1. **Given** a workspace with no accounting connection, **When** the owner starts the connection
   flow and authorizes access in the provider's own consent screen, **Then** the workspace shows
   an active connection with the connected company/account name and the date it was connected.
2. **Given** an active connection, **When** the owner chooses to disconnect it, **Then** the
   connection is revoked immediately, no further data syncs from that account, and previously
   synced records remain visible (disconnecting stops new data, it does not erase history).
3. **Given** the owner starts the connection flow, **When** they decline authorization in the
   provider's consent screen or it fails for any reason, **Then** ProcurePilot shows a clear
   failure state and the workspace remains in its prior (not-connected, or still-connected-to-the-
   previous-account) state — a failed attempt never leaves a half-connected workspace.
4. **Given** an active connection whose authorization has expired or been revoked on the
   provider's side (outside ProcurePilot), **When** the next sync attempt runs, **Then** the
   workspace is shown as needing re-authorization rather than silently failing to sync.

---

### User Story 2 - See synced bills and invoices alongside purchase records (Priority: P2)

A buyer or owner sees the supplier bills and invoices recorded in the connected accounting system,
matched automatically where possible against ProcurePilot's own purchase records for the same
supplier, so they can see at a glance whether what was billed lines up with what was ordered.

**Why this priority**: This is the actual reconciliation value the release exists to deliver — a
connection with nothing to look at is not yet useful.

**Independent Test**: Can be tested by connecting a real (or sandbox) account with existing bills,
triggering a sync, and confirming the bills appear with the correct supplier, amount, currency,
and date — independent of whether automatic matching succeeds for any of them.

**Acceptance Scenarios**:

1. **Given** an active connection with existing bills at the provider, **When** a sync completes,
   **Then** every bill appears in ProcurePilot with its supplier, amount (with explicit currency),
   bill date, and status (open/paid/void, as the provider reports it).
2. **Given** a synced bill whose supplier, amount, and approximate date match an existing
   ProcurePilot purchase record for the same supplier, **When** the sync completes, **Then** the
   bill and the purchase record are shown linked together as a matched pair.
3. **Given** a synced bill with no reasonably matching purchase record, **When** viewed in
   ProcurePilot, **Then** it is clearly shown as unmatched rather than silently omitted or
   force-matched to the nearest candidate.
4. **Given** a bill that was already synced and later changes at the provider (amount corrected,
   voided, paid), **When** the next sync runs, **Then** ProcurePilot's copy reflects the update
   rather than keeping stale data indefinitely.

---

### User Story 3 - Review and resolve reconciliation discrepancies (Priority: P3)

An owner or buyer reviews a list of reconciliation exceptions — bills that don't match any
purchase record, purchase records with no corresponding bill after 30 days, or matched pairs
whose amounts disagree — and marks each one resolved once they've investigated it, so
discrepancies don't silently accumulate unnoticed.

**Why this priority**: Automatic matching (User Story 2) handles the easy cases; the actual
business value of "know what's really being spent" comes from surfacing the cases that need a
human to look at them.

**Independent Test**: Can be tested by seeding a mix of matched, unmatched, and amount-mismatched
records and confirming the discrepancy list shows exactly the ones that need attention, with
enough context (supplier, amounts, dates, the specific mismatch) to act without leaving the
screen.

**Acceptance Scenarios**:

1. **Given** a bill whose amount differs from its matched purchase record's own recorded cost,
   **When** viewing the discrepancy list, **Then** the mismatch is shown with both figures side by
   side, in their own explicit currencies.
2. **Given** an unmatched bill (immediately) or an unmatched purchase record more than 30 days old
   (giving normal net-30 invoicing time to catch up), **When** viewing the discrepancy list,
   **Then** it appears there with enough detail (supplier, amount, date) to investigate without
   cross-referencing another screen.
3. **Given** a discrepancy the reviewer has investigated and considers resolved (e.g. a legitimate
   price change, or a manual match they've confirmed by eye), **When** they mark it resolved,
   **Then** it no longer appears in the active discrepancy list but its resolution is recorded
   (who resolved it, when, and any note they added) for later reference.
4. **Given** a resolved discrepancy, **When** the underlying bill or purchase record changes again
   at a later sync, **Then** it is re-evaluated rather than staying silently resolved against
   stale data.

### Edge Cases

- What happens when the same accounting connection is attempted from two browser tabs/sessions at
  once? The second attempt must not create a duplicate connection or leave the workspace in an
  inconsistent state.
- What happens when a sync is already in progress and another one is triggered (manually or by
  schedule) before it finishes? The system must not run two overlapping syncs for the same
  connection.
- What happens when the provider's API is unreachable or rate-limits ProcurePilot mid-sync? The
  workspace must show the sync as failed/incomplete rather than silently missing data with no
  indication anything went wrong.
- What happens to already-synced bills and matches if the connection is later disconnected and a
  *different* accounting account is connected afterward? Historical data from the first account
  must not be silently merged with or overwritten by the second.
- What happens when a bill at the provider is denominated in a currency ProcurePilot does not
  otherwise support for this tenant? It must be surfaced explicitly (with its real currency,
  never silently converted or dropped), not hidden.
- What happens when a workspace member without permission to view financial data is signed in
  during this feature's rollout? Reconciliation data must respect the same role-based visibility
  the rest of the product already uses for commercial/financial information.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let a workspace owner initiate an authorization flow to connect one
  QuickBooks Online account to the workspace (the first of the two accounting-provider
  integrations R3.0's roadmap entry calls for; a second provider is out of scope for this release
  and belongs to R3.3).
- **FR-002**: The system MUST show the current connection state (not connected / connected with
  account name and connection date / needs re-authorization) at all times, not just at the moment
  of connecting.
- **FR-003**: Only a workspace owner MUST be able to connect or disconnect the accounting
  integration, matching this product's existing pattern of gating integration-level settings to
  the owner role.
- **FR-004**: The system MUST support disconnecting an active connection without deleting
  previously synced records.
- **FR-005**: The system MUST sync supplier bills/invoices from the connected account, capturing
  at minimum: supplier name, amount, explicit currency, bill date, and the provider's own status
  for that bill.
- **FR-006**: The system MUST sync the connected account's supplier/vendor list to support
  matching synced bills against ProcurePilot's own supplier records, without requiring a buyer to
  manually re-enter supplier identity information the accounting system already has.
- **FR-007**: The system MUST automatically match each synced bill to an existing ProcurePilot
  purchase record when they share the same supplier, the amount is identical (allowing for
  currency-rounding differences up to $0.01), and the bill date falls within 14 days of the
  purchase record's own date — and MUST clearly distinguish a matched pair from an unmatched bill
  or purchase record rather than guessing silently. A bill or purchase record with more than one
  equally-qualifying candidate is left unmatched for manual review rather than auto-picked.
- **FR-008**: The system MUST re-sync once daily (not solely on manual request) so that
  reconciliation data does not silently go stale, and MUST also support an on-demand manual sync.
- **FR-009**: The system MUST prevent two sync operations from running concurrently for the same
  connection.
- **FR-010**: The system MUST surface a reconciliation discrepancy list distinct from the general
  matched-bills view, covering: amount mismatches on matched pairs, bills with no matching
  purchase record (flagged immediately), and purchase records with no matching bill after 30 days
  (aligned with common net-30 supplier payment terms).
- **FR-011**: The system MUST let an owner or buyer mark a discrepancy as resolved, recording who
  resolved it, when, and an optional note, and MUST re-surface a previously resolved discrepancy
  if the underlying records change again afterward.
- **FR-012**: The system MUST record every connect, disconnect, sync, and discrepancy-resolution
  event to this workspace's audit history, consistent with every other commercially significant
  action in the product.
- **FR-013**: The system MUST NOT create, modify, or delete any record in the connected accounting
  system — this release is strictly read-only with respect to the connected provider. All match
  and discrepancy-resolution state (User Stories 2 and 3) lives only in ProcurePilot; nothing is
  ever written back to the accounting provider. Write-back (e.g. tagging a bill as reconciled at
  the provider itself) is explicitly out of scope for this release and is a candidate for a later
  one, not assumed here.
- **FR-014**: The system MUST respect this product's existing tenant isolation and role-based
  visibility rules for all synced financial data — a member of one workspace must never see
  another workspace's connection, synced bills, or discrepancies, and a member without financial
  visibility permissions must not see reconciliation data other roles can.
- **FR-015**: The system MUST scope the initial historical sync to bills from the last 90 days at
  connection time by default, rather than importing a connected account's entire multi-year
  history unconditionally, to keep first-sync volume and duration predictable; ongoing syncs after
  the initial one are unaffected by this window.

### Key Entities *(include if feature involves data)*

- **Accounting Connection**: One workspace's authorized link to one external accounting account.
  Tracks which provider, the connected account's own display name, connection and
  last-successful-sync timestamps, and current health (active / needs re-authorization /
  disconnected). Exactly one active connection per workspace for this release (a workspace does
  not connect multiple accounting accounts simultaneously).
- **Synced Bill**: One supplier bill/invoice as recorded by the connected accounting system at the
  time of the most recent sync — supplier, amount, explicit currency, bill date, provider status,
  and a reference back to the provider's own record so updates can be matched to the right row on
  the next sync.
- **Purchase-Bill Match**: A link between a Synced Bill and an existing ProcurePilot purchase
  record, however that purchase record already exists in the product today, produced either
  automatically (by the matching in FR-007) or confirmed manually by a reviewer resolving a
  discrepancy.
- **Reconciliation Discrepancy**: A flagged exception — an amount mismatch on a matched pair, an
  unmatched bill, or an unmatched purchase record past its grace period — with its own resolution
  state (open / resolved), resolver identity, resolution timestamp, and optional note.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A workspace owner can connect their accounting account and see it reflected as
  active in under 2 minutes, without needing help documentation.
- **SC-002**: Within one sync cycle of connecting, at least 90% of an account's genuinely matching
  bills (same supplier, amount within $0.01, and a purchase record within 14 days) are
  automatically linked without manual intervention.
- **SC-003**: A reviewer can find and resolve a real reconciliation discrepancy end-to-end
  (identify it, see enough context to judge it, mark it resolved) in under 60 seconds per
  discrepancy, without leaving the discrepancy screen.
- **SC-004**: Zero synced financial records are ever visible to a member of a different workspace,
  verified the same way every other tenant-isolation guarantee in this product is verified.
- **SC-005**: A disconnected accounting integration never causes data loss — 100% of previously
  synced bills, matches, and discrepancy history remain visible and unchanged after disconnecting.
