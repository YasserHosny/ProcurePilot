<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (unversioned) → 1.0.0
Bump rationale: Initial ratification. All placeholder tokens replaced with concrete,
testable governance derived from the approved roadmap. No prior version to compare
against, so this is a MAJOR-equivalent first release rather than an amendment.

Principles defined (template slots 1-5 expanded to 7):
  - [PRINCIPLE_1_NAME] → I. Evidence Over Assertion (NON-NEGOTIABLE)
  - [PRINCIPLE_2_NAME] → II. Deterministic, Replayable Normalisation
  - [PRINCIPLE_3_NAME] → III. Human Authority Over Automation (NON-NEGOTIABLE)
  - [PRINCIPLE_4_NAME] → IV. Every Insight Ends in an Action
  - [PRINCIPLE_5_NAME] → V. Tenant Isolation by Construction
  - (added)           → VI. Modular Monolith Until Scale Demands Otherwise
  - (added)           → VII. Money, Tax, and Language Correct from the Schema Up

Sections added:
  - [SECTION_2_NAME] → Quality Gates and Measured Thresholds
  - [SECTION_3_NAME] → Development Workflow and Phase Discipline
  - Governance (filled)

Sections removed: none

Source of truth traceability:
  - docs/roadmap/procurepilot_roadmap.md §1.4 (product thesis), §1.8 (strategic pillars),
    §1.9 (non-goals), §2.2-2.3 (phase OKRs, stage gates), §9.3 (AI guardrails),
    §10.1 (architectural principles), §10.3 (technology stack)
  - docs/speckit-plan.md §2 (constitution input), §7 (Phase 2 gate conditions)
  - docs/quality/test-strategy.md §1-7 (test pyramid, AI eval, performance, accessibility)

Templates requiring updates:
  ✅ .specify/templates/plan-template.md   — Constitution Check gate references this file
                                              generically; no edit required.
  ✅ .specify/templates/spec-template.md   — scope/requirements sections compatible with
                                              Principles I and IV; no edit required.
  ✅ .specify/templates/tasks-template.md  — task categories already cover test-first and
                                              observability; no edit required.
  ✅ .claude/commands/speckit.*.md         — agent-generic; no outdated references found.
  ⚠ docs/README.md                         — pending: add a pointer to this constitution
                                              once the first feature spec lands.

Deferred items:
  - TODO(LAUNCH_REGION): Principle VII fixes the schema requirement (multi-currency,
    multi-tax, bilingual) but the launch region, currency set, and tax model remain
    open decision D2 in docs/roadmap/procurepilot_roadmap.md §16 (due end M2). No
    principle depends on the answer; only concrete rule data does.
-->

# ProcurePilot Constitution

ProcurePilot converts fragmented supplier information into trusted, comparable, actionable
purchasing decisions, and proves the money saved. This constitution governs how that is
built. It is derived from the Master Roadmap and supersedes habit, convenience, and
individual preference.

## Core Principles

### I. Evidence Over Assertion (NON-NEGOTIABLE)

Every value the product derives, extracts, or infers MUST carry its provenance as
first-class data, never as a metadata blob: source record, extraction or inference method,
model version, confidence score, and reviewing human where one intervened.

- A saving MUST be traceable to the source documents that justify it. A saving that cannot
  be audited back to source MUST NOT be displayed or counted toward the north-star metric.
- A recommendation MUST present evidence, confidence, risk, and validity period. A
  recommendation without all four is incomplete and MUST fail review.
- A forecast MUST state an uncertainty range. Point predictions are read as promises.
- Where history or data is insufficient, the product MUST say so explicitly rather than
  emit a low-confidence number silently.

**Rationale:** a wrong product match produces a *fabricated* saving, which damages trust
more than no saving at all. Confidence and provenance are user-facing product features, not
internal tooling.

### II. Deterministic, Replayable Normalisation

Normalisation and landed-cost computation MUST be pure, versioned, replayable functions.

- Raw inputs MUST be stored alongside the identifier of the rule-set version applied.
- Derived cost MUST be recomputable from raw input plus rule version, yielding an identical
  result. Replay determinism MUST be covered by automated tests.
- Price and offer data MUST be bitemporal: valid-time (when the price applied) and
  record-time (when we learned it) are separate, both required.
- Outcome history — recommendation, action, purchase, delivery, quality, saving — MUST be an
  append-only event stream. Destructive updates to outcome records are prohibited.

**Rationale:** savings claims are defensible only if the system can answer "what did we know,
and when?" and reproduce a historical recommendation after the rules have changed.

### III. Human Authority Over Automation (NON-NEGOTIABLE)

Automation may extract, normalise, compare, recommend, prepare, and route. A human
authorises.

- No purchase may be executed without human authorisation, in any phase, under any
  configuration.
- Human review is an architectural concept, not a screen: the review queue has its own state
  machine, SLAs, and metrics.
- Arithmetic inconsistencies, failed validations, and sub-threshold confidence MUST force
  review rather than silently accept.
- Any grounded-answer or analyst feature MUST cite a source record and show its calculation.
  Ungrounded generation is prohibited.

**Rationale:** autonomous purchasing is an explicit non-goal for the entire roadmap horizon.
Trust is the product's scarcest asset and is lost non-linearly.

### IV. Every Insight Ends in an Action

No read-only dashboards ship as a feature in their own right.

- Every insight surface MUST carry an executable next step, plus the expected value,
  confidence, and validity period of taking it.
- A feature that cannot be traced to the product thesis chain — document → extraction →
  matching → normalisation → landed cost → recommendation → approval → outcome → verified
  saving — MUST be justified explicitly in its spec or rejected.
- The explicit non-goals are binding: no consumer deals application, no generic public
  price-comparison site, no public supplier-review marketplace, no marketplace repricing
  tool, no enterprise source-to-pay suite, no ERP replacement, no social features.

**Rationale:** the normalisation and entity-resolution core *is* the product. Everything else
is replaceable surface area and must earn its place on the value chain.

### V. Tenant Isolation by Construction

Multi-tenancy is enforced by the database, not by application diligence.

- Every tenant-scoped table MUST carry `tenant_id` and MUST be protected by row-level
  security policies.
- Every authenticated request MUST resolve a tenant scope; JWTs carry `tenant_id`.
- Cross-tenant isolation MUST be proven by automated integration tests asserting that a user
  of tenant A cannot read, write, or enumerate data of tenant B. A feature touching
  tenant-scoped data without such a test is incomplete.
- The canonical product spine is shared; tenant aliases, preferences, and history are
  overlaid per tenant and MUST NOT leak between tenants.

**Rationale:** a single cross-tenant leak is an extinction-level event for a product whose
entire value proposition is trusted commercial data.

### VI. Modular Monolith Until Scale Demands Otherwise

One deployable backend with strict internal module boundaries.

- New services MUST NOT be introduced without a measured scaling or isolation reason
  recorded in an ADR. Only the extraction worker and the optimiser are pre-authorised for
  extraction when load justifies it.
- Module boundaries MUST be explicit; cross-module access goes through defined interfaces,
  not shared internal state.
- Complexity MUST be justified in the plan's Complexity Tracking section. Unjustified
  complexity is a review failure, not a style preference.

**Rationale:** a distributed system at Phase 1 is self-inflicted cost paid by a team that has
not yet proven the value loop.

### VII. Money, Tax, and Language Correct from the Schema Up

- Monetary values MUST store an explicit currency; no implicit single-currency assumptions.
- Tax treatment MUST be modelled as data, not hardcoded rates or inline conditionals.
- Unit and pack definitions MUST be explicit and normalised; comparison across pack sizes is
  the core function of the product, not a display concern.
- User-facing strings MUST come from the shared i18n catalogue (English and Arabic), and
  layouts MUST support RTL.
- Locale-sensitive parsing — decimal separators above all — MUST be explicitly tested.

**Rationale:** retrofitting currency, tax, and bidirectional language support is
disproportionately expensive, and decimal-separator errors are a known source of silent
financial leakage.

## Quality Gates and Measured Thresholds

These thresholds are product requirements, not aspirations. A release that misses them does
not ship.

| Gate | Threshold | Measured on |
|---|---|---|
| Extraction field accuracy | ≥90% on priority fields | Held-out labelled benchmark |
| Matching precision at auto-accept | ≥92% | Held-out labelled benchmark |
| Human review band | ≤8% of lines routed to review | Production + benchmark |
| Comparison acceptance | ≥80% accepted without manual correction | Production telemetry |
| Compare grid recalculation | <150 ms | Performance test |
| Accessibility | WCAG 2.1 AA, automated axe-core scan clean | CI |
| Landed-cost replay | Bit-identical on re-run at pinned rule version | Automated test |

Additional standing requirements:

- Test discipline follows the documented pyramid: unit and integration tests on every PR;
  E2E on the critical value path; AI evaluation against held-out sets on model or prompt
  change.
- AI accuracy claims MUST be measured on a held-out set, never on data used to tune the
  extractor, matcher, or prompts.
- Secrets MUST NOT enter the repository. Local agent state and credential-bearing files stay
  in `.gitignore`.

## Development Workflow and Phase Discipline

- **Specification precedes code.** Work flows through the Speckit chain: constitution →
  specify → clarify → plan → tasks → analyze → implement. Implementation without an
  approved spec and task list is out of process.
- **Stage gates are binding.** Phase N+1 code MUST NOT be written until gate G(N-1) is
  passed and recorded. Future-phase chunks may be *planned* and *sketched*; they MUST NOT be
  *implemented*. Current gates: G0 → Phase 1, G1 → Phase 2, G2 → Phase 3, G3 → Phase 4, with
  exit criteria as defined in the roadmap.
- **Ambiguity is resolved before planning**, via clarification recorded in the spec, not
  discovered during implementation.
- **Every PR MUST verify constitutional compliance**, in particular Principles I, III, and V,
  which are the ones whose violation is silent and expensive.
- **Delegated implementation is permitted and reviewed.** Work may be delegated to
  implementer CLIs, but the delegating agent remains accountable: every delegated diff MUST
  be reviewed against the spec and this constitution before it lands.
- **Deviations are documented, not argued.** A justified deviation belongs in the plan's
  Complexity Tracking section or an ADR; an undocumented one is a defect.

## Governance

This constitution supersedes other development practices. Where a document, habit, or tool
conflicts with it, this document wins.

**Amendment procedure.** Amendments require a written proposal stating the principle
affected, the rationale, and the migration impact on existing code and specs. Amendments are
recorded in this file with a Sync Impact Report, and dependent templates and docs are
updated in the same change.

**Versioning policy.** Semantic versioning applies to this document:
- **MAJOR** — a principle is removed or redefined in a backward-incompatible way.
- **MINOR** — a principle or section is added, or guidance is materially expanded.
- **PATCH** — clarification, wording, or non-semantic refinement.

**Compliance review.** Constitutional compliance is checked at three points: the
`/speckit.plan` Constitution Check gate, the `/speckit.analyze` cross-artifact pass, and code
review before merge. Non-compliance blocks the merge unless an explicit, recorded exception
is granted by the project owner.

**Runtime guidance.** Detailed technical and operational guidance lives in `docs/` — the
Master Roadmap for scope and phasing, the engineering spec and ADRs for design decisions, the
test strategy for quality expectations, and the deployment plan and runbook for operations.
This constitution constrains those documents; it does not replace them.

**Version**: 1.0.0 | **Ratified**: 2026-08-20 | **Last Amended**: 2026-08-20
