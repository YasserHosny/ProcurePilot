# Feature Specification: Platform Foundation

**Feature Branch**: `001-platform-foundation`
**Created**: 2026-08-20
**Status**: Draft
**Input**: User description: "Chunk 4.1 Foundation (R1.0): monorepo, CI/CD, environments, authentication, multi-tenancy, RBAC skeleton, design system v1, and app shell."

## Overview

This feature establishes the ground floor every later ProcurePilot capability stands on: a business can create an isolated workspace, sign in, invite colleagues with roles, and see an application shell in their language — while the team can build, test, and release that application repeatably.

It deliberately delivers **no procurement functionality**. Catalogue, documents, extraction, matching, comparison, and savings all arrive in later chunks (4.2–4.6). The value of this chunk is that those chunks become buildable, and that the isolation guarantee they depend on is proven from the first commit rather than retrofitted.

## Clarifications

### Session 2026-08-20

- **Q: What region, currency, and tax model should a new workspace default to?**
  **A: No default — collected at sign-up.** The registering business states its region,
  primary currency, and tax model during workspace creation. This resolves roadmap decision
  D2 for engineering purposes without pre-committing the commercial launch region: the
  supported set can be narrow at first and widened without schema change. Consequence: the
  sign-up flow gains a configuration step, and the tax model must be data-driven from the
  first migration rather than a hardcoded rate.

- **Q: During the pilot, who may create a workspace?**
  **A: Invitation-gated.** Workspace creation in R1.0 requires a platform invitation issued
  by the ProcurePilot team; public registration is closed. Consequence: abuse prevention,
  email-verification hardening, and registration rate limiting stay out of this chunk. Opening
  self-serve registration is part of chunk 4.6, where gate G1's "≥8 paying customers on a
  self-serve product" is actually measured.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A business gets its own isolated workspace (Priority: P1)

A small-business owner discovers ProcurePilot, creates an account, and lands in a workspace that belongs solely to their business. Everything they later add — suppliers, quotations, prices, savings — is visible to their business and to no one else. The owner never configures isolation; it is the default state of the system.

**Why this priority**: commercial pricing data is the most sensitive information the product will ever hold. A tenancy model retrofitted after data exists is both expensive and unsafe, and one cross-tenant leak would end the product's credibility. Nothing else can be built until this is true and proven.

**Independent Test**: create two separate businesses, add a marker record to each, and confirm from every entry point that neither can read, list, modify, or infer the existence of the other's record. Delivers a demonstrable isolation guarantee even with zero product features present.

**Acceptance Scenarios**:

1. **Given** a visitor holding a valid platform invitation, **When** they complete sign-up with their business name, region, primary currency, and tax model, **Then** a workspace is created with that configuration, they become its owner, and they are signed in to it.
2. **Given** a visitor with no platform invitation, **When** they attempt to create a workspace, **Then** the attempt is refused and no workspace is created.
3. **Given** two workspaces each holding one record, **When** a member of workspace A requests workspace B's record by its identifier, **Then** the system responds as though the record does not exist, and the attempt is recorded.
4. **Given** a signed-in member, **When** any request is made on their behalf, **Then** the request resolves to exactly one workspace, and a request that resolves to none is rejected rather than served unscoped.
5. **Given** a member who has been removed from a workspace, **When** they retry a previously working request, **Then** access is refused.

---

### User Story 2 - A team works together with appropriate authority (Priority: P2)

The owner invites colleagues — a buyer who will do the purchasing work, a branch manager who will request goods, an approver who will authorise spend, and a viewer who may only read. Each sees the workspace through the lens of their role. The roles carry no procurement powers yet; they establish who *will* be permitted to do what when those powers arrive.

**Why this priority**: the authority model shapes every later endpoint and screen. Introducing it after requests and approvals exist would mean re-deciding permissions across a large surface. Isolation (P1) must exist first, because roles are meaningless without a workspace to be scoped to.

**Independent Test**: invite one user of each role, sign in as each, and confirm the permitted and refused actions match the role matrix — testable with only the account and workspace screens present.

**Acceptance Scenarios**:

1. **Given** an owner, **When** they invite an email address and choose a role, **Then** the invitee can accept, join that workspace, and hold exactly that role.
2. **Given** a member holding a non-owner role, **When** they attempt an owner-only action such as inviting a user or changing another member's role, **Then** the action is refused with a clear explanation and the attempt is recorded.
3. **Given** a viewer, **When** they open the workspace, **Then** they can read what their role permits and are offered no action they may not perform.
4. **Given** the only owner of a workspace, **When** they attempt to remove or demote themselves, **Then** the action is refused, because a workspace must always retain at least one owner.
5. **Given** an invitation that has expired or been revoked, **When** the recipient attempts to accept it, **Then** it is refused and no membership is created.

---

### User Story 3 - The product speaks the customer's language from day one (Priority: P2)

A member whose working language is Arabic uses the application in Arabic, with the interface laid out right-to-left. A member working in English sees the same application left-to-right. Amounts and dates read correctly in both. No screen is hardcoded to one language or direction.

**Why this priority**: bidirectional layout and currency/locale correctness are structural, not cosmetic. The roadmap treats retrofitting them as disproportionately expensive, and locale-sensitive number parsing — decimal separators above all — is a known source of silent financial error in exactly the calculations this product exists to perform.

**Independent Test**: switch language on the shell and confirm every visible string resolves from the shared catalogue, layout mirrors correctly, and no untranslated key or reversed-punctuation defect appears.

**Acceptance Scenarios**:

1. **Given** a member with Arabic selected, **When** any shell screen renders, **Then** the layout is right-to-left and all visible text comes from the Arabic catalogue.
2. **Given** a member switches language, **When** the change is applied, **Then** it persists across sign-out and sign-in on the same account.
3. **Given** a string with no entry in the active catalogue, **When** a screen renders it, **Then** the gap is detectable by automated check rather than silently displaying a raw key to the user.
4. **Given** a monetary amount, **When** it is displayed, **Then** it carries an explicit currency and is formatted for the active locale.

---

### User Story 4 - The team can build and release repeatably (Priority: P3)

A developer joins the project, starts the whole system on their machine with a single documented command, and gets a working environment. When they open a change, automated checks build it, test it, and report a verdict. When the change is accepted, a documented path takes it to a running environment without manual assembly.

**Why this priority**: it does not deliver customer value directly, which is why it is P3 — but every subsequent chunk's cost is set by how reliable this is. It is placed last because it can be validated only once there is an application to build.

**Independent Test**: on a clean machine, follow the written setup steps and confirm the system starts and its health check reports healthy; open a trivial change and confirm the automated checks run and report.

**Acceptance Scenarios**:

1. **Given** a clean checkout, **When** a developer runs the documented start command, **Then** the application, its interface, and its data store start together and the health check reports healthy.
2. **Given** a proposed change, **When** it is submitted, **Then** automated build and test checks run and their pass/fail verdict is visible before it can be accepted.
3. **Given** a change that breaks a test, **When** checks run, **Then** the failure is reported and the change is blocked from acceptance.
4. **Given** an accepted change, **When** the release path runs, **Then** it produces a deployable artefact without hand-assembled steps.
5. **Given** any environment, **When** it is configured, **Then** its secrets come from managed configuration and no secret is present in the repository.

---

### Edge Cases

- **Sign-up with an email that already belongs to another workspace** — the person is a distinct member of each workspace; the system must never silently merge, and must resolve exactly one active workspace per session.
- **Workspace creation attempted with a spent, expired, or revoked platform invitation** — refused, with no partial workspace left behind.
- **Two people sign up for the same business independently** — the second creates a separate workspace rather than joining the first; joining requires an invitation. The system must not guess that two similar business names are the same business.
- **Session outlives membership** — a member removed mid-session must lose access on their next request, not at session expiry.
- **Identity provider unreachable** — sign-in fails with a clear, non-technical message; the system must not fall back to an unauthenticated or partially trusted state.
- **Request arrives with a well-formed credential that names an unknown or deleted workspace** — refused, and recorded.
- **Language catalogue missing an entry** — detectable by automated check; must never surface a raw key to an end user.
- **Health check while the data store is unavailable** — reports unhealthy rather than healthy, so a broken environment cannot pass as working.
- **Concurrent invitation acceptance** — accepting the same invitation twice creates exactly one membership.
- **Last-owner removal** — refused in every path that could otherwise leave a workspace ownerless.

## Requirements *(mandatory)*

### Functional Requirements

**Workspace and isolation**

- **FR-001**: System MUST allow a new business to self-register, creating exactly one workspace with the registrant as its owner.
- **FR-002**: System MUST associate every stored record that belongs to a business with exactly one workspace.
- **FR-003**: System MUST enforce workspace isolation at the data-storage layer, so that isolation holds even if application-level filtering is omitted by mistake.
- **FR-004**: System MUST resolve every authenticated request to exactly one workspace scope, and MUST refuse any request that cannot be so resolved.
- **FR-005**: System MUST respond to a cross-workspace access attempt without revealing whether the requested record exists.
- **FR-006**: System MUST record every authentication and authorisation failure with enough detail to investigate it, and without recording credentials.

**Identity, roles, and membership**

- **FR-007**: Users MUST be able to register, sign in, sign out, and reset their password.
- **FR-008**: System MUST support the roles owner, buyer, branch manager, approver, and viewer, and MUST assign exactly one role per member per workspace.
- **FR-009**: Owners MUST be able to invite a user by email address with a chosen role, and to revoke a pending invitation.
- **FR-010**: System MUST require invitations to be accepted by the invited address, and MUST expire unaccepted invitations after a bounded period.
- **FR-011**: Owners MUST be able to change a member's role and remove a member.
- **FR-012**: System MUST prevent any action that would leave a workspace with no owner.
- **FR-013**: System MUST refuse actions not permitted to the actor's role, and MUST NOT present actions a role may not perform.
- **FR-014**: System MUST record membership and role changes as an auditable history.
- **FR-015**: System MUST carry a per-member indicator of whether multi-factor authentication is enabled, so that enforcement can be introduced later without a data migration.

**Application shell and localisation**

- **FR-016**: System MUST present a signed-in shell with navigation, workspace identity, and account controls, and MUST separate routes that require authentication from those that do not.
- **FR-017**: System MUST source all user-facing text from a shared catalogue supporting English and Arabic.
- **FR-018**: System MUST render right-to-left layout when the active language is right-to-left.
- **FR-019**: System MUST persist a member's language choice across sessions.
- **FR-020**: System MUST record each workspace's region, primary currency, and tax model at creation, and MUST store every monetary value with an explicit currency.
- **FR-021**: System MUST apply a documented, consistent visual language — colour, typography, spacing, and shared interface elements — across the shell.
- **FR-022**: System MUST meet WCAG 2.1 AA on all shell screens.

**Engineering foundation**

- **FR-023**: System MUST start completely on a developer machine via a single documented command, including its data store.
- **FR-024**: System MUST expose a health check reporting healthy only when the application and its data store are both reachable.
- **FR-025**: System MUST run automated build and test checks on every proposed change and report a blocking verdict.
- **FR-026**: System MUST produce a deployable artefact through an automated, repeatable path.
- **FR-027**: System MUST read all secrets from managed configuration, and MUST contain no secret in version control.
- **FR-028**: System MUST separate local, staging, and production environments with independent configuration and data.
- **FR-029**: System MUST emit structured logs and report unhandled errors to a monitoring destination.
- **FR-030**: System MUST include an automated test proving cross-workspace isolation, and this test MUST run on every proposed change.

**Workspace creation and configuration**

- **FR-031**: System MUST collect region, primary currency, and tax model from the registrant during workspace creation, and MUST NOT apply a silent default for any of the three.
- **FR-032**: System MUST validate the chosen region, currency, and tax model against a supported set held as data, so the set can be widened without schema change.
- **FR-033**: System MUST require a valid, unexpired platform invitation to create a workspace, and MUST refuse workspace creation without one.
- **FR-034**: System MUST record which platform invitation a workspace was created from, so pilot cohorts are attributable.

### Key Entities

- **Workspace (Tenant)**: a customer business and the isolation boundary for all its data. Holds business name, unique identifier, region, primary currency, and tax model. Every other business record belongs to exactly one workspace.
- **Member (User / Membership)**: a person's participation in one workspace, holding their identity, exactly one role, and their multi-factor status. One person may hold memberships in several workspaces; each is separate.
- **Role**: the authority level of a membership — owner, buyer, branch manager, approver, or viewer — determining permitted actions.
- **Member Invitation**: a pending offer of membership in an existing workspace, to an email address with an intended role, with an expiry and an accepted/revoked state.
- **Platform Invitation**: a pending offer admitting a new business to the pilot, permitting exactly one workspace creation, with an expiry and an accepted/revoked state. Retained after use so a workspace is attributable to the cohort that produced it.
- **Audit Event**: an append-only record of a security- or membership-significant action, capturing actor, workspace, action, and time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new business can go from landing on the sign-up screen to standing in its own workspace in under 3 minutes without assistance.
- **SC-002**: In 100% of automated cross-workspace attempts, no data belonging to another workspace is returned, and the existence of the target record is not revealed.
- **SC-003**: An owner can invite a colleague and see them active in the workspace in under 2 minutes.
- **SC-004**: 100% of role-restricted actions are refused for roles that do not hold them, verified by automated test for every role.
- **SC-005**: 100% of user-facing strings on shell screens resolve from the shared catalogue in both supported languages, with zero missing entries at release.
- **SC-006**: All shell screens pass an automated WCAG 2.1 AA check with zero violations.
- **SC-007**: A developer with no prior exposure to the project reaches a running local system in under 30 minutes using only the written setup steps.
- **SC-008**: Automated checks report a verdict on a proposed change within 10 minutes of submission.
- **SC-009**: Zero secrets are present in version control, verified by automated scan on every change.
- **SC-010**: A change that breaks any test is blocked from acceptance in 100% of cases.
- **SC-011**: 100% of workspace-creation attempts without a valid platform invitation are refused.
- **SC-012**: Every workspace records a region, currency, and tax model at creation, with zero workspaces holding an inferred or empty value.

## Assumptions

- **Identity is delegated, not built.** Authentication uses the managed identity provider already selected in the architecture decision records; password storage, reset flows, and session issuance are not re-implemented.
- **One role per member per workspace.** The data dictionary defines `role` as a single enumerated value; composite or multiple simultaneous roles are out of scope.
- **Roles are declared, not yet exercised.** This chunk establishes the role set and enforcement mechanism. The procurement permissions those roles will govern arrive with the features themselves in chunks 4.2–4.6.
- **A person may belong to several workspaces**, with exactly one active at a time in a session. Cross-workspace switching UI is minimal in this chunk.
- **Multi-factor authentication is modelled but not enforced.** The per-member indicator exists so enforcement is a policy change later, not a migration.
- **Invitation expiry defaults to 7 days** for both platform invitations and workspace member invitations, an industry-standard interval, unless the pilot programme requires otherwise.
- **Two invitation kinds exist**: a *platform* invitation admits a new business to the pilot and permits workspace creation; a *member* invitation admits a person to an existing workspace. They share an expiry model but not a purpose.
- **The supported region/currency/tax set starts narrow** — as few as one entry — and is data, not code.
- **English and Arabic only.** Additional languages are structurally supported by the catalogue but not supplied.
- **Design system v1 means tokens and shell-level elements** — colour, typography, spacing, buttons, form fields, navigation — not a comprehensive component library.
- **The technology stack is already fixed** by the tech stack blueprint and the ADRs; this specification states outcomes, and the plan states the means.
- **Staging and production environments are provisioned as skeletons** in this chunk, sized for pilot load rather than scale.

## Dependencies

- Architecture decision records and the tech stack blueprint, which fix the stack this foundation must instantiate.
- The engineering specification's repository layout (§1), module boundaries (§2), and security model (§7).
- The deployment plan, for environment topology, release path, and secret management.
- A managed identity and database provider account, plus hosting and error-monitoring accounts, all provisioned before the release path can run end to end.
- Roadmap decision D2 (launch region, currency set, tax model) no longer blocks this chunk: configuration is collected per workspace and validated against a data-held supported set. D2 still governs which entries that set contains at launch, and remains open for commercial planning.

## Out of Scope

Everything on the procurement value chain, deferred to later chunks by design:

- Product catalogue, suppliers, units, and pack definitions (chunk 4.2)
- Document upload, extraction, and the review queue (chunk 4.3)
- Product matching, normalisation, and the landed-cost engine (chunk 4.4)
- Offer comparison, recommendations, and baskets (chunk 4.5)
- Savings ledger, exports, onboarding polish, and billing (chunk 4.6)
- Purchase requests, approvals, branches, and budgets (Phase 2)
- The mobile application beyond an empty project placeholder (Phase 2)
- Any accounting, POS, inventory, or ERP integration (Phase 3)
- Subscription plan gating and payment collection (chunk 4.6)
