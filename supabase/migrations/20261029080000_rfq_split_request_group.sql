-- 20261029080000_rfq_split_request_group.sql — a split of an RFQ becomes one group of purchase
-- requests (spec 024 data-model.md, research R4/R5).
--
-- * basket_split_job.rfq_id — the RFQ a split was started from (null for a standalone split).
-- * purchase_request_group — the single act of turning one RFQ's split into requests. Immutable
--   evidence: which split, which branch, and the totals and saving as computed when it was
--   prepared (Constitution I). One per RFQ (an RFQ converts once), one per idempotency key.
--   Its state is the state of its requests; nothing is stored twice.
-- * purchase_request.request_group_id — the group a request belongs to; such requests are
--   submitted, approved, rejected and withdrawn only together (owner decision Q2), routed by the
--   group's combined total.
-- * approval_step_source gains 'group_threshold_match' for steps routed by that combined total.
--
-- Tenancy: every reference is a composite (tenant_id, id) foreign key; the new table has ENABLE +
-- FORCE row-level security with USING and WITH CHECK; client roles may read and insert it, never
-- update or delete it.

alter type approval_step_source add value if not exists 'group_threshold_match';

alter table basket_split_job
  add constraint basket_split_job_tenant_id_key unique (tenant_id, id);

alter table basket_split_job
  add column rfq_id uuid,
  add constraint basket_split_job_rfq_fkey
    foreign key (tenant_id, rfq_id) references rfq (tenant_id, id);

create table purchase_request_group (
  id                          uuid primary key default gen_random_uuid(),
  tenant_id                   uuid not null references tenant (id) on delete cascade,
  rfq_id                      uuid not null,
  basket_split_job_id         uuid not null,
  branch_id                   uuid not null,
  combined_total_amount       numeric(18, 4) not null check (combined_total_amount >= 0),
  combined_total_currency     text not null references supported_currency (code),
  best_single_total_amount    numeric(18, 4) check (best_single_total_amount >= 0),
  best_single_total_currency  text references supported_currency (code),
  saving_amount               numeric(18, 4) check (saving_amount >= 0),
  saving_currency             text references supported_currency (code),
  idempotency_key             uuid not null,
  created_by_membership_id    uuid not null,
  created_at                  timestamptz not null default now(),

  constraint purchase_request_group_tenant_id_key unique (tenant_id, id),
  constraint purchase_request_group_one_per_rfq unique (tenant_id, rfq_id),
  constraint purchase_request_group_idempotency_key unique (tenant_id, idempotency_key),
  constraint purchase_request_group_rfq_fkey
    foreign key (tenant_id, rfq_id) references rfq (tenant_id, id),
  constraint purchase_request_group_job_fkey
    foreign key (tenant_id, basket_split_job_id) references basket_split_job (tenant_id, id),
  constraint purchase_request_group_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id),
  constraint purchase_request_group_created_by_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id),
  constraint purchase_request_group_best_single_has_currency
    check ((best_single_total_amount is null) = (best_single_total_currency is null)),
  constraint purchase_request_group_saving_has_currency
    check ((saving_amount is null) = (saving_currency is null))
);

create index purchase_request_group_tenant_idx on purchase_request_group (tenant_id);

alter table purchase_request_group enable row level security;
alter table purchase_request_group force row level security;

create policy purchase_request_group_select on purchase_request_group
  for select
  using (tenant_id = current_tenant_id());

create policy purchase_request_group_insert on purchase_request_group
  for insert
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

revoke all on purchase_request_group from public, anon, authenticated;
grant select, insert on purchase_request_group to authenticated;
grant select, insert, update, delete on purchase_request_group to service_role;

alter table purchase_request
  add column request_group_id uuid,
  add constraint purchase_request_request_group_fkey
    foreign key (tenant_id, request_group_id) references purchase_request_group (tenant_id, id);

create index purchase_request_request_group_idx
  on purchase_request (request_group_id)
  where request_group_id is not null;
