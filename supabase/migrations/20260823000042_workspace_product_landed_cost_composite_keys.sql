-- 20260823000042_workspace_product_landed_cost_composite_keys.sql — task T002, chunk R2.1
--
-- Purely additive: no existing column, data, or behaviour changes on either table.
--
-- Enables composite (tenant_id, id) foreign keys from purchase_request_line
-- (workspace_product_id, estimated_unit_price_source_landed_cost_id) so a tenant-A line can
-- never reference a tenant-B product or landed-cost row while still passing its own table's
-- tenant_id RLS check — the same GitHub issue #7 gap R2.0's membership_composite_key migration
-- closed for membership, now closed here for the two pre-R2.0 tables this chunk is the first to
-- reference from a composite-FK-convention table. Neither workspace_product nor landed_cost was
-- retrofitted by R2.0, since R2.0 itself never referenced either.

alter table workspace_product add constraint workspace_product_tenant_id_key unique (tenant_id, id);
alter table landed_cost       add constraint landed_cost_tenant_id_key       unique (tenant_id, id);
