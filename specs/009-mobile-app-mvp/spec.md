# Feature Specification: Mobile MVP

**Feature Branch**: `009-mobile-app-mvp`
**Created**: 2026-09-11
**Status**: Draft
**Input**: User description: "Release R2.2 Mobile MVP (Phase 2): the first mobile app release,
covering the three mobile-native jobs the roadmap scopes for it — Request and, read-only,
awareness of Approve — mobile shell (navigation, theming from shared design tokens), sign-in with
biometric re-entry, a role-aware home screen, branch request submission (catalogue search, lines,
quantity, required-by date, note — reusing R2.1's request/routing/budget-check/audit behaviour
unchanged, not reimplementing it), a lightweight low-stock report distinct from a full purchase
request, push notifications for request decisions, and offline-tolerant drafts with queued,
idempotent sync. Explicitly OUT of scope for this release, per the roadmap's own release split:
approving or rejecting a request from mobile, delivery confirmation and quality-issue reporting,
and the camera/barcode capture pipeline (shelf photo, barcode scan, damage photo) — all three are
R2.3 ('Mobile approvals + receipt'). Also out of scope, per the roadmap's permanent mobile
exclusions: quotation extraction review, match resolution, catalogue administration, basket
optimisation configuration, reporting builders, integration setup, and billing — desk tasks that
stay on web. Builds on R2.1's Requests + Approvals API and data model (008-requests-approvals)
without changing it; the only new backend surface is device push-token registration and the
low-stock report itself. Source: docs/roadmap/procurepilot_roadmap.md §7.2 (R2.2 release scope),
§12.1-12.4 (mobile strategic role, screen set, technical requirements)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in and land on a role-aware home (Priority: P1)

A member opens the mobile app for the first time and signs in with the same credentials they
already use on web. On every later launch, they unlock with their device's biometric (fingerprint
or face) instead of typing a password again. Once in, they land on a home screen that reflects
their role: a branch-scoped member sees "Request items" as the primary action; a member who also
holds an approver role additionally sees how many requests are currently waiting on their
decision — a number they can be aware of on the move, even though deciding on mobile is not part
of this release.

**Why this priority**: Nothing else in this release is reachable without it — the same role
mobile plays for every other story here that submission plays for R2.1's web workflow.

**Independent Test**: Can be fully tested by signing in on a fresh device, confirming biometric
re-entry works on the next app open without re-entering a password, and confirming the home
screen's primary action and (for an approver) pending count match the signed-in member's actual
role and branch scope.

**Acceptance Scenarios**:

1. **Given** a member with valid web credentials, **When** they sign in on the mobile app for the
   first time, **Then** they reach their role-aware home screen and are offered to enable
   biometric unlock for future launches.
2. **Given** a member who previously enabled biometric unlock, **When** they reopen the app,
   **Then** a successful biometric match takes them straight to their home screen without
   re-entering credentials.
3. **Given** a member holding an approver role with requests pending their decision, **When**
   they view their home screen, **Then** they see the count of pending requests, without any
   control to act on them from mobile.
4. **Given** an owner has revoked a member's session (already possible from web), **When** that
   member's device next opens the app, **Then** they are required to sign in again rather than
   being let through on a stale session.

---

### User Story 2 - Submit a purchase request from the branch floor (Priority: P1)

A branch manager standing in front of a shelf that needs restocking opens the app, searches the
branch's catalogue (or picks from recently requested items), adds one or more lines with
quantities, sets a required-by date, adds an optional note, and submits. The request enters the
exact same approval pipeline R2.1 already built — routing, budget check, and audit — unchanged;
mobile is a new way in, not a new decision path. They can also check back later and see its status
and, once decided, the approver's comment, the same way they already can on web.

**Why this priority**: This is the job mobile exists for — the roadmap's own words are "a branch
manager standing in front of an empty shelf." Sign-in (Story 1) is the prerequisite; this is the
first thing worth reaching it for.

**Independent Test**: Can be fully tested by a signed-in branch manager creating a request naming
one or more lines and a required-by date, submitting it, and confirming it appears with status
"submitted" in their own request list on mobile — and, independently, that the same request is
visible and correctly routed in the existing R2.1 web approval queue, proving mobile submission is
not a second, divergent code path.

**Acceptance Scenarios**:

1. **Given** a signed-in branch manager on the request screen, **When** they search the catalogue,
   add a line with a quantity, set a required-by date, and submit, **Then** the request is created
   with status "submitted," using the same routing and budget-check behaviour as a web submission.
2. **Given** a request still in progress, **When** the branch manager leaves the screen without
   submitting, **Then** it persists as a draft they can return to and finish later.
3. **Given** a request they previously submitted from mobile, **When** they open their request
   list, **Then** they see its current status, and once decided, the approver's comment — matching
   exactly what they would see on web for the same request.
4. **Given** a request with no lines, **When** the branch manager attempts to submit, **Then** the
   app refuses submission, the same rule R2.1 already enforces.

---

### User Story 3 - Report low stock in one tap (Priority: P2)

A branch manager notices a product is running low but isn't ready to commit to a full purchase
request yet — they just want to flag it. They tap "running low" on that product, optionally add a
count of what's left, and it's logged as a demand signal — distinct from, and much faster than,
building a full request.

**Why this priority**: It's a named mobile-native job in its own right (a lighter-weight sibling
to full request submission, per the roadmap's screen set), but the workflow is fully useful
without it — Stories 1-2 already deliver the core request loop.

**Independent Test**: Can be fully tested by a signed-in branch manager tapping "running low" on a
product with and without an optional count, and confirming each is recorded as a low-stock report
attributed to that member, branch, and product — without creating or affecting any purchase
request.

**Acceptance Scenarios**:

1. **Given** a signed-in branch manager viewing a product, **When** they tap "running low" with no
   count entered, **Then** a low-stock report is recorded for that product, branch, and member.
2. **Given** the same action, **When** they enter an optional count first, **Then** the report
   records that count alongside the signal.
3. **Given** a low-stock report has just been submitted, **When** the branch manager checks the
   product again, **Then** nothing about a purchase request has been created or changed — the
   report is informational, not a request.

---

### User Story 4 - Stay informed without opening the app (Priority: P2)

A member who submitted a request from mobile (or from web) gets a push notification on their
phone the moment it's approved or rejected, without needing to have the app open or check email.
Tapping the notification takes them straight to that request's status.

**Why this priority**: It closes the loop Story 2 opens — a requester who has to remember to check
back is a materially worse experience than one who is told — but the request loop itself already
works without it.

**Independent Test**: Can be fully tested by a signed-in member with notifications enabled having
one of their submitted requests approved or rejected, and confirming a push notification arrives
and deep-links into that request's status screen.

**Acceptance Scenarios**:

1. **Given** a member has granted notification permission, **When** a request they submitted is
   approved or rejected, **Then** they receive a push notification naming the request and its new
   status.
2. **Given** that notification, **When** the member taps it, **Then** the app opens directly to
   that request's status view.
3. **Given** a member has declined notification permission, **When** one of their requests is
   decided, **Then** no push arrives, but the outcome is still visible the next time they open the
   app and check their request list — the feature degrades, it does not break anything else.

---

### User Story 5 - Keep working with a weak or no connection (Priority: P3)

A branch manager is in a stockroom with no signal. They can still open the app, build a request or
a low-stock report, and submit it — the app queues it locally and sends it automatically the
moment connectivity returns, without the manager having to remember to retry or risk it going
through twice.

**Why this priority**: Genuinely useful and specific to the mobile context (a desk-bound web user
rarely loses connectivity mid-task), but Stories 1-4 already deliver full value on a normal
connection — this is resilience, not new capability.

**Independent Test**: Can be fully tested by putting the device in airplane mode, building and
submitting a request or low-stock report, confirming it shows as queued/pending rather than
failed, then restoring connectivity and confirming it completes exactly once with no duplicate.

**Acceptance Scenarios**:

1. **Given** no network connectivity, **When** a branch manager builds a request, **Then** it
   saves as a local draft exactly as it would with connectivity.
2. **Given** no connectivity, **When** the branch manager submits that draft, **Then** the app
   marks it as queued rather than claiming it succeeded, and does not lose it if the app is closed.
3. **Given** a queued submission, **When** connectivity returns, **Then** it is sent automatically
   and the member is shown its real outcome — without any further action from them.
4. **Given** a queued submission that is retried after a partial failure (e.g., the request was
   received but the confirmation was not), **When** it is resent, **Then** it does not create a
   duplicate request — the same submission is recognized and not repeated.

---

### Edge Cases

- What happens when a member's device does not support biometrics, or they have none enrolled?
  They sign in with credentials every time, the same as web — biometric unlock is an enhancement,
  never a requirement to use the app.
- What happens if a member uninstalls and reinstalls the app, or signs in on a new device? Their
  previous device's push registration goes stale; the app registers a new one on next sign-in, and
  a notification is never expected to reach a device that no longer has the app installed.
- What happens to a request drafted offline if the member never returns to finish it? It stays a
  local draft indefinitely, the same as an unfinished draft on web — nothing forces completion.
- Does this release put photo attachment, barcode scanning, or any camera capability on mobile? No
  — per the roadmap's own release split, the camera/barcode capture pipeline (shelf photo for
  requests, barcode scan, delivery/damage photo) belongs to R2.3 alongside approvals and delivery
  confirmation, not this release. A request submitted from mobile in this release carries the same
  fields a web request does today, with photo attachment coming later.
- Can an approver decide on a request from mobile in this release? No — mobile surfaces only a
  read-only count of pending decisions (Story 1); the approve/reject action itself is R2.3. A push
  notification is sent to the *requester* when their request is decided (Story 4), not to prompt an
  *approver* to decide, since there is nowhere on mobile yet for them to act on it.
- What happens when the same low-stock report is tapped twice in quick succession (e.g., a
  double-tap)? It is treated as one report, not two — the interaction is a single signal, not a
  running tally the member is expected to manage duplicates on.
- What happens when a member's role or branch assignment changes while they are signed in on
  mobile (e.g., an owner reassigns their branch)? The app reflects the new scope the next time it
  syncs with the server — the same "current role wins" behaviour R2.1 already has on web, not a
  mobile-specific rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The mobile app MUST authenticate a member with the same credentials used on web, and
  MUST offer biometric re-entry (where the device supports it) so a member is not required to
  re-enter credentials on every launch.
- **FR-002**: The mobile app MUST present a role-aware home screen on sign-in: a branch-scoped
  member sees a primary "request items" action; a member holding an approver role additionally
  sees a count of requests currently pending their decision, without any control to act on them.
- **FR-003**: The mobile app MUST let a member search their branch's product catalogue, build a
  purchase request (one or more lines with quantity and an optional note, a required-by date),
  save it as a draft, and submit it — using R2.1's existing request creation, threshold routing,
  delegation, budget-check, and audit behaviour unchanged; mobile submission MUST NOT introduce a
  second, divergent decision path.
- **FR-004**: The mobile app MUST reject submission of a request with zero lines, the same rule
  already enforced on web (FR-003, 008-requests-approvals).
- **FR-005**: The mobile app MUST let a member view the status of requests they have submitted
  (from either mobile or web) — draft, submitted, approved, rejected, or withdrawn — and, once
  decided, the approver's comment, matching exactly what is already visible on web.
- **FR-006**: The mobile app MUST let a member record a low-stock report for a product — a
  lighter-weight, optional-count "running low" signal distinct from a purchase request — without
  that report itself creating, modifying, or committing to any purchase request.
- **FR-007**: The system MUST register a signed-in member's device for push notifications (subject
  to the member granting notification permission) and MUST send a notification when a request they
  submitted is approved or rejected, deep-linking directly into that request's status view.
- **FR-008**: The mobile app MUST continue to function fully — including a member seeing decision
  outcomes by opening the app and checking their request list — for a member who has declined
  notification permission; push notifications are an enhancement, not a requirement to use the app.
- **FR-009**: The mobile app MUST NOT surface an approve/reject action anywhere on mobile in this
  release; the read-only pending count (FR-002) is the only approval-related surface this release
  ships, consistent with the roadmap scoping the approval decision itself to R2.3.
- **FR-010**: The mobile app MUST let a member continue building or editing a draft request while
  offline, persisting it locally on the device without requiring connectivity.
- **FR-011**: The system MUST queue a request or low-stock report submitted while offline and
  submit it automatically once connectivity returns, without creating a duplicate if the same
  queued submission is retried after a partial failure.
- **FR-012**: The mobile app MUST show a member a clear, truthful indicator of whether a draft or a
  queued submission has actually reached the server, and MUST NOT report a submission as
  successful before it has — a member must never be left uncertain, or wrongly reassured, about
  whether an action went through.
- **FR-013**: The mobile app MUST support English and Arabic, with full right-to-left layout in
  Arabic, drawn from the same shared string catalogue used on web — no mobile-only hardcoded
  copy.
- **FR-014**: The system MUST let a member's session be revoked remotely (already possible from
  web) and MUST require the mobile app to re-authenticate on that device the next time it is
  opened after revocation, rather than continuing on a stale session.
- **FR-015**: The mobile app MUST scope every screen to the signed-in member's role and branch
  assignment exactly as R2.1's web screens already are: a branch-scoped member sees and can act on
  only their own branch's requests; an owner sees everything in the tenant.
- **FR-016**: The system MUST record every mobile-originated request submission and every
  low-stock report in the existing append-only audit log, on the same terms as every other
  administrative action in the product — the audit trail MUST NOT have a gap for "submitted from
  mobile."

### Key Entities

- **Purchase Request / Purchase Request Line**: Reused unchanged from 008-requests-approvals —
  mobile is a new way to create and view them, not a new definition of what they are.
- **Low-Stock Report**: A branch manager's quick "running low" signal for a product at their
  branch, with an optional count, attributed to the member and moment it was raised. Informational
  only — it does not create, modify, or commit to a purchase request, and carries no approval or
  routing of its own.
- **Device Registration**: A signed-in member's mobile device registered to receive push
  notifications — enough to identify which device(s) to notify and to stop notifying a device once
  it is no longer current (reinstalled, signed out, or superseded by a newer registration).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A branch manager can go from opening the app to a submitted request in under 2
  minutes on a normal connection.
- **SC-002**: A branch manager can record a low-stock report in under 15 seconds (one tap, plus an
  optional count).
- **SC-003**: 100% of requests submitted from mobile appear correctly routed in the existing web
  approval queue, and 100% of their status/comment updates are visible identically on both mobile
  and web — no channel-specific behaviour gap.
- **SC-004**: A member with notifications enabled learns their request was decided without opening
  the app, for 100% of decisions on requests they submitted.
- **SC-005**: Zero requests or low-stock reports submitted while offline are lost or duplicated —
  each one that was genuinely submitted completes exactly once once connectivity returns.
- **SC-006**: A member is never shown a false "submitted successfully" state for something that has
  not actually reached the server — 100% of success indicators reflect confirmed server state.
