# Phase 0 Research: Organisation Model

## R1 — How branch-scoped RLS visibility is enforced

**Decision**: A new SQL helper function, `current_membership_id()`, resolves the signed-in
member's own `membership.id` via a live lookup (`tenant_id = current_tenant_id() and user_id =
current_user_id() and is_active_workspace = true`), and branch-scoped RLS policies on `branch`,
`cost_centre`, and `budget` check membership against `branch_role_assignment` live, at
query-evaluation time — not via a JWT claim.

```sql
create or replace function current_membership_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id from membership
  where tenant_id = current_tenant_id()
    and user_id = current_user_id()
    and is_active_workspace = true
  limit 1;
$$;
```

A representative policy shape (branch table):

```sql
create policy branch_visibility on branch
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or not exists (select 1 from branch_role_assignment where membership_id = current_membership_id())
      or exists (
        select 1 from branch_role_assignment
        where membership_id = current_membership_id() and branch_id = branch.id
      )
    )
  );
```

(`current_member_role()` reads the existing `member_role` JWT claim the same way
`current_tenant_id()` already reads `tenant_id` — no new claim needed, since `member_role` is
already present on every token per chunk 4.1's auth hook. The middle `not exists` clause covers a
role like `buyer` or `viewer` that has no branch assignment at all, meaning tenant-wide by
default, not branch-restricted — only a role WITH at least one `branch_role_assignment` row is
actually scoped.)

**Rationale**: The existing precedent for role itself (`resolve_member_from_token` in
`apps/api/src/procurepilot_api/deps.py`) already does a *live* database lookup for role, using
the JWT only for a consistency check, not as the source of truth — role divergence between the
JWT claim and the live row is treated as `membership_claim_mismatch`, forcing re-authentication
rather than silently trusting a stale claim. Branch assignment has no existing JWT representation
at all, so introducing one now would mean extending the auth hook (`20260819000006_auth_hook.sql`)
— a security-sensitive, already-tested piece of chunk 4.1 infrastructure — purely to support a
staleness tradeoff the spec doesn't actually need. A live lookup instead:
- Requires zero auth-hook changes, isolating this chunk's risk to its own new tables.
- Makes a branch reassignment effective on the member's *very next request*, satisfying
  spec.md's edge case ("takes effect on their next request, not retroactively") more literally
  than a claims-based approach would (which would need the member to sign in again before a new
  claim takes effect).
- Matches Principle V's "never rely on application-layer WHERE alone" exactly: the check lives
  in the RLS policy itself, evaluated by Postgres on every row, not filtered by application code
  after the fact.

**Alternatives considered**:
- *Extend the auth hook to inject `branch_ids` into the JWT.* Rejected: touches already-tested
  security-critical infrastructure for a staleness tradeoff (branch reassignment would only take
  effect after a token refresh) that is strictly worse than the live-lookup approach, not better.
- *Application-layer filtering only (no RLS change; the API adds a `WHERE branch_id = ...`
  clause for scoped roles).* Rejected outright — this is precisely the pattern Principle V
  prohibits ("Every tenant-scoped table carries `tenant_id`... Never rely on an application-layer
  `WHERE tenant_id = ...` alone"), and the same reasoning applies to the new branch axis: a
  forgotten filter in one future endpoint would silently leak cross-branch data with no
  database-level backstop.

## R2 — Representing "one or more branches" per scoped role assignment

**Decision**: `branch_role_assignment` is its own join table (`tenant_id`, `membership_id`,
`branch_id`, composite unique on `(membership_id, branch_id)`), not an array column on
`membership`.

**Rationale**: spec.md's edge cases explicitly require supporting a role scoped to more than one
branch (e.g. an approver responsible for two branches). A join table gives this for free with a
standard foreign key and RLS policy, matches the exact pattern `product_alias`/
`workspace_product_substitute` already established in chunk 4.2 for a similar "many-to-many,
tenant-scoped, needs its own RLS" shape, and keeps `membership` itself unchanged — no migration
touching the existing, already-tested `membership` table's structure.

**Alternatives considered**:
- *`branch_id uuid[]` array column on `membership`.* Rejected: arrays cannot carry a foreign key
  (the same reason chunk 4.2's `data-dictionary.md` gives for rejecting a `uuid[]` for product
  substitutes), so a deactivated or deleted branch could leave a dangling ID silently referenced
  from an array with no referential-integrity backstop.

## R3 — Cost centre and budget currency

**Decision**: `budget.currency` is its own explicit, independently-set column (not inferred from
`tenant.currency`), defaulting to the tenant's own currency in the UI but never implicitly
assumed to match it in the schema or a query.

**Rationale**: Matches the exact precedent PR #2 established for `quotation.currency` — that
column is *also* independent of `tenant.currency` (a supplier can quote in a different currency
than the tenant's default), and PR #2's own follow-up findings (tracked in GitHub issue #5) show
what happens when code elsewhere assumes otherwise: a real, confirmed bug in Smart Compare's
recommendation engine and the basket-split optimiser, both of which compared bare amounts across
offers without checking currency. This chunk deliberately does not repeat that mistake for
budgets: currency is explicit from the schema up, per Principle VII, from day one.

**Alternatives considered**:
- *Infer `budget.currency` from `tenant.currency` and omit the column.* Rejected: Principle VII
  ("Monetary values MUST store an explicit currency; no implicit single-currency assumptions")
  and the concrete precedent above both argue against it. The one-time cost of an explicit column
  is trivial next to the class of bug it prevents.
