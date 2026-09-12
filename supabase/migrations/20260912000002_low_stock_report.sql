-- 20260912000002_low_stock_report.sql — task T002, chunk R2.2 (Mobile MVP)
--
-- low_stock_report — a branch manager's quick "running low" signal for a product at their branch
-- (specs/009-mobile-app-mvp/research.md R2). Informational only: no FK from purchase_request to
-- this table or the other direction — deliberately unlinked, since a low-stock report must never
-- create, modify, or commit to any purchase request (FR-006). Insert-only; no PATCH/DELETE
-- surface this release.
--
-- idempotency_key (nullable) plus the partial unique index below is this chunk's own,
-- narrowly-scoped fix for a systemic, separately-tracked gap: Idempotency-Key is accepted but
-- not actually enforced anywhere else in this codebase yet (research.md R4, revised). This table
-- gets real enforcement because it is FR-011's actual offline-retry surface for R2.2 — a replayed
-- POST /low-stock-reports after a dropped response must return the original row, not create a
-- second one.
--
-- Branch-scoped visibility reuses R2.0/008's exact current_membership_id()/current_member_role()
-- mechanism, the same shape as purchase_request — see that migration's own RESTRICTIVE policy
-- for the reasoning; this one is structurally identical, substituting low_stock_report's own
-- "member always sees reports they personally raised" clause for purchase_request's requester
-- clause.

create table if not exists low_stock_report (
  id                      uuid primary key default gen_random_uuid(),
  tenant_id               uuid not null references tenant(id) on delete cascade,
  branch_id               uuid not null,
  member_id               uuid not null,
  workspace_product_id    uuid not null,
  count_remaining         numeric(18, 6),
  idempotency_key         uuid,
  created_at              timestamptz not null default now(),

  constraint low_stock_report_tenant_id_key unique (tenant_id, id),

  constraint low_stock_report_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id),
  constraint low_stock_report_member_fkey
    foreign key (tenant_id, member_id) references membership (tenant_id, id),
  constraint low_stock_report_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id)
);

create index if not exists low_stock_report_tenant_idx on low_stock_report (tenant_id);
create index if not exists low_stock_report_branch_idx on low_stock_report (branch_id);
create index if not exists low_stock_report_product_idx on low_stock_report (workspace_product_id);
create index if not exists low_stock_report_recent_idx
  on low_stock_report (tenant_id, branch_id, workspace_product_id, created_at);

-- Partial: two genuinely separate reports with no key (the common online-submission case) never
-- collide; a replayed offline submission's second attempt with the SAME key is rejected by this
-- index, and the service layer reads the existing row back instead of inserting a duplicate.
create unique index if not exists low_stock_report_idempotency_key_idx
  on low_stock_report (tenant_id, idempotency_key)
  where idempotency_key is not null;

comment on table low_stock_report is
  'A branch manager''s quick "running low" signal for a product (chunk R2.2). Informational
   only — no linkage to purchase_request in either direction (research.md R2). Insert-only.
   idempotency_key + its partial unique index give this table real server-side offline-retry
   dedup (FR-011, research.md R4 revised) — a chunk-scoped fix, not a claim that the
   Idempotency-Key header is enforced anywhere else in this codebase yet.';

alter table low_stock_report enable row level security;
alter table low_stock_report force  row level security;

create policy low_stock_report_tenant_isolation on low_stock_report
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, SELECT-only — same shape as purchase_request's own scoped-visibility policy.
-- Write authorization (which branch a member may report low stock for) is an application-layer
-- check, matching this project's standing convention rather than a second RLS policy.
create policy low_stock_report_scoped_visibility on low_stock_report
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() = 'owner'
      or member_id = current_membership_id()
      or not exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = low_stock_report.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
      )
      or exists (
        select 1 from branch_role_assignment
        where branch_role_assignment.tenant_id = low_stock_report.tenant_id
          and branch_role_assignment.membership_id = current_membership_id()
          and branch_role_assignment.branch_id = low_stock_report.branch_id
      )
    )
  );

grant select, insert, update, delete on low_stock_report to authenticated;
grant select, insert, update, delete on low_stock_report to service_role;
