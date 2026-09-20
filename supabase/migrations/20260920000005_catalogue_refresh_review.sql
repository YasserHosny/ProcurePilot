-- Reviewable output of a scheduled CSV refresh. This is a preview, not a price mutation.

create table if not exists catalogue_refresh_review (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references tenant(id) on delete cascade,
  refresh_schedule_id  uuid not null,
  source_import_id     uuid not null,
  supplier_id          uuid not null,
  status               text not null default 'pending_review'
                       check (status in ('pending_review', 'approved', 'rejected')),
  normalized_rows      jsonb not null default '[]'::jsonb,
  errors               jsonb not null default '[]'::jsonb,
  row_count            integer not null default 0 check (row_count >= 0),
  error_count          integer not null default 0 check (error_count >= 0),
  created_at           timestamptz not null default now(),
  reviewed_at          timestamptz,
  reviewed_by          uuid,

  constraint catalogue_refresh_review_tenant_id_key unique (tenant_id, id),
  constraint catalogue_refresh_review_schedule_fkey
    foreign key (tenant_id, refresh_schedule_id)
    references offer_refresh_schedule (tenant_id, id) on delete cascade,
  constraint catalogue_refresh_review_source_fkey
    foreign key (tenant_id, source_import_id)
    references catalogue_imports (tenant_id, id) on delete cascade,
  constraint catalogue_refresh_review_supplier_fkey
    foreign key (tenant_id, supplier_id)
    references supplier (tenant_id, id) on delete cascade,
  constraint catalogue_refresh_review_member_fkey
    foreign key (tenant_id, reviewed_by)
    references membership (tenant_id, id),
  constraint catalogue_refresh_review_unique_source
    unique (tenant_id, refresh_schedule_id, source_import_id),
  constraint catalogue_refresh_review_rows_array
    check (jsonb_typeof(normalized_rows) = 'array'),
  constraint catalogue_refresh_review_errors_array
    check (jsonb_typeof(errors) = 'array'),
  constraint catalogue_refresh_review_reviewed_state
    check ((status = 'pending_review') = (reviewed_at is null and reviewed_by is null))
);

create index if not exists catalogue_refresh_review_tenant_status_idx
  on catalogue_refresh_review (tenant_id, status, created_at desc);

alter table catalogue_refresh_review enable row level security;
alter table catalogue_refresh_review force row level security;

create policy catalogue_refresh_review_tenant_select on catalogue_refresh_review
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy catalogue_refresh_review_owner_buyer_update on catalogue_refresh_review
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and reviewed_by = current_membership_id()
  );

grant select on catalogue_refresh_review to authenticated;
grant update on catalogue_refresh_review to authenticated;
grant select, insert, update on catalogue_refresh_review to service_role;
