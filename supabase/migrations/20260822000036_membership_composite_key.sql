-- 20260822000036_membership_composite_key.sql — task T001, chunk R2.0
--
-- Purely additive: no existing column, data, or behaviour changes. The existing
-- membership_one_per_person_per_tenant unique constraint on (tenant_id, user_id) is untouched.
--
-- Enables composite (tenant_id, id) foreign keys from this chunk's new tables
-- (branch_role_assignment.membership_id, cost_centre.budget_owner_membership_id,
-- budget.created_by) so a tenant-A row can never reference a tenant-B membership row while
-- still passing its own table's tenant_id RLS check — closing the class of gap tracked in
-- GitHub issue #7 (a single-column FK checks existence only, not tenant ownership).

alter table membership add constraint membership_tenant_id_key unique (tenant_id, id);
