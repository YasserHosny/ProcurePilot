# Specification Quality Checklist: Matching and Normalisation

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
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

- Every candidate ambiguity (auto-accept threshold value, whether "other charges" needs modelling,
  whether matching is a separate trigger or automatic) resolved to a documented default in
  **Assumptions** rather than a [NEEDS CLARIFICATION] marker, same discipline as chunks 4.2 and 4.3.
- **A real architectural discrepancy surfaced during research, deliberately not resolved here**:
  `docs/architecture/engineering-spec.md` §2.3 names a `services/matching-worker` as its own
  deployable, but `.specify/memory/constitution.md` Principle VI pre-authorises only "the extraction
  worker and the optimiser" — matching is not named, and unlike extraction (which calls slow,
  external third-party APIs), matching is pure in-database computation (`pg_trgm`/`pgvector`
  queries plus scoring) with no external network call and no equivalent latency/isolation
  justification. This spec deliberately says nothing about services vs. modules — that is an
  implementation decision for `/speckit.plan`'s Constitution Check, not a business requirement — but
  the next phase must not silently follow engineering-spec's service listing without addressing
  this. Constitution supersedes engineering-spec per the Governance section.
- FR-009 (create-new-product from a match decision) deliberately reuses chunk 4.2's existing
  product-creation capability rather than specifying a new one — this chunk is a new caller of that
  capability, not a redesign of it.
- SC-002 and SC-003 (the 92%/8% gates) are carried forward from the constitution's Quality Gates
  table verbatim; they cannot be honestly verified until a real held-out labelled benchmark exists,
  which is recorded as an assumption rather than papered over.
