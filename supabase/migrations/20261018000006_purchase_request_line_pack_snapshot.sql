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

-- Match the PO snapshot migration: newest pack per tenant/product, ID breaking ties.
-- Only backfill null snapshots, so reruns never overwrite an existing historical value.
with packs as (
  select distinct on (tenant_id, workspace_product_id)
    tenant_id, workspace_product_id, base_quantity
  from pack_definition
  order by tenant_id, workspace_product_id, created_at desc, id desc
)
update purchase_request_line line
set pack_base_quantity = packs.base_quantity
from packs
where packs.tenant_id = line.tenant_id
  and packs.workspace_product_id = line.workspace_product_id
  and line.pack_base_quantity is null;
