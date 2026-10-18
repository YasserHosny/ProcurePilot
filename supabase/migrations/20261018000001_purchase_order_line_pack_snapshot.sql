-- ADR-020: quantities and prices are per purchasing pack; preserve its historical size.
alter table purchase_order_line
  add column if not exists pack_base_quantity numeric(18,6)
  check (pack_base_quantity is null or pack_base_quantity > 0);

comment on column purchase_order_line.pack_base_quantity is
  'Pack size in base units at PO creation/edit, per ADR-020; null when no pack is known.';

-- The catalogue expects a single pack per product and rejects duplicates. For legacy
-- duplicates, use the newest definition with an ID tie-breaker, as in the order inserts.
with packs as (
  select distinct on (tenant_id, workspace_product_id)
    tenant_id, workspace_product_id, base_quantity
  from pack_definition
  order by tenant_id, workspace_product_id, created_at desc, id desc
)
update purchase_order_line line
set pack_base_quantity = packs.base_quantity
from packs
where packs.tenant_id = line.tenant_id
  and packs.workspace_product_id = line.workspace_product_id
  and line.pack_base_quantity is null;
