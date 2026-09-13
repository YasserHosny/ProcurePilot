-- 20260913000004_delivery_quality_issue_photo.sql — task T004, chunk R2.3 (Mobile Approvals and
-- Delivery Receipt)
--
-- delivery_quality_issue_photo — one row per photo attached to a quality issue (many-to-one
-- child, not a single photo column on the issue itself, so "zero or more photos" is a natural
-- cardinality rather than an artificial limit — specs/010-mobile-approvals-receipt/data-model.md).
-- Same tenant-isolation and derived-visibility shape as delivery_quality_issue, one join level
-- deeper.

create table if not exists delivery_quality_issue_photo (
  id                             uuid primary key default gen_random_uuid(),
  tenant_id                      uuid not null references tenant(id) on delete cascade,
  delivery_quality_issue_id      uuid not null,
  storage_path                   text not null,
  created_at                     timestamptz not null default now(),

  constraint delivery_quality_issue_photo_issue_fkey
    foreign key (tenant_id, delivery_quality_issue_id)
    references delivery_quality_issue (tenant_id, id) on delete cascade,

  constraint delivery_quality_issue_photo_storage_path_not_empty
    check (char_length(storage_path) > 0)
);

create index if not exists delivery_quality_issue_photo_tenant_idx
  on delivery_quality_issue_photo (tenant_id);
create index if not exists delivery_quality_issue_photo_issue_idx
  on delivery_quality_issue_photo (tenant_id, delivery_quality_issue_id);

comment on table delivery_quality_issue_photo is
  'One photo attached to a delivery_quality_issue (chunk R2.3). storage_path is allocated
   server-side under tenants/{tenant_id}/quality-issues/{issue_id}/{filename} — never
   client-supplied. Insert-only; no PATCH/DELETE surface this release.';

alter table delivery_quality_issue_photo enable row level security;
alter table delivery_quality_issue_photo force  row level security;

create policy delivery_quality_issue_photo_tenant_isolation on delivery_quality_issue_photo
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

create policy delivery_quality_issue_photo_scoped_visibility on delivery_quality_issue_photo
  as restrictive
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from delivery_quality_issue
      join purchase_request
        on purchase_request.tenant_id = delivery_quality_issue.tenant_id
        and purchase_request.id = delivery_quality_issue.purchase_request_id
      where delivery_quality_issue.tenant_id = delivery_quality_issue_photo.tenant_id
        and delivery_quality_issue.id = delivery_quality_issue_photo.delivery_quality_issue_id
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

grant select, insert on delivery_quality_issue_photo to authenticated;
grant select, insert, update, delete on delivery_quality_issue_photo to service_role;
