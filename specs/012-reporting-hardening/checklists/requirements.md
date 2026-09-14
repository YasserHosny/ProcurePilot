# Specification Quality Checklist: Reporting and Hardening

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-14
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

**Validation iteration 1 (2026-09-14)** — the Wave 15 plan named five scope ambiguities that had
to be resolved before tasks: report delivery channels, report formats, digest scope, mandatory
a11y surfaces, and security scan depth. All five were resolved from recorded evidence rather than
guesswork, and are documented in research.md R1–R3, R11, and R12:

1. Delivery model — combination: artifacts in an in-app Reports center plus email digests only
   (roadmap §7.1 and §10.2 name "Scheduled reports and email digests" as distinct surfaces).
2. Formats — CSV everywhere, XLSX everywhere, PDF only for document-shaped kinds; matrix declared
   in the contract (extends the already-shipped Excel/PDF export from R1.5).
3. Digest scope — per-member weekly subscriptions with optional branch filter (keeps the existing
   RLS authorisation model unchanged; tenant-wide digests would either leak or flatten).
4. A11y surfaces — a named mandatory list (existing high-value screens plus the two new ones), in
   both locales, because "every shell screen" without a list decays to "new screens only".
5. Security depth — gitleaks (existing) + blocking dependency-audit CI + recorded manual review
   checklist + procurement-ready pentest scope document; the pentest itself stays out of R2.5.

Two choices are flagged as assumptions for the user at the Wave 16 start gate rather than blocked
on now: provider-agnostic SMTP for email delivery, and the choice of an OFL-licensed Arabic
typeface. Neither changes what is built, only how one subsystem reaches the same requirement.

**Validation iteration 2 (2026-09-14)** — cross-artifact pass against the Wave 15 critique set
(product, security, performance/a11y, docs) completed; contradiction-free. All items pass.
