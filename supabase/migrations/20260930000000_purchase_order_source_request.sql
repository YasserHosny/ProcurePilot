-- 20260930000000_purchase_order_source_request.sql — T002: Link purchase orders to purchase requests (US4)

-- Existing purchase_request_line has no tenant/id composite key. Add one so its
-- tenant-pinned reference from purchase_order_line can be enforced by PostgreSQL.
alter table purchase_request_line
  add constraint purchase_request_line_tenant_id_key unique (tenant_id, id);

-- 2. Link purchase_order to purchase_request
alter table purchase_order
  add column source_request_id uuid;

alter table purchase_order
  add constraint purchase_order_source_request_fkey
  foreign key (tenant_id, source_request_id) references purchase_request (tenant_id, id);

create index if not exists purchase_order_source_request_idx
  on purchase_order (tenant_id, source_request_id);

-- 3. Link purchase_order_line to purchase_request_line
alter table purchase_order_line
  add column source_request_line_id uuid;

alter table purchase_order_line
  add constraint purchase_order_line_source_request_line_fkey
  foreign key (tenant_id, source_request_line_id) references purchase_request_line (tenant_id, id);

create index if not exists purchase_order_line_source_request_line_idx
  on purchase_order_line (tenant_id, source_request_line_id);

-- Note on Constraints and RLS:
-- - `source_request_id` and `source_request_line_id` are deliberately NOT unique to allow one-to-many
--   split allocations (one request -> many POs).
-- - Service-layer (T004/T005) handles approval state validation; no DB constraint is added for `status = 'approved'`.
-- - Existing ENABLE + FORCE row level security on `purchase_order` and `purchase_order_line`
--   remains fully in force and protects these new columns automatically.
-- - No policies were altered or weakened in this migration.
