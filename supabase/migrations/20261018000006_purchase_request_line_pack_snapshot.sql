-- ADR-020: request quantities and prices are per purchasing pack; preserve its historical size.
alter table purchase_request_line
  add column if not exists pack_base_quantity numeric(18,6)
  check (pack_base_quantity is null or pack_base_quantity > 0);

comment on column purchase_request_line.pack_base_quantity is
  'Pack size in base units at request line creation/edit, per ADR-020; null when no pack is known.';

-- Existing ENABLE + FORCE RLS and tenant/scoped-visibility policies cover the new column.
-- Grants are table-level (20260823000043, including authenticated re-granted by
-- 20261018000005_public_table_least_privilege.sql); no column-level grant list exists
-- for purchase_request_line. No RLS or grant change is needed.

-- Current packs are mutable, so only backfill a null snapshot when the newest pack
-- already existed at line creation and no subsequent catalogue update could have changed it.
-- Product edits identify target.product_id. CSV updates only record the batch action
-- catalogue.import_committed (target.kind / target.updated), without affected product IDs:
-- conservatively exclude ALL lines predating an updating product import in that tenant.
-- audit_event has target jsonb and occurred_at (not target_id or created_at).
-- Unprovable historical pack sizes remain NULL; reruns preserve existing snapshots.
with packs as (
  select distinct on (tenant_id, workspace_product_id)
    tenant_id, workspace_product_id, base_quantity, created_at
  from pack_definition
  order by tenant_id, workspace_product_id, created_at desc, id desc
)
update purchase_request_line line
set pack_base_quantity = packs.base_quantity
from packs
where packs.tenant_id = line.tenant_id
  and packs.workspace_product_id = line.workspace_product_id
  and line.pack_base_quantity is null
  and packs.created_at <= line.created_at
  and not exists (
    select 1
    from audit_event event
    where event.tenant_id = line.tenant_id
      and event.occurred_at > line.created_at
      and (
        (event.action = 'catalogue.product_updated'
          and event.target ->> 'product_id' = line.workspace_product_id::text)
        or (event.action = 'catalogue.import_committed'
          and event.target ->> 'kind' = 'products'
          and (event.target ->> 'updated')::numeric > 0)
      )
  );
