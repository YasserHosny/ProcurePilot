# Feature Specification: Organisation Model

**Feature Branch**: `007-organisation-model`
**Created**: 2026-08-22
**Status**: Draft
**Input**: User description: "Chunk R2.0 Organisation Model, start of Phase 2: branches, cost centres, an expanded roles and permissions model beyond Phase 1 owner/buyer/branch-manager/approver/viewer, budget definitions, and an organisation settings screen. This is the foundational layer that later Phase 2 releases depend on: purchase requests (R2.1) need branches and cost centres to assign to and budgets to check against; approval routing (R2.1) needs the expanded roles and permissions; mobile (R2.2/R2.3) needs branch membership to scope what a branch manager sees. Scope for this chunk specifically: branch CRUD (name, address, region, active or inactive), cost-centre CRUD (name, code, budget owner), budget definitions (period, amount, currency, scope of org-wide, branch, or cost-centre), an org settings screen, and a role and permission model extended to support branch-scoped and cost-centre-scoped access so a branch manager sees only their own branch data. Explicitly out of scope for this chunk: purchase requests themselves, approval routing and workflow, the mobile app, the advanced basket optimiser, supplier scorecards, anomaly detection, and scheduled reports, all of which are later Phase 2 releases starting at R2.1 per the roadmap."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Owner structures the business into branches (Priority: P1)

An owner running a business with more than one physical location or division creates a branch
for each one (a shop, a site, a regional office), giving each a name, address, region, and
active status. This is the prerequisite every later Phase 2 capability hangs off: a purchase
request has to belong to a branch, an approver has to be scoped to one, and a branch manager's
mobile app has to know which branch they manage.

**Why this priority**: Nothing else in this chunk or in R2.1 onward is reachable without at
least one branch existing. It is the root of the whole organisational tree.

**Independent Test**: Can be fully tested by an owner creating, editing, and deactivating a
branch through the org settings screen, and confirming the branch list reflects each change
immediately — independent of cost centres, budgets, or any role assignment.

**Acceptance Scenarios**:

1. **Given** an owner on the organisation settings screen, **When** they create a branch with a
   name, address, and region, **Then** the branch appears in the branch list as active.
2. **Given** an existing active branch, **When** the owner marks it inactive, **Then** it no
   longer appears as an assignable option anywhere in the product, but its historical data (once
   later releases produce any) remains visible and attributed to it.
3. **Given** a branch with members or a cost centre still assigned to it, **When** the owner
   attempts to deactivate it, **Then** the system allows the deactivation (a branch closing down
   is a normal business event) but requires an explicit confirmation naming what is still
   attached, so the owner is not surprised later.

---

### User Story 2 - Owner defines cost centres and assigns a budget owner (Priority: P1)

An owner or finance-authorised member creates cost centres (e.g. "Kitchen", "Facilities",
"Marketing"), each with a name, a short code, and a designated budget owner (a specific member
responsible for that cost centre's spend). A cost centre may optionally belong to one branch, or
span the whole organisation.

**Why this priority**: Equal in priority to branches — cost centres are the other assignment
target that requests (R2.1) and budgets in this chunk both depend on. Without a cost centre, a
budget has nothing to attach to at that granularity.

**Independent Test**: Can be fully tested by creating a cost centre, assigning a budget owner
from the existing member list, optionally linking it to a branch, and confirming it appears
correctly scoped in the cost-centre list — independent of whether any budget has been defined for
it yet.

**Acceptance Scenarios**:

1. **Given** an owner on the organisation settings screen, **When** they create a cost centre
   with a name, a unique code, and a budget owner chosen from existing members, **Then** the cost
   centre appears in the list with that owner shown.
2. **Given** a cost centre linked to a specific branch, **When** that branch is later deactivated,
   **Then** the cost centre is flagged as orphaned rather than silently left in an inconsistent
   state, and the owner is prompted to reassign or archive it.
3. **Given** an attempt to create a cost centre with a code already in use in the same tenant,
   **When** the form is submitted, **Then** the system rejects it with a clear duplicate-code
   message.

---

### User Story 3 - Owner defines a budget and sees it reflected in org settings (Priority: P2)

An owner defines a budget: an amount, a currency, a period (e.g. monthly, quarterly, annual), and
a scope — the whole organisation, one branch, or one cost centre. This chunk defines and stores
the budget; enforcing it against real purchase requests is explicitly R2.1's job, not this one.

**Why this priority**: Depends on User Stories 1 and 2 existing (branch- and cost-centre-scoped
budgets need those entities first), and its own consumer (request-time budget checking) is
explicitly out of scope until R2.1 — so it is real, necessary, and independently demonstrable,
but one step removed from the two foundational stories above.

**Independent Test**: Can be fully tested by defining a budget at each of the three scopes
(org-wide, one branch, one cost centre) and confirming each appears correctly attributed in the
budget list, with no purchase-request flow required to observe it.

**Acceptance Scenarios**:

1. **Given** an owner on the organisation settings screen, **When** they define a budget with an
   amount, currency, period, and org-wide scope, **Then** it appears in the budget list as the
   organisation's overall budget for that period.
2. **Given** an existing branch, **When** the owner defines a budget scoped to that branch,
   **Then** the budget list shows it attributed to that specific branch, distinct from the
   org-wide budget.
3. **Given** two budgets already exist for the same scope with overlapping periods, **When** the
   owner defines a third overlapping one, **Then** the system allows it (multiple budgets can
   legitimately co-exist, e.g. a running annual budget and a supplementary quarterly top-up) but
   surfaces the overlap so the owner is not defining it by accident.

---

### User Story 4 - Branch manager sees only their own branch's data (Priority: P1)

A member holding the branch_manager role, now assigned to a specific branch, signs in and sees
organisation screens (branch details, cost centres, budgets) scoped to their own branch only —
not the whole organisation's data, and not other branches' data. An owner, by contrast, continues
to see everything.

**Why this priority**: This is the actual permissions payoff of the whole chunk — without it,
"branch-scoped access" is just a label on a role with no enforcement behind it, and every later
Phase 2 release that assumes a branch manager cannot see other branches would be building on an
unmet assumption.

**Independent Test**: Can be fully tested by assigning a member the branch_manager role scoped to
Branch A, signing in as that member, and confirming Branch B's data and any org-wide-only screens
are not visible or reachable, while Branch A's own data is — independent of requests, approvals,
or budgets being enforced anywhere yet.

**Acceptance Scenarios**:

1. **Given** a member assigned as branch_manager of Branch A, **When** they view the branch list,
   **Then** they see only Branch A, not Branch B or any other branch in the tenant.
2. **Given** the same member, **When** they view cost centres, **Then** they see only cost
   centres linked to Branch A plus org-wide cost centres, not cost centres linked to another
   branch.
3. **Given** the same member attempts to access Branch B directly (e.g. by a guessed or shared
   link), **When** the request is made, **Then** the system responds as though Branch B does not
   exist, not with a permission-denied message (consistent with the existing cross-tenant
   non-disclosure convention, applied here at the branch-isolation layer).
4. **Given** an owner, **When** they view the same screens, **Then** they see every branch, every
   cost centre, and every budget in the tenant, unscoped.

---

### Edge Cases

- What happens when an owner tries to delete (not just deactivate) a branch, cost centre, or
  budget that still has other records depending on it? The system does not permit hard deletion
  of a branch or cost centre once anything references it; deactivation/archiving is the only path
  once dependents exist, so history is never silently destroyed.
- How does the system handle a member whose role or branch assignment changes while they are
  actively signed in? The change takes effect on their next request, not retroactively for
  requests already in flight, consistent with how role changes already behave in Phase 1.
- What happens if a tenant defines zero branches at all? The organisation continues to operate
  entirely at the org-wide scope, exactly as it did before this chunk — branches are additive,
  never mandatory, since not every business is structured that way.
- What happens to a cost centre's budget owner if that member is removed from the workspace
  entirely? The cost centre is flagged as having no budget owner and surfaced to the owner for
  reassignment, rather than silently keeping a reference to a removed member.
- What happens when a member holds a role that is scoped to more than one branch (e.g. an
  approver responsible for two branches, not one)? Supported: role assignment can name one or
  more branches for scoped roles, not only exactly one.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow an owner to create, edit, and deactivate branches, each with a
  name, an address, a region, and an active/inactive status.
- **FR-002**: System MUST allow an owner to create, edit, and archive cost centres, each with a
  name, a unique-per-tenant code, a designated budget owner, and an optional link to one branch
  (absent = organisation-wide cost centre).
- **FR-003**: System MUST reject a cost centre creation or edit that would produce a duplicate
  code within the same tenant.
- **FR-004**: System MUST allow an owner to define a budget with an amount, an explicit currency,
  a period, and a scope of exactly one of: the whole organisation, one named branch, or one named
  cost centre.
- **FR-005**: System MUST allow multiple budgets to coexist for the same scope, including
  overlapping periods, while surfacing the overlap to the person defining the new one.
- **FR-006**: System MUST extend the existing role model so that the branch_manager and approver
  roles (already defined in Phase 1's role matrix) can be scoped to one or more specific branches,
  in addition to existing as tenant-wide roles for owner, buyer, and viewer.
- **FR-007**: System MUST scope every organisation-model screen (branch list, cost-centre list,
  budget list) to the signed-in member's role and branch assignment: an owner sees everything in
  the tenant; a member holding a branch-scoped role sees only their own assigned branch(es) and
  organisation-wide entities, never another branch's data.
- **FR-008**: System MUST respond to an attempt to access another branch's data the same way the
  product already responds to a cross-tenant access attempt: as though the resource does not
  exist, never with an explicit permission-denied message, so branch existence itself is not
  disclosed to a member without access to it.
- **FR-009**: System MUST NOT permit hard deletion of a branch or cost centre once any other
  record depends on it; deactivation/archiving is the only path in that case, preserving history.
- **FR-010**: System MUST flag a cost centre as orphaned (without silently reassigning or hiding
  it) when the branch it is linked to is deactivated, or when its designated budget owner is
  removed from the workspace, and surface that flag to the owner for resolution.
- **FR-011**: System MUST provide an organisation settings screen from which an owner manages
  branches, cost centres, and budgets in one place, in both English and Arabic (RTL) per the
  product's existing localisation standard.
- **FR-012**: System MUST record every branch, cost centre, and budget creation, edit,
  deactivation, and archival in the existing append-only audit log, consistent with how every
  other administrative action in the product is already audited.

### Key Entities

- **Branch**: A physical location or organisational division within a tenant. Has a name,
  address, region, and active/inactive status. The unit that branch-scoped roles, and later
  purchase requests (R2.1), are assigned against.
- **Cost Centre**: A budget-tracking grouping within a tenant, independent of physical location.
  Has a name, a tenant-unique code, a designated budget-owner member, and an optional link to one
  branch. The unit that budgets and, later, purchase requests can be assigned against at a finer
  grain than a whole branch or the whole organisation.
- **Budget**: A defined spending allowance for a period (e.g. monthly, quarterly, annual), with an
  explicit amount and currency, scoped to exactly one of: the organisation as a whole, one branch,
  or one cost centre. This chunk defines and stores budgets; checking real spend against them at
  request time is out of scope until R2.1.
- **Branch Assignment**: The association between a member's role and the specific branch(es) that
  role is scoped to, extending the existing membership/role relationship rather than replacing it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An owner can define a complete organisational structure — at least one branch, one
  cost centre, and one budget — in under 10 minutes without external help.
- **SC-002**: A member assigned a branch-scoped role never sees another branch's name, address, or
  budget figures anywhere in the product, verified across every organisation-model screen.
- **SC-003**: 100% of branch, cost centre, and budget administrative actions appear in the audit
  log with the correct actor, action, and target.
- **SC-004**: Deactivating a branch or archiving a cost centre with existing dependents never
  results in an orphaned reference silently disappearing from view; every such case is surfaced to
  the owner for explicit resolution.
