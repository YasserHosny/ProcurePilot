# Phase 0 Research: Mobile MVP

## R1 — Device push-token registration: a small standalone module, delivery via the existing job queue

**Decision**: `device_registration` is a small, standalone table (one row per signed-in
member+device install) written through a new `devices` module in `apps/api`. Registration is a
plain upsert keyed on `(tenant_id, member_id, push_token)` at sign-in and whenever the OS reissues
a token; no separate "unregister" endpoint is needed for this release — an app reinstall or a
newer registration simply supersedes the old row (`last_seen_at` bump on every app-open handles
staleness, per spec.md's edge case on reinstall/new-device). Sending a push itself is **not** a
synchronous HTTP call made from the request/approval decision path — it is queued onto the
existing RQ job worker (`services/` background-jobs infrastructure already used for extraction)
the moment `approval_step.status` transitions away from `pending`, exactly the same way every other
side-effecting fan-out in this codebase is decoupled from its triggering request/response cycle.

**Rationale**: Keeping registration in its own module (not inside `requests/`) follows Principle VI
directly — push delivery is infrastructure a future feature (a low-stock alert to an owner, say)
will also need, and nothing about it is conceptually a purchase-request concern. Queuing the actual
send rather than calling FCM/APNs inline keeps a request/approval decision's response time
independent of a third-party push provider's latency or an outage — the approval endpoint's
existing contract and error envelope stay unchanged; a push failure degrades to "notification not
delivered," never to "the approval itself failed," matching FR-008's requirement that the app keep
working fully without push.

**Alternatives considered**:
- *Send the push synchronously inside the approve/reject request handler.* Rejected: couples an
  approver's decision latency to an external push provider's round-trip, and a transient FCM/APNs
  outage would have no business making `POST /requests/{id}/approve` itself slow or error.
- *Fold `device_registration` into the existing `membership` table as nullable push-token columns.*
  Rejected: a member can have more than one device (phone + a second phone, or a reinstall before
  the old row is known-stale), so this is genuinely a one-to-many relationship, not a
  one-to-one extension of `membership`.

## R2 — Low-stock report: a standalone table, not folded into `purchase_request`

**Decision**: `low_stock_report` is its own table — `member_id`, `branch_id`, `workspace_product_id`,
an optional `count_remaining`, and `created_at`. It is insert-only from the mobile client (no
update/delete surface this release — a duplicate double-tap is collapsed client-side per spec.md's
edge case, not de-duplicated server-side with a uniqueness constraint, since two genuine
"still running low" taps on different days are both legitimate signals, not duplicates). It lives
inside the existing `requests` module (per FR-006 and the Key Entities section of spec.md, it is a
request-adjacent signal a branch manager raises about the same catalogue a purchase request draws
from) rather than getting a fourth backend module for one small endpoint pair.

**Rationale**: The spec is explicit and repeated across three places (User Story 3, FR-006, Key
Entities) that a low-stock report MUST NOT create, modify, or commit to any purchase request — it
is not a first line, seed, or draft of one, so it has no reason to live inside `purchase_request`'s
own hierarchy or to trigger `purchase_request`'s value-estimation/routing machinery. A dedicated
table keeps that boundary structurally obvious rather than relying on a status flag or nullable
column on `purchase_request` to mean "this one isn't real yet," which would blur exactly the
distinction the spec insists on.

**Alternatives considered**:
- *Model a low-stock report as a draft `purchase_request` with zero lines and a special flag.*
  Rejected outright — this is precisely the conflation FR-006 forbids ("without that report itself
  creating, modifying, or committing to any purchase request"), and it would drag routing/valuation
  logic that has no meaning for a one-tap signal.
- *A generic `signal`/`event` table shared across future mobile-native quick actions.* Rejected for
  this release: YAGNI — there is exactly one such signal today (low-stock); a shared table designed
  for a second use case that does not yet exist would be speculative generality, not something this
  chunk needs to build correctly.

## R3 — Mobile auth reuses R1/R2.1's JWT+refresh unchanged; biometric unlock is client-only

**Decision**: The mobile app authenticates against the exact same Supabase Auth endpoint web
already uses — no new backend auth surface. The access/refresh token pair is stored in
`flutter_secure_storage` (iOS Keychain / Android Keystore-backed). Biometric "unlock" (FR-001) is
purely a client-side gate in front of *using* an already-valid stored refresh token — it verifies
the device owner's fingerprint/face via `local_auth`, then lets the app proceed to silently refresh
the session, exactly as if the member had typed their password. Biometric enrollment state lives
only on-device; the backend has no concept of "this member has biometrics enabled" and needs none.
Session revocation (FR-014) already works today because R1's refresh-token invalidation is
server-side — the mobile app inherits it for free the next time it attempts a refresh (biometric
unlock included: a revoked refresh token fails to refresh regardless of a successful fingerprint
match, correctly forcing re-authentication per spec.md's edge case).

**Rationale**: The constitution's Principle VI (Modular Monolith Until Scale Demands Otherwise)
argues directly against a parallel mobile-specific auth path; R1's JWT/refresh mechanism was never
web-specific in the first place; reusing it verbatim is the null-cost option and the only one that
does not introduce a second thing to keep secure. Client-only biometrics is the standard mobile
pattern (both `local_auth` and platform guidance treat biometric APIs as a local gate, not an
identity assertion sent to a server) — sending "biometric succeeded" to the backend as if it were a
credential would be a meaningfully weaker auth story, not a stronger one.

**Alternatives considered**:
- *A dedicated mobile OAuth client / device-code flow distinct from web's.* Rejected: no
  requirement in spec.md calls for it, and it would be new complexity with no corresponding new
  capability — Supabase Auth's existing email/password (or whatever web already uses) flow works
  identically from a Flutter HTTP client.
- *Register a device public key server-side and treat a biometric-signed challenge as a second
  auth factor the backend verifies.* Rejected as over-engineering for this release — spec.md frames
  biometric re-entry as a convenience over already-issued credentials (FR-001: "not required to
  re-enter credentials on every launch"), not as a stronger authentication requirement the backend
  needs to enforce.

## R4 — Offline queue reuses the existing Idempotency-Key mechanism, not a new protocol

**Decision**: A request or low-stock report built while offline (FR-010) is persisted to an
on-device local store (MMKV/SQLite) with a client-generated `Idempotency-Key` (a UUID) stamped onto
it at creation time, not at send time. When connectivity returns, the app replays the queued
submission using that same key exactly the way an online submission already uses one. If the first
attempt actually reached the server but the confirmation was lost (spec.md's User Story 5, scenario
4), the replayed request with the same `Idempotency-Key` is recognized server-side and returns the
original result rather than creating a duplicate — no new dedup logic is needed because
`Idempotency-Key` handling already exists on every mutation per this codebase's API conventions
(CLAUDE.md: "`Idempotency-Key` on mutations"). The client shows three honest states — local draft,
queued (has a key, not yet confirmed), confirmed — and FR-012 is satisfied by never marking
something "submitted" until the confirmed response actually arrives.

**Rationale**: The PR #2 follow-up findings already on record for this codebase call out a
*systemic unused Idempotency-Key* gap elsewhere in the product — inventing a second, mobile-only
offline-sync protocol here would both duplicate a mechanism that already exists and risk repeating
that exact class of bug in a new place. Stamping the key at creation time (not send time) is the
detail that makes retry-after-partial-failure safe: if key generation happened at send time, a
retry after a dropped response would generate a *new* key and defeat the whole purpose.

**Alternatives considered**:
- *A bespoke sync-queue protocol with server-side sequence numbers per device.* Rejected: strictly
  more moving parts for the same guarantee `Idempotency-Key` already gives, and a new protocol is a
  new thing to get right under Principle VI's "until scale demands otherwise" test — nothing about
  this release's scale demands it.
- *Optimistically mark a queued item "submitted" the moment it is queued, reconciling silently
  later.* Rejected directly by FR-012 ("MUST NOT report a submission as successful before it has"
  reached the server) — this is the exact false-positive state the requirement forbids.

## R5 — No presigned-photo-upload endpoint this release; confirmed out of scope

**Decision**: This chunk adds no file/photo upload surface of any kind. Camera/barcode capture
(shelf photo, barcode scan, delivery/damage photo) is explicitly R2.3 work per spec.md's own scope
statement and Edge Cases section ("Does this release put photo attachment, barcode scanning, or any
camera capability on mobile? No"). `low_stock_report` carries no image field; `purchase_request`'s
existing shape is reused completely unchanged, with no new optional photo attribute added
speculatively ahead of R2.3 actually needing it.

**Rationale**: Direct traceability to spec.md rather than a judgment call — the spec answers this
question explicitly, so research.md's job here is only to record that the answer was read and
honored, not to re-derive it. Adding a photo field "while we're in here" ahead of R2.3 would be
exactly the kind of unrequested scope creep the parallel-execution-plan's cautions and the Stitch
mockup review (`docs/product/r2.2-mobile-mvp-mockups/README.md`) already flagged as a pattern to
actively guard against on this feature.

**Alternatives considered**: None seriously — this is a scope confirmation, not a design decision
with real trade-offs to weigh.

## R6 — Flutter consumes `packages/i18n`'s existing JSON catalogue, not a forked copy

**Decision**: The Flutter app bundles `packages/i18n/en.json` and `packages/i18n/ar.json` as raw
asset files (Flutter's standard `assets:` declaration in `pubspec.yaml`), loaded at runtime by a
small `I18nLoader` in `apps/mobile/lib/core/` that mirrors the flat key-lookup shape
`@ngx-translate/core` already uses on web (dotted keys, e.g. `requests.form.branchLabel`), rather
than generating Dart constants at build time. RTL (FR-013) is driven by Flutter's built-in
`Directionality`/`TextDirection.rtl`, switched from the same `ar` locale selection that already
picks the Arabic JSON file — no separate RTL flag to keep in sync. A string added to
`packages/i18n` for a web-only screen with no mobile equivalent is simply unused by mobile — no
attempt is made to keep the two catalogues' *coverage* identical, only their *source of truth*
identical (one file per language, never a forked mobile copy that could drift).

**Rationale**: A runtime asset read (rather than a Dart-constants codegen step) is the simpler of
the two options with no loss of correctness for this release's scale — Flutter's asset bundle
mechanism already gives compile-time verification that the files exist and ships them in the app
binary; a codegen step would add a build-pipeline dependency (when to regenerate, what CI step
enforces freshness) for a benefit — compile-time key-typo checking — that this codebase does not
yet have on the web side either (`@ngx-translate` is also a runtime string lookup, not statically
checked). Keeping parity with web's own actual rigor level, rather than over-building mobile's i18n
pipeline beyond what web itself has, is the appropriate scope here.

**Alternatives considered**:
- *Generate Dart constants from the JSON at build time.* Rejected for this release — real benefit
  (compile-time key checking) but adds a build step and a freshness-enforcement problem neither
  strictly required by spec.md's FR-013 nor matched by web's own current (runtime-checked) i18n
  rigor; worth reconsidering if a future release wants stronger guarantees, not a blocker now.
- *A separate, hand-maintained Flutter string catalogue.* Rejected directly by FR-013 ("drawn from
  the same shared string catalogue used on web — no mobile-only hardcoded copy") and by Principle
  VII, which requires every user-facing string to come from `packages/i18n`.
