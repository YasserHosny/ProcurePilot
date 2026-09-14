# Feature Specification: Reporting and Hardening

**Feature Branch**: `012-reporting-hardening`
**Created**: 2026-09-14
**Status**: Draft
**Input**: Roadmap R2.5 (M14 – M15): "Scheduled reports, digests, exports, performance tuning,
accessibility pass, security review". Roadmap §7.1 Phase 2 workflow scope: "Scheduled reports and
email digests". Roadmap §10.8: third-party penetration test before general availability (end of
Phase 2). R2.5 is the final Phase 2 release before the G2 gate.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive scheduled reports without asking (Priority: P1)

An owner or buyer configures a weekly report schedule for savings, supplier spend, or alert
activity. On the chosen weekday, in the workspace's reporting timezone, ProcurePilot generates the
report as a workspace-scoped artifact, lists it in a Reports center with its period, row count,
rule version, and applied filters, and serves it for download through an expiring, audited link.
No one has to remember to pull numbers before a meeting.

**Why this priority**: "Scheduled reports" is the first named R2.5 scope item. The savings ledger
already proves the value of exported evidence; scheduling removes the manual step between
existence and delivery.

**Independent Test**: Seed a workspace with verified savings, purchase records, and alert
conditions. Create a weekly schedule with a due date in the past. Run the scheduler once. Verify
exactly one artifact exists for that schedule and period, its rows match the seeded source data
with explicit currencies, its download link works, and a second scheduler run does not duplicate
the artifact.

**Acceptance Scenarios**:

1. **Given** a weekly savings-ledger schedule for Mondays, **When** the scheduler runs after a
   Monday due time in the workspace reporting timezone, **Then** one artifact covering the prior
   week appears in the Reports center with period, row count, rule version, and currency-explicit
   values.
2. **Given** a completed artifact, **When** a member downloads it, **Then** the download resolves
   through an authenticated, expiring link and the download is recorded as an audit event.
3. **Given** the same schedule and period are processed twice, **When** the second run completes,
   **Then** no duplicate artifact is created; the run is idempotent per schedule and period.
4. **Given** a schedule owner pauses the schedule, **When** the next due time passes, **Then** no
   artifact is generated and the paused state is visible in the Reports center.

---

### User Story 2 - Act on a weekly digest (Priority: P2)

A member subscribes to a weekly digest. Each week ProcurePilot assembles a short, action-oriented
summary: verified savings recorded that week, new anomalies detected, and offers whose validity
expires within seven days. Each item links to the place where the member acts on it. The digest is
delivered by email when the workspace has email delivery configured, and is always available
in-app with its delivery status shown honestly.

**Why this priority**: "Digests" is the second named R2.5 scope item and the roadmap's §7.1 names
"email digests" explicitly. The digest is the retention surface that pulls members back to the
workflow between sessions.

**Independent Test**: Seed a week of verified savings, anomaly conditions, and offers expiring
within seven days. Trigger the digest for one subscription. Verify every digest section matches
the seeded records, every item carries a deep link, the delivery attempt is audited, and when no
email provider is configured the digest is still readable in-app with an explicit
"email not configured" status.

**Acceptance Scenarios**:

1. **Given** two verified savings recorded in the last seven days, **When** the digest renders,
   **Then** the digest shows the weekly total with currency and links each saving to its evidence.
2. **Given** a new price-spike anomaly, **When** the digest renders, **Then** the digest lists it
   with severity and links to the alerts inbox.
3. **Given** email delivery is not configured, **When** the member opens digest settings, **Then**
   the settings show that email is not configured, the digest is available in-app, and no failure
   is silently swallowed.
4. **Given** an email delivery attempt fails, **When** the attempt is recorded, **Then** the
   subscription shows the failed status with the failure time and the attempt is audited.

---

### User Story 3 - Trust export behaviour under load and locale (Priority: P2)

A buyer exports the savings ledger, supplier spend, or alert activity as CSV or XLSX, optionally
filtered by branch, and receives a complete file or a clear refusal — never a truncated sheet or a
hanging job. Arabic-language workspaces receive PDF and XLSX reports with correct labels and
right-to-left layout. Old artifacts disappear when they expire, and their deletion is recorded.

**Why this priority**: "Exports" is the third named R2.5 scope item. Wave 15's baseline audit found
concrete defects on `main`: the documented `GET /exports/{id}/download` endpoint is not
implemented, the branch filter is refused, CSV is missing, PDF rendering uses Helvetica which
cannot render Arabic, and renderer labels are hardcoded English strings outside `packages/i18n`.

**Independent Test**: Request an export of each kind in each supported format, in both English and
Arabic locales, with and without a branch filter. Request an export over the row cap. Verify
completed files download correctly, over-cap requests return a structured refusal, Arabic PDFs
render legible right-to-left text with catalogue labels, and expired artifacts are purged with an
audit event.

**Acceptance Scenarios**:

1. **Given** a completed export, **When** the member follows its download URL, **Then** the file
   downloads with the correct content type and the URL expires after its configured lifetime.
2. **Given** a request for more rows than the export row cap, **When** the request is submitted,
   **Then** it is refused with a structured error naming the cap, and no partial file is produced.
3. **Given** the workspace locale is Arabic, **When** a PDF report renders, **Then** all labels
   come from the shared catalogue and the layout is right-to-left with an Arabic-capable font.
4. **Given** an artifact older than the retention window, **When** the retention pass runs, **Then**
   the stored file is removed and the purge is audited.

---

### User Story 4 - Feel the app stay fast and accessible (Priority: P2)

A buyer uses the full app — reports included — and it stays fast and usable. The initial bundle
returns inside its budget, component styles stay inside theirs, the compare grid recalculates in
under 150 ms, and every mandatory screen passes automated accessibility checks in English and
Arabic, including keyboard-only operation of the Reports center.

**Why this priority**: "Performance tuning" and "accessibility pass" are named R2.5 scope items and
the constitution's quality gates already set the thresholds (compare grid < 150 ms; WCAG 2.1 AA,
automated axe-core scan clean). Wave 15's baseline measured the current app at 588.35 kB initial
bundle against a 500 kB budget, with nine component style budgets exceeded — hardening must close
measured regressions, not invent new aspirations.

**Independent Test**: Build the web app and run the accessibility and performance suites. Verify
the initial bundle is at or under 500 kB raw, no component style budget warning remains, the
compare-grid recalculation regression test passes under 150 ms, and axe-core reports zero
violations on every mandatory surface in both locales.

**Acceptance Scenarios**:

1. **Given** the production build, **When** it completes, **Then** the initial bundle is at or
   under the 500 kB budget and zero budget warnings remain.
2. **Given** the compare grid with a seeded basket, **When** quantity changes, **Then** the
   recalculation completes in under 150 ms as asserted by an automated regression test.
3. **Given** the Reports center, **When** a keyboard-only user navigates it, **Then** every action
   is reachable and focus order is logical in both left-to-right and right-to-left layouts.

---

### User Story 5 - Pass the pre-G2 security review (Priority: P2)

The team responsible for release runs the security review the roadmap requires before general
availability: dependency audits run in CI on every pull request, the reporting and digest surfaces
are reviewed against the tenant-isolation and service-role checklist, new endpoints are rate
limited, and a third-party penetration test is scoped and ready to procure.

**Why this priority**: "Security review" is the last named R2.5 scope item, and roadmap §10.8
schedules a third-party penetration test before general availability. R2.5 produces the evidence
and the procurement-ready scope; the test itself is a separate engagement.

**Independent Test**: Open a pull request and verify the dependency audit job runs and blocks on
high-severity findings. Execute the security review checklist against the R2.5 code and verify
every item is recorded as passed or carries a documented, owned exception. Verify the penetration
test scope document exists and names every in-scope surface.

**Acceptance Scenarios**:

1. **Given** a pull request introducing a dependency with a known high-severity vulnerability,
   **When** CI runs, **Then** the dependency audit job fails the verdict.
2. **Given** the R2.5 reporting and digest endpoints, **When** the security checklist is executed,
   **Then** row-level security, tenant pinning in workers, signed-URL expiry, and rate limits are
   each verified and recorded.
3. **Given** the pre-GA penetration test requirement, **When** release planning needs it, **Then**
   a scope document exists listing in-scope surfaces, data classifications, and test boundaries.

### Edge Cases

- If a scheduled run's source data is empty for the period, the artifact must still be generated
  with row count zero and an explicit empty-state label, not skipped silently.
- If the workspace timezone is invalid or missing, schedules run in UTC and the Reports center
  shows which timezone was used.
- If two scheduler instances race, exactly one must enqueue each due run; the loser must observe
  the claim and skip without error.
- If a worker crashes mid-generation, the run must be retried within the same period without
  producing a half-written artifact visible as completed.
- If an export request exceeds the row cap, the refusal must name the cap and the actual row
  count, and must not create a storage object.
- If a digest subscriber's membership is removed or suspended, the subscription must stop
  delivering and the next scheduler run must skip it without error.
- If a report schedule's creating membership is deactivated, the schedule must continue as a
  workspace asset under tenant authority, editable by any owner or buyer, with the creator
  preserved for provenance.
- If email delivery is unconfigured, unreachable, or refuses the message, the in-app digest and
  the explicit failure status must remain available and audited.
- If an artifact's retention window passes while a member holds an unexpired download link, the
  link must fail as not found after purge, never as a cross-tenant or stale-content response.
- If a cross-tenant schedule, artifact, export job, or digest subscription id is requested, the
  response must be not found, never forbidden.
- If a report or digest is requested for a branch the caller cannot see, the request must resolve
  as not found or be refused with a validation error, never silently return another branch's rows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide report schedules with kind, format, filters (period, supplier,
  branch), weekly cadence, weekday, status (active or paused), and next-run time, creatable and
  editable by owners and buyers.
- **FR-002**: System MUST support report kinds `savings_ledger`, `spend_by_supplier`, and
  `alerts_summary`, each with a declared set of supported formats: CSV and XLSX for all kinds;
  PDF additionally for `savings_ledger` and `alerts_summary`. Each kind MUST declare its column
  schema — human-readable business identifiers (supplier name, product name, branch name,
  PO or reference number), never bare UUIDs — and spend aggregation MUST group by currency and
  MUST NOT sum across currencies.
- **FR-003**: System MUST generate scheduled artifacts in the workspace's reporting timezone
  (IANA name, default UTC, owner-editable), covering the prior complete period window.
- **FR-004**: System MUST list artifacts and export jobs in one cursor-paginated Reports surface
  carrying kind, format, filters snapshot, period, status, row count, rule version, source
  schedule id where applicable, and created, started, and completed timestamps. The listing MUST
  filter by the caller's authorized branches: branch-scoped roles MUST NOT see artifacts whose
  filters include branches they cannot see.
- **FR-005**: System MUST serve artifact downloads through an authenticated endpoint that returns
  an expiring signed URL, records a download audit event, and returns not found for cross-tenant
  or expired artifacts. The download MUST additionally verify the caller's branch visibility
  against the artifact's branch filter, resolving as not found when unauthorised. The
  documented-but-unimplemented `GET /api/v1/exports/{id}/download` endpoint on `main` MUST be
  delivered by this feature.
- **FR-006**: System MUST make scheduled generation idempotent per schedule and period: a repeated
  or raced scheduler pass MUST NOT produce a duplicate artifact.
- **FR-007**: System MUST run scheduled generation and digest delivery in workers without a
  member JWT, treating queue payloads as untrusted hints: the worker MUST load the owning row by
  id, re-derive the tenant scope (and membership or branch scope where relevant) from the
  database row inside the transaction, and refuse mismatches before any read, render, upload, or
  audit. Reader functions MUST be authorization-pinned — validating the effective membership and
  branch visibility — not merely tenant-pinned. Each generation and delivery attempt MUST be
  recorded as an audit event.
- **FR-008**: System MUST provide per-member digest subscriptions with kind, optional branch
  filter, channel, status, next-run time, and last delivery outcome. New memberships MUST be
  provisioned with one active weekly digest subscription (in-app channel, or email when the
  workspace has email configured), disclosed in the invitation flow with one-click pause.
- **FR-009**: System MUST render the weekly digest with verified savings in the hero position
  (explicit currency), followed by actionable backlog sections — purchase outcomes pending
  verification and purchase requests awaiting the subscriber's approval — then new anomalies
  detected in the period, then offers whose validity ends within seven days, with every item
  carrying a deep link into the acting surface. No section may present history without an
  available action.
- **FR-010**: System MUST deliver digests by email through an environment-configured SMTP provider
  when configured, and MUST expose the digest in-app regardless, with an explicit
  "email not configured" status when the provider is absent. Digest email MUST be multipart (HTML
  and plain text), MUST set direction and language attributes per locale with email-safe fonts,
  and MUST carry standard List-Unsubscribe headers plus a footer link to digest settings.
- **FR-011**: System MUST record every digest delivery attempt with outcome, timestamp, and error
  detail where present, audited append-only. Each audit action across this feature MUST carry its
  mandatory payload fields: actor membership for member actions and an explicit system-actor
  marker for worker actions, trace or correlation id, source schedule or subscription id, period
  window, filters digest, row count, storage path reference, and outcome-specific detail
  (signed-URL TTL, delivery response class, purge reason, schedule state transition).
- **FR-012**: System MUST support the CSV format for every export kind and MUST support the branch
  filter that today returns `unsupported_in_phase_1`.
- **FR-013**: System MUST cap export row counts at a configured maximum (default 10,000) and
  refuse over-cap requests with a structured error naming the cap and actual count.
- **FR-014**: System MUST purge stored artifacts after a configurable retention window (default
  90 days) and record each purge as an audit event. Artifact rows MUST carry immutable schedule
  and filter snapshots so replay survives schedule deletion, and purging MUST invalidate
  previously issued download links.
- **FR-015**: System MUST render report labels and headings from the shared `packages/i18n`
  catalogues (English and Arabic) — no hardcoded user-facing strings in renderers — with CSV
  output prefixed by a UTF-8 BOM for Excel compatibility, empty exports rendering full report
  header metadata (workspace, kind, filters, period, timestamp, rule version) rather than a bare
  sentence, PDFs using structured table layouts with page headers, and Arabic PDFs passing
  through an explicit shaping pipeline (Arabic glyph reshaping and bidirectional reordering)
  before drawing, right-to-left, with an Arabic-capable embedded font. Evidence references in
  artifacts MUST be human-usable web links, not internal API paths.
- **FR-016**: System MUST express every monetary value in reports, digests, and exports as amount
  with explicit currency, and MUST carry rule version and filter snapshots in every artifact
  metadata for replay.
- **FR-017**: System MUST keep reporting and digests advisory: no endpoint or worker in this
  feature may create a purchase, approval, order, payment, or supplier message.
- **FR-018**: System MUST enforce database RLS on every new tenant-scoped table with `ENABLE` and
  `FORCE` row-level security and policies supplying both `USING` and `WITH CHECK`, and MUST
  resolve tenant scope for API requests only from the verified JWT claim.
- **FR-019**: System MUST return not found, never forbidden, for cross-tenant schedule, artifact,
  export job, and digest subscription references.
- **FR-020**: System MUST rate limit export creation, schedule mutations, and digest subscription
  mutations, keyed by the verified tenant and membership claims (IP only as fallback), MUST cap
  active schedules and digest subscriptions per member, and MUST return structured 429 responses
  without queuing work.
- **FR-021**: System MUST run dependency vulnerability audits (Python and JavaScript) as a
  blocking CI job on every pull request.
- **FR-022**: System MUST produce a recorded security review covering RLS on new tables, worker
  tenant pinning, signed-URL expiry, storage bucket policy, rate limits, and secret handling, with
  every failed item owned and tracked.
- **FR-023**: System MUST produce a third-party penetration-test scope document naming in-scope
  surfaces, data classifications, environment, and boundaries, ready for procurement.
- **FR-024**: System MUST bring the web production build inside its budgets: initial bundle at or
  under 500 kB raw and zero component style budget warnings.
- **FR-025**: System MUST add an automated regression test asserting compare-grid recalculation
  under 150 ms.
- **FR-026**: System MUST pass automated WCAG 2.1 AA checks with zero violations on the mandatory
  surfaces — sign-in, dashboard, compare, basket split, alerts inbox, supplier scorecard, savings
  ledger, approval queue, and the new Reports center and digest settings — in English and Arabic.
- **FR-027**: System MUST support keyboard-only operation of the Reports center and digest
  settings with logical focus order in both layout directions.
- **FR-028**: System MUST serve all new web UI strings from `packages/i18n` in English and Arabic
  with layout using CSS logical properties.
- **FR-029**: System MUST record the rendering locale on every report schedule and export job,
  defaulting to the requesting member's preferred locale, and MUST expose it in the Reports
  surface so members can identify an artifact's language before download.

### Key Entities *(include if feature involves data)*

- **ReportSchedule**: A tenant-scoped, member-owned recurring report definition: kind, format,
  filters, weekly cadence and weekday, active or paused status, and next-run time.
- **ReportArtifact / ExportJob (extended)**: The durable job-and-artifact record for one
  generation — on demand or scheduled — carrying filters snapshot, period, status, row count,
  storage location, rule version, expiry, and timestamps.
- **DigestSubscription**: A tenant-scoped per-member weekly digest definition: optional branch
  filter, channel, status, next-run time, and last delivery outcome.
- **DigestDelivery**: The append-only record of each delivery attempt for a subscription: outcome,
  timestamp, and error detail.
- **TenantReportingTimezone**: The workspace-level IANA timezone that anchors schedule and digest
  run windows.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For seeded weekly schedules, one scheduler pass produces exactly one artifact per
  due schedule with correct period window, row count, rule version, and currency-explicit values;
  a repeated pass produces no duplicate.
- **SC-002**: Cross-tenant schedule, artifact, export job, and digest subscription ids return not
  found through the API, and worker queries are tenant-pinned by construction — verified by an
  isolation test that runs with the reporting tables present.
- **SC-003**: Digest content matches seeded weekly source records exactly; every item deep-links;
  delivery attempts (success, failure, and unconfigured) are audited; the in-app digest renders
  with an explicit status when email is not configured.
- **SC-004**: An export of 10,000 rows completes within 60 seconds in the worker test; an
  over-cap request is refused with a structured error and produces no storage object.
- **SC-005**: The web production build reports the initial bundle at or under 500 kB raw with zero
  budget warnings of any kind.
- **SC-006**: The compare-grid recalculation regression test asserts completion under 150 ms and
  passes in CI.
- **SC-007**: Automated accessibility checks report zero WCAG 2.1 AA violations on every mandatory
  surface in English and Arabic, and the keyboard-only Reports center journey passes in both
  directions.
- **SC-008**: The dependency audit CI job runs on pull requests and fails on high-severity
  findings; the recorded security review has no open red items; the penetration-test scope
  document exists.
- **SC-009**: Artifacts past the retention window are purged with their purge audited, and their
  download links subsequently resolve as not found.
- **SC-010**: No R2.5 endpoint, worker, or UI path can execute or imply autonomous purchasing.

## Assumptions

- Email delivery uses a provider-agnostic SMTP configuration (host, port, credentials, sender)
  held in environment variables; no vendor SDK is introduced, and no tenant-specific sender
  addresses are supported in R2.5.
- The third-party penetration test itself is out of scope and out of budget for R2.5; this feature
  delivers its procurement-ready scope document only.
- `alerts_summary` and digest anomaly sections are computed from live alert conditions at
  generation time, consistent with R2.4's dismissal-only alert model; no alert rows are persisted
  by reporting.
- Product telemetry for the G2 gate (workflow origination, mobile adoption, retention) is measured
  by the existing telemetry pipeline, not by reporting code; R2.5 does not add a telemetry product.
- The existing `openpyxl` and `reportlab` dependencies remain the rendering stack; Arabic support
  additionally requires Arabic glyph reshaping and bidirectional-reordering libraries (for
  example `arabic-reshaper` and `python-bidi`) alongside the embedded open-license font — font
  embedding alone does not shape Arabic script.
- The existing `export_job` table remains the single job-and-artifact record; scheduled runs extend
  it rather than creating a parallel table, per its own migration comment.
- Bundle-size reduction uses route-level lazy loading of existing feature areas; no feature is
  removed to meet the budget.
