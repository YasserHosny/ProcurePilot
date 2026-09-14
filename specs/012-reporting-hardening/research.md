# Phase 0 Research: Reporting and Hardening

Wave 15 required five scope ambiguities to be resolved before tasks were written. They are
resolved below (R1 – R5) from the roadmap's own text plus the Wave 15 code audit; each decision
cites its evidence. The remaining decisions (R6 – R12) cover the design choices the tasks depend
on.

## R1 - Scheduled report delivery model (ambiguity 1)

**Decision**: A combination. Scheduled reports generate downloadable tenant-scoped artifacts
surfaced in an in-app Reports center; on-demand exports remain; digests add email as the only
push channel (R3). There is no email attachment of full reports and no in-app-only scheduling.

**Rationale**: Roadmap §7.1 names "Scheduled reports and email digests" as one line — reports are
the artifacts, digests are the email. The experience-layer diagram (§10.2) lists "Email digests ·
Scheduled reports" as separate surfaces. Attaching full XLSX/PDF reports to email would multiply
the secret-handling and tenant-isolation surface of email delivery for no roadmap-mandated value,
and the Reports center already needs to exist to make schedules inspectable (pause, evidence,
history). Email stays narrow: short digests with deep links.

## R2 - Report formats per kind (ambiguity 2)

**Decision**: CSV is added for every kind. XLSX remains for every kind. PDF is supported only
where a printable template exists: `savings_ledger` (already implemented) and `alerts_summary`
(new). `spend_by_supplier` is CSV/XLSX only.

**Rationale**: The roadmap's R1.5 line already shipped "exports (Excel/PDF)" and the current
implementation supports `xlsx` and `pdf` for `savings_ledger`; CSV is the natural machine-readable
addition for customers feeding their own tooling, at trivial renderer cost. PDF templates are the
expensive part (fonts, layout, RTL), so they are limited to the two kinds with document-shaped
output. The kind-format matrix is declared once in the OpenAPI contract and enforced server-side.

## R3 - Digest scope and channel (ambiguity 3)

**Decision**: Digests are per-member subscriptions (not tenant-wide, not per-branch, not
role-scoped by configuration). One kind in R2.5: the weekly digest. Content is computed from
tenant data the member's own role already permits, with an optional branch filter. Channel:
email through environment-configured SMTP when configured; the digest is additionally rendered
in-app, and unconfigured email shows an explicit status.

**Rationale**: A tenant-wide digest pushes the same content to owners and branch buyers, which
either leaks summary data to narrower roles or flattens the content to the lowest common
denominator. Per-member subscriptions with the member's own RLS-visible data keep the
authorisation model unchanged — the worker renders what the member could query themselves.
Per-branch and per-role variants are additive filter work later; R2.5 ships the weekly cadence
the roadmap names, and monthly/other cadences are deliberately excluded to keep the scheduler
honest.

## R4 - Scheduling mechanism and idempotency

**Decision**: A single-instance scheduler entrypoint (`procurepilot_api.workers.report_scheduler`)
ticks on a short interval, selects due `report_schedule` and `digest_subscription` rows with
`FOR UPDATE SKIP LOCKED` on the claim, and enqueues RQ jobs for the existing queues. Runs are
idempotent per (schedule, period): the enqueued job carries a deterministic job id
(`schedule:{id}:{period_start}`), and `export_job` gains a unique index on
`(tenant_id, schedule_id, filters->>'period_start')` so a repeat pass cannot create a duplicate
artifact. Next-run times advance inside the same claimed transaction.

**Rationale**: RQ has no first-class cron that is also auditable and replayable against the job
table; a database-driven due-list keeps the schedule state in Postgres (survives Redis restarts),
keeps the claim race-free without a lock library, and matches the roadmap's "Background jobs | RQ
| Extraction, matching, refresh, digests" topology. At-least-once enqueue plus per-period
uniqueness is the same pattern the codebase already uses for idempotency keys.

## R5 - Worker tenant pinning and the service-role boundary

**Decision**: Scheduled runs and digest delivery execute without a member JWT using the
service-role connection, and every query is pinned to the owning tenant by an explicit
`tenant_id` parameter — the same pattern as `record_audit_event` (migration `0007`) and
`accept_member_invitation` (migration `0009`), which exist precisely because RLS cannot admit a
claimless caller. Tenant-pinned reader functions for savings, purchases, alert conditions, and
validity windows are SECURITY DEFINER functions taking `tenant_id` (plus period/branch/supplier
filters), owned by the migrations with `SET search_path`. The isolation test gains cases that
call these functions with tenant A and assert tenant B rows are invisible.

**Rationale**: The alternative — minting member-impersonating JWTs inside workers — couples
scheduling to session semantics and widens the audit story. Parameter-pinned functions keep the
boundary explicit, reviewable in one migration, and testable. This is the highest-risk decision in
R2.5 and is therefore retained on the orchestrator lane (see tasks.md Delegation lanes).

## R6 - The missing download endpoint (Wave 15 audit finding)

**Decision**: Implement `GET /api/v1/exports/{id}/download` as part of R2.5, returning an expiring
signed URL (or streaming the object) after an authenticated, RLS-visible job lookup, with a
`reports.artifact_downloaded` audit event. Signed-URL TTL is environment-configured with a safe
default.

**Rationale**: `storage.py` on `main` already returns `/api/v1/exports/{job_id}/download` as the
`download_url` and `docs/architecture/api-specification.md` §exports documents it, but no such
route exists in the exports router (verified in Wave 15: the only download route in the api is
`GET /documents/{id}/download`). Completed exports currently advertise a link that 404s. Fixing a
documented-but-missing endpoint is hardening, not new scope.

## R7 - Email delivery design

**Decision**: Provider-agnostic SMTP (host, port, username, password, sender address, TLS mode)
read from environment settings; a minimal SMTP client in the digest worker; per-attempt outcome
recorded on the subscription and in `audit_event`. No vendor SDK, no per-tenant senders, no
attachments — deep links only. When SMTP is unconfigured, subscriptions remain active, the digest
renders in-app, and settings show "email not configured" explicitly.

**Rationale**: The constitution's Principle I requires explicit honesty over silent failure, and
the Wave 15 security critique flagged secret-handling as the main email risk. A provider-agnostic
client keeps secrets in the environment (gitleaks scope unchanged), avoids a new dependency, and
lets each environment choose its relay. Attachments are excluded deliberately (R1).

## R8 - Renderer labels, Arabic PDF, and print

**Decision**: All renderer and digest strings come from `packages/i18n` `en.json`/`ar.json` — the
api loads the catalogue files at runtime (new `shared/i18n.py`), keyed by the tenant's or
recipient's preferred locale. Arabic PDFs embed an Arabic-capable open-license font (Noto Naskh
Arabic or equivalent OFL font, committed under a licence-checking path) and draw right-to-left
layout; the current Helvetica usage remains only for Latin locales. The web Reports center uses
CSS logical properties and a print stylesheet that works in both directions.

**Rationale**: AGENTS.md non-negotiable 5 ("every user-facing string comes from `packages/i18n`")
applies to rendered documents, not only to the SPA; today's renderer headers are hardcoded
English. reportlab's base-14 fonts carry no Arabic glyphs, so Arabic PDFs without an embedded
font produce empty glyphs — a correctness defect for Arabic-first tenants, not a polish item.

## R9 - Artifact retention and purge

**Decision**: Artifacts (storage objects) expire after a configurable window (default 90 days).
The scheduler's tick includes a purge pass: objects past expiry are deleted from the private
bucket, the `export_job` row is marked expired (new terminal-ish state with `expires_at`), and a
`reports.artifact_purged` audit event is written. `export_job` rows are kept (they are the
reporting history); only the stored bytes go away. Download of a purged artifact returns not
found.

**Rationale**: The Wave 15 security critique requires bounded storage exposure and a documented
retention story. Keeping job rows while purging bytes preserves the audit and history value at
near-zero storage cost.

## R10 - Performance budgets and the measured baseline

**Decision**: The budgets are the existing ones, now enforced: initial bundle ≤ 500 kB raw
(measured 588.35 kB on 2026-09-14 — reduce via route-level lazy loading), component style budget
4 kB (nine components currently exceed by 109 bytes to 4.68 kB — refactor or split styles),
compare-grid recalculation < 150 ms (constitution gate — add an automated regression test, none
exists today), export of 10,000 rows ≤ 60 s, digest generation ≤ 30 s per subscription. No budget
is raised to make the build pass; the build is brought to the budgets.

**Rationale**: Raising a budget to match a regression is how budgets stop meaning anything. The
Wave 15 baseline (docs/quality/r2.5-performance-accessibility-baseline.md) records the exact
measured numbers so R2.5 success is a diff against evidence, not opinion. Lazy loading is the
assumed technique; if a route cannot be split, the plan's assumption is revisited with data.

## R11 - Accessibility pass scope

**Decision**: Mandatory surfaces for the R2.5 axe-core zero-violation gate: sign-in, dashboard,
compare, basket split, alerts inbox, supplier scorecard, savings ledger, approval queue, Reports
center, and digest settings — each in English and Arabic. The Reports center and digest settings
additionally require a keyboard-only Playwright journey in both directions. Print stylesheet
coverage is required for the Reports center artifact list.

**Rationale**: The constitution gate is "WCAG 2.1 AA, automated axe-core scan clean" measured in
CI; a pass needs a named surface list or "every shell screen" quietly becomes "the new screens
only". The list is the existing high-value screens plus the two new ones; mobile is out of R2.5
scope per the roadmap.

## R12 - Security review depth before G2

**Decision**: Four layers, all blocking or recorded: (1) gitleaks — already a required CI check,
unchanged; (2) dependency audits — new blocking CI job running `pip-audit` (api + workers) and
`pnpm audit --prod` (web + packages), failing on high/critical with an allowlist file for
accepted, owned findings; (3) a manual security review executed against R2.5 and recorded in
`docs/quality/r2.5-security-review-record.md` — RLS policy review for the two new tables, worker
tenant-pinning review, signed-URL TTL and bucket policy review, rate-limit review for the new
endpoints, SMTP secret-handling review; (4) a procurement-ready penetration-test scope document
(`docs/operations/pentest-scope.md`) per roadmap §10.8 ("third-party test before general
availability"). The pentest itself is out of R2.5.

**Rationale**: The Wave 15 plan asked for the required scan depth before G2. CI-visible automation
covers what can be automated; the checklist covers what cannot (policy shape, boundary pinning);
the pentest is a purchase, and R2.5's job is to make it procurable the day G2 closes. G2 itself is
passed on product telemetry, not on these checks — the Wave 15 G2 evidence checklist carries that
separately.

## Open questions carried to Wave 16

None blocking. Two items are flagged for the user at the Wave 16 start gate, both recorded as
spec assumptions: the SMTP provider-agnostic choice (R7), and Noto Naskh Arabic (or equivalent
OFL font) as the embedded Arabic typeface (R8).
