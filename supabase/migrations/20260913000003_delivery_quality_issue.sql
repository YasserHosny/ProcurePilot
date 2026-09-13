-- 20260913000003_delivery_quality_issue.sql — task T003, chunk R2.3 (Mobile Approvals and
-- Delivery Receipt)
--
-- delivery_quality_issue — a report of a problem with a delivered request (damaged, wrong item,
-- spoiled), distinct from the plain quantity-shortfall fact purchase_request/
-- purchase_request_line already capture (specs/010-mobile-approvals-receipt/data-model.md).
-- Visibility is inherited via purchase_request_id, mirroring purchase_request_line's own
-- established idiom (20260823000043_purchase_request_line.sql) rather than duplicating branch_id
-- onto this table — an EXISTS join against the parent row is this codebase's own established RLS
-- pattern for a request-child table, not a new one.
--
-- Insert-only this release (no PATCH/DELETE surface) — a filed quality issue is not editable or
-- retractable, the same insert-only posture low_stock_report already established for its own raw
-- signal data, with UPDATE/DELETE explicitly withheld from the grant rather than relying on a
-- RESTRICTIVE policy alone (mirrors low_stock_report's own review-fix precedent,
-- 20260912000004_low_stock_report_review_fixes.sql).

create table if not exists delivery_quality_issue (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   uuid not null references tenant(id) on delete cascade,
  purchase_request_id         uuid not null,
  reported_by_membership_id   uuid not null,
  description                 text not null,
  created_at                  timestamptz not null default now(),

  constraint delivery_quality_issue_tenant_id_key unique (tenant_id, id),

  constraint delivery_quality_issue_request_fkey
    foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id) on delete cascade,
  constraint delivery_quality_issue_reporter_fkey
    foreign key (tenant_id, reported_by_membership_id) references membership (tenant_id, id),

  constraint delivery_quality_issue_description_not_empty check (char_length(description) > 0)
);

create index if not exists delivery_quality_issue_tenant_idx on delivery_quality_issue (tenant_id);
create index if not exists delivery_quality_issue_request_idx
  on delivery_quality_issue (tenant_id, purchase_request_id);

comment on table delivery_quality_issue is
  'A report of a problem with a delivered request (chunk R2.3) — damaged, wrong item, spoiled.
   Insert-only; no PATCH/DELETE surface this release. The parent purchase_request must be in
   status delivered at the time of insert, enforced at the service layer (application-layer
   precondition, same convention approval_step''s own migration documents for its
   assignee/owner write check).';

alter table delivery_quality_issue enable row level security;
alter table delivery_quality_issue force  row level security;

create policy delivery_quality_issue_tenant_isolation on delivery_quality_issue
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, SELECT-only: a quality issue is visible exactly when its parent purchase_request
-- is visible under that table's own scoped-visibility policy — re-derived via EXISTS join, the
-- same reasoning purchase_request_line_scoped_visibility already documents (RLS policies cannot
-- reference another table's policy directly, only its rows via a join).
create policy delivery_quality_issue_scoped_visibility on delivery_quality_issue
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from purchase_request
      where purchase_request.tenant_id = delivery_quality_issue.tenant_id
        and purchase_request.id = delivery_quality_issue.purchase_request_id
        and (
          current_member_role() = 'owner'
          or purchase_request.requested_by_membership_id = current_membership_id()
          or not exists (
            select 1 from branch_role_assignment
            where branch_role_assignment.tenant_id = purchase_request.tenant_id
              and branch_role_assignment.membership_id = current_membership_id()
          )
          or exists (
            select 1 from branch_role_assignment
            where branch_role_assignment.tenant_id = purchase_request.tenant_id
              and branch_role_assignment.membership_id = current_membership_id()
              and branch_role_assignment.branch_id = purchase_request.branch_id
          )
        )
    )
  );

-- Insert-only for authenticated — no update/delete grant, per the note above.
grant select, insert on delivery_quality_issue to authenticated;
grant select, insert, update, delete on delivery_quality_issue to service_role;
