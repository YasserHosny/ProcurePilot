-- 20260930000003_purchase_order_request_line_integrity.sql — US4 request-line integrity
--
-- Design choice: this migration uses composite, tenant-pinned foreign keys instead of a trigger.
-- `purchase_order_line.source_request_id` mirrors the nullable header link so PostgreSQL can
-- enforce two facts declaratively: the line belongs to the same source request as its order header,
-- and the referenced request line belongs to that same request. Existing manual purchase orders keep
-- both line source columns null and are unaffected.

alter table purchase_request_line
  add constraint purchase_request_line_tenant_request_id_key
  unique (tenant_id, purchase_request_id, id);

alter table purchase_order
  add constraint purchase_order_tenant_id_source_request_id_key
  unique (tenant_id, id, source_request_id);

alter table purchase_order_line
  add column source_request_id uuid;

update purchase_order_line pol
set source_request_id = po.source_request_id
from purchase_order po
where po.tenant_id = pol.tenant_id
  and po.id = pol.purchase_order_id
  and pol.source_request_line_id is not null
  and pol.source_request_id is null;

alter table purchase_order_line
  add constraint purchase_order_line_source_link_pair_check
  check (
    (source_request_id is null and source_request_line_id is null)
    or (source_request_id is not null and source_request_line_id is not null)
  );

alter table purchase_order_line
  add constraint purchase_order_line_header_source_request_fkey
  foreign key (tenant_id, purchase_order_id, source_request_id)
  references purchase_order (tenant_id, id, source_request_id);

alter table purchase_order_line
  add constraint purchase_order_line_source_request_line_belongs_to_request_fkey
  foreign key (tenant_id, source_request_id, source_request_line_id)
  references purchase_request_line (tenant_id, purchase_request_id, id);

create index if not exists purchase_order_line_source_request_pair_idx
  on purchase_order_line (tenant_id, source_request_id, source_request_line_id);

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'purchase_order_line'
      and policyname = 'purchase_order_line_owner_buyer_delete'
  ) then
    create policy purchase_order_line_owner_buyer_delete on purchase_order_line
      for delete to authenticated
      using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
  end if;
end $$;

grant delete on purchase_order_line to authenticated;
grant delete on purchase_order_line to service_role;
