# Phase 0 Research: Mobile Approvals and Delivery Receipt

## R1 — Delivery lifecycle lives on `purchase_request` itself, not a new disconnected entity

**Decision**: Extend `purchase_request.status` with two new terminal-adjacent states —
`ordered` and `delivered` — reached only from `approved` (an approved request is implicitly
"ordered" the moment a human decided to fulfil it; there is no separate "place the order" action in
this feature's scope, matching spec.md's explicit exclusion of any new purchasing action). Add
delivery-fact columns directly to `purchase_request` (or a 1:1 `purchase_request_delivery` table if
the column count grows large enough to warrant it during implementation — a call left to
data-model.md, not pre-decided here) rather than reusing or extending the existing, unrelated
`PurchaseRecord` entity (006-value-proof-launch).

**Rationale**: spec.md's own Assumptions section already flagged this tension and this research
resolves it, as promised. Three reasons favor extending `purchase_request` over touching
`PurchaseRecord`:

1. **Different actors, different trigger**. `PurchaseRecord` is written by an owner or buyer,
   after the fact, as evidence for a savings claim tied to a quotation/match/landed-cost chain —
   it exists to *prove money saved*, not to track *whether an order arrived*. This feature's
   delivery confirmation is written by a branch member, at the moment of physical receipt, with no
   necessary connection to a quotation at all (many approved requests never went through the
   quotation-matching pipeline `PurchaseRecord` was built for). Forcing one record to serve both
   jobs would mean widening `PurchaseRecord`'s write access to branch managers (a real RLS/RBAC
   change to an existing, already-shipped, financially-sensitive table) or leaving delivery
   confirmation unable to use it for requests with no matching `PurchaseRecord` row at all — a
   worse outcome than two records with two clear owners.
2. **`PurchaseRecord` has no link to `purchase_request` today**, and retrofitting one is a bigger,
   riskier change than this feature's own scope justifies — it would mean deciding how every
   *existing* `PurchaseRecord` row (predating R2.1) relates to a request that may not exist for it,
   a backfill problem this feature has no reason to take on.
3. **The roadmap's own words support this reading**: `docs/roadmap/procurepilot_roadmap.md` §12.3
   describes the "My requests" screen as showing "Draft, submitted, approved, ordered, delivered
   states with timeline" — one progression of one entity's own status, the same shape
   `purchase_request.status` already has for its first four states.

**Alternatives considered**:

- *Extend `PurchaseRecord` and add a `purchase_request_id` FK to it.* Rejected for the reasons
  above — different actor, different trigger, and a real backfill/RBAC-widening problem for an
  existing table this feature does not need to touch.
- *A new, fully separate `purchase_request_fulfillment` entity, linked by FK but not extending
  `purchase_request.status` itself.* A reasonable alternative, and data-model.md may still land
  here if the column count on `purchase_request` gets unwieldy — but for the two facts this feature
  actually needs (quantity received per line, a status flag), adding to the existing row is the
  more direct read path for the "My requests" timeline the roadmap describes, and avoids a join for
  the common case of "show me this request's current state."

## R2 — Mobile reuses 008's existing decision endpoints verbatim; no new backend surface for approvals

**Decision**: The mobile approval queue and decision screen call the exact same
`GET /approvals/pending`, `POST /requests/{id}/approve`, and `POST /requests/{id}/reject` endpoints
008-requests-approvals already built for web. No new endpoint, no new parameter distinguishing a
mobile caller, no new service-layer branch. The only backend work this half of the feature needs is
none — 009-mobile-app-mvp already proved the pattern (its home screen's read-only pending count
calls `GET /approvals/pending` today; this feature's mobile approval queue is the same call,
rendered as an actionable list instead of a bare count) and 008's endpoints were never mobile-
specific to begin with (there is nothing "web" about a JSON POST with a bearer token).

**Rationale**: This is the most constitutionally sensitive decision in this plan (Principle III).
A second decision code path — even one that produces an identical result — is exactly the kind of
thing that could accidentally diverge in authorization logic, audit action strings, or the
`_require_assigned_approver_or_owner` check over time. Calling the same endpoint, from a second
client, with zero server-side awareness of which client is calling, makes divergence structurally
impossible rather than merely unintended. This mirrors 009's own precedent for request submission
("mobile is a new way in, not a new decision path") applied to the more consequential half of the
workflow.

**Alternatives considered**:

- *A mobile-optimized decision endpoint* (e.g., returning a slimmer payload). Rejected — no
  evidence this release needs it (the existing payload is already small: lines, total, budget
  status, requester), and it is exactly the kind of premature divergence Principle III's gate
  exists to prevent.

## R3 — Quality-issue photo evidence reuses the `quotation-documents` Storage isolation pattern exactly

**Decision**: A new Supabase Storage bucket, `quality-issue-photos`, with the identical
tenant-isolation-by-object-path RLS policy `supabase/migrations/20260819000020_quotation_
storage.sql` already established for `quotation-documents` — paths allocated server-side under
`tenants/{tenant_id}/quality-issues/{issue_id}/{filename}`, the client never supplies `tenant_id`,
and `storage.foldername(name)` gates every operation on the tenant segment matching
`current_tenant_id()`.

**Rationale**: This codebase has exactly one prior precedent for "a tenant-scoped file that must
not be readable across tenants even with a guessed path" — inventing a second, differently-shaped
pattern for the second file-storage need this project has ever had would be arbitrary novelty with
no benefit. The bucket is separate (not reusing `quotation-documents` itself) because these are
unrelated document types with unrelated lifecycles and no reason to share a bucket's size/type
limits or retention policy.

**Alternatives considered**:

- *Store photos as base64 in a Postgres column.* Rejected outright — this project's data model
  stores no binary blobs anywhere else, and Postgres row/page bloat from image data would be a
  real, avoidable operational cost for something Storage already solves cleanly.
- *A single shared "attachments" bucket for all file types this project might ever need.*
  Rejected as premature generalization (Principle VI, "until scale demands otherwise") — two
  buckets with two clear, narrow policies are simpler to reason about than one bucket with a
  type-dispatching policy for a need that does not exist yet.

## R4 — Camera/image package selection is an implementation-time decision, not a plan-time one

**Decision**: This plan does not pin a specific Flutter camera/image-picker package or version.
`apps/mobile/pubspec.yaml` has none today (confirmed absent as of 009's own delivery); whichever
package implementation selects should be wrapped behind a small abstraction in
`apps/mobile/lib/core/camera/`, mirroring the existing `BiometricAuth`/`NotificationPermission`
abstract-class-plus-fake pattern already used twice in this codebase (`core/auth/biometric_gate.
dart`, `core/offline_queue`'s notification counterpart from 009) — so widget tests can inject a
fake capture result without touching a real camera or the device's photo library.

**Rationale**: This project's own established practice (visible in 009's own plan for its push
client) is to defer a specific third-party package version to implementation time rather than
pin one during planning, since package churn in the Flutter ecosystem is fast enough that a
version chosen today may already be superseded by a better-maintained option when implementation
actually starts. What planning *does* need to fix — and does, above — is the shape of the
abstraction so implementation has a clear, testable seam to build against, matching this
codebase's own convention rather than inventing test infrastructure per-feature.

**Alternatives considered**:

- *Pin an exact package now.* Rejected for the reason above — this plan fixes the architecture
  (an injectable abstraction), not a dependency-lockfile decision better made at implementation
  time.
