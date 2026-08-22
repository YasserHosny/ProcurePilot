# Specification Quality Checklist: Catalogue and Suppliers

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-20
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

**Validation iteration 1 (2026-08-20)** — one item failed: a [NEEDS CLARIFICATION] marker on FR-032,
asking which roles may write to the catalogue. Escalated rather than guessed, because a read-only
role needs its own filtered views and that changes what gets built.

**Validation iteration 2 (2026-08-20)** — all items pass. Answer recorded in the spec's
Clarifications section: **owner and buyer write; branch manager, approver and viewer read.** FR-032
became three requirements (FR-032 to FR-034) and SC-009 was added to assert the refusals per role.

Everything else was resolved by informed default and recorded in Assumptions. Notably:

- **Import format** narrowed to delimited text; native spreadsheet binaries would need a parsing
  library and a whole class of error handling that the PRD does not ask for.
- **Base units from a fixed set** rather than free text, because normalising arbitrary unit names
  is not decidable and the entire comparison engine rests on this being right.
- **No prices in this chunk.** The PRD puts pricing with offers, and storing a price against a
  product without a supplier and a validity window would produce a number nobody could defend.

*Content-quality note:* the spec names WCAG 2.1 AA. Retained deliberately — a measurable compliance
target carried from the constitution's quality gates, not a framework choice.
