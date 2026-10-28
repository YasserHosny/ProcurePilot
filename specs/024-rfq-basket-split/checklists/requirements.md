# Specification Quality Checklist: Split an RFQ Between Suppliers and Turn the Split Into Purchase Requests

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-28
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain (owner decision recorded below)
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

- "Why now" cites current behaviour (one request per RFQ, latest-price source) as motivation only.
- **Q2 resolved (owner, 2026-10-28): the split is approved as one group.** Submit, approve, reject and
  withdraw act on the whole split (FR-010). The approver is chosen by the combined total (FR-011), so
  splitting can't route a purchase below its approval threshold.
- FR-008 changes the rule that an RFQ converts into exactly one request. Planning must update the
  conversion lock and the guardrail evaluator (ADR-019) together.
- FR-010 to FR-012 add a group concept to request approval. Planning should check spec 008/010
  (requests, approvals, delegation, budgets) and the mobile approval screen, which must also show a split
  as one item.
- The split's saving is not written to the savings ledger (R1-M12 is out of scope).
- Ready for `/speckit.plan`.
