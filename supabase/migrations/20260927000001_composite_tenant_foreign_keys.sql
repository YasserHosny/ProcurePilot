-- 20260927000001_composite_tenant_foreign_keys.sql
--
-- PR2 follow-up finding 6: a plain single-column foreign key from a tenant-scoped child table to
-- another tenant-scoped parent only checks that the referenced row exists ANYWHERE, not that it
-- belongs to the SAME tenant as the child's own tenant_id -- which already passed the child's own
-- RLS check. That is both a cross-tenant existence oracle (an insert/update's success or failure
-- reveals whether a guessed id exists somewhere in the system, even one the caller's own RLS would
-- otherwise hide) and a genuine data-corruption risk: a tenant-A row could end up referencing a
-- tenant-B parent, undetected, since nothing else in the schema checks it.
--
-- 20260822000036 (membership) and 20260823000042 (workspace_product, landed_cost) already
-- established the fix for this exact gap ("GitHub issue #7"): add `unique (tenant_id, id)` on the
-- parent, then a composite FK `(tenant_id, child_col) references parent(tenant_id, id)` on the
-- child, so a cross-tenant reference can never satisfy both columns at once. That pattern has been
-- followed for every table introduced since, but a full audit (PR2 follow-up finding 6, run
-- 2026-09-27) found 45 pre-existing single-column FKs across 20 tables whose parent already
-- carries that unique constraint -- simply never retrofitted. This migration closes all 45 in one
-- pass. A further 6 FKs need a NEW unique constraint added to their parent first (document,
-- match_candidate, match_decision, product_alias) -- deliberately left for a follow-up migration,
-- since adding a unique constraint to an existing table needs its own data-integrity check first.
--
-- A composite ON DELETE SET NULL defaults to nulling EVERY referencing column, including
-- tenant_id -- which is NOT NULL everywhere, so that would break every affected delete
-- outright. Each of the 7 SET NULL cases below names the single non-tenant column to null
-- (Postgres 15+'s column-scoped ON DELETE SET NULL (col) syntax), so tenant_id is never
-- touched.
--
-- Purely corrective, no column or data changes: a local audit confirmed zero existing rows would
-- violate any of these 45 constraints before this migration runs. Each replacement FK keeps the
-- exact ON DELETE/ON UPDATE action the original single-column FK had.

do $$
declare
  rec record;
begin
  for rec in
    select * from (values
    ('quotation', 'quotation_previous_quotation_id_fkey', 'previous_quotation_id', 'quotation', ''),
    ('quotation', 'quotation_reviewed_by_fkey', 'reviewed_by', 'membership', ''),
    ('quotation_line', 'quotation_line_quotation_id_fkey', 'quotation_id', 'quotation', 'ON DELETE CASCADE'),
    ('product_substitute', 'product_substitute_substitute_product_id_fkey', 'substitute_product_id', 'workspace_product', 'ON DELETE CASCADE'),
    ('product_alias', 'product_alias_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', 'ON DELETE CASCADE'),
    ('member_invitation', 'member_invitation_invited_by_fkey', 'invited_by', 'membership', ''),
    ('audit_event', 'audit_event_actor_membership_id_fkey', 'actor_membership_id', 'membership', 'ON DELETE SET NULL (actor_membership_id)'),
    ('product_alias', 'product_alias_supplier_id_fkey', 'supplier_id', 'supplier', 'ON DELETE SET NULL (supplier_id)'),
    ('product_alias', 'product_alias_created_by_fkey', 'created_by', 'membership', 'ON DELETE SET NULL (created_by)'),
    ('pack_definition', 'pack_definition_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', 'ON DELETE CASCADE'),
    ('product_substitute', 'product_substitute_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', 'ON DELETE CASCADE'),
    ('workspace_product', 'workspace_product_preferred_supplier_fkey', 'preferred_supplier_id', 'supplier', 'ON DELETE SET NULL (preferred_supplier_id)'),
    ('import_job', 'import_job_created_by_fkey', 'created_by', 'membership', 'ON DELETE SET NULL (created_by)'),
    ('document', 'document_created_by_fkey', 'created_by', 'membership', ''),
    ('quotation', 'quotation_supplier_id_fkey', 'supplier_id', 'supplier', ''),
    ('field_extraction', 'field_extraction_quotation_id_fkey', 'quotation_id', 'quotation', 'ON DELETE CASCADE'),
    ('field_extraction', 'field_extraction_corrected_by_fkey', 'corrected_by', 'membership', ''),
    ('extraction_job', 'extraction_job_quotation_id_fkey', 'quotation_id', 'quotation', 'ON DELETE CASCADE'),
    ('review_task', 'review_task_quotation_id_fkey', 'quotation_id', 'quotation', 'ON DELETE CASCADE'),
    ('match_candidate', 'match_candidate_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', 'ON DELETE CASCADE'),
    ('match_candidate', 'match_candidate_candidate_workspace_product_id_fkey', 'candidate_workspace_product_id', 'workspace_product', ''),
    ('match_task', 'match_task_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', 'ON DELETE CASCADE'),
    ('match_decision', 'match_decision_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', 'ON DELETE CASCADE'),
    ('match_decision', 'match_decision_matched_workspace_product_id_fkey', 'matched_workspace_product_id', 'workspace_product', ''),
    ('match_decision', 'match_decision_decided_by_fkey', 'decided_by', 'membership', ''),
    ('landed_cost', 'landed_cost_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', 'ON DELETE CASCADE'),
    ('purchase_record', 'purchase_record_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', ''),
    ('purchase_record', 'purchase_record_landed_cost_id_fkey', 'landed_cost_id', 'landed_cost', ''),
    ('basket_split_job', 'basket_split_job_requested_by_fkey', 'requested_by', 'membership', ''),
    ('alert_dismissal', 'alert_dismissal_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', 'ON DELETE CASCADE'),
    ('alert_dismissal', 'alert_dismissal_supplier_id_fkey', 'supplier_id', 'supplier', 'ON DELETE CASCADE'),
    ('alert_dismissal', 'alert_dismissal_dismissed_by_fkey', 'dismissed_by', 'membership', ''),
    ('purchase_record', 'purchase_record_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', ''),
    ('purchase_record', 'purchase_record_supplier_id_fkey', 'supplier_id', 'supplier', ''),
    ('purchase_record', 'purchase_record_recorded_by_fkey', 'recorded_by', 'membership', ''),
    ('saving_record', 'saving_record_purchase_record_id_fkey', 'purchase_record_id', 'purchase_record', 'ON DELETE CASCADE'),
    ('saving_record', 'saving_record_workspace_product_id_fkey', 'workspace_product_id', 'workspace_product', ''),
    ('saving_record', 'saving_record_supplier_id_fkey', 'supplier_id', 'supplier', ''),
    ('saving_record', 'saving_record_recorded_by_fkey', 'recorded_by', 'membership', ''),
    ('saving_record', 'saving_record_verified_by_fkey', 'verified_by', 'membership', ''),
    ('export_job', 'export_job_requested_by_fkey', 'requested_by', 'membership', ''),
    ('quotation', 'quotation_suggested_supplier_id_fkey', 'suggested_supplier_id', 'supplier', 'ON DELETE SET NULL (suggested_supplier_id)'),
    ('match_resolution_idempotency', 'match_resolution_idempotency_quotation_line_id_fkey', 'quotation_line_id', 'quotation_line', 'ON DELETE CASCADE'),
    ('ingestion_email_log', 'ingestion_email_log_quotation_id_fkey', 'quotation_id', 'quotation', 'ON DELETE SET NULL (quotation_id)'),
    ('auto_preparation_guardrail', 'auto_preparation_guardrail_default_branch_id_fkey', 'default_branch_id', 'branch', '')
    ) as t(child_table, old_conname, col, parent_table, tail)
  loop
    execute format('alter table %I drop constraint %I', rec.child_table, rec.old_conname);
    execute format(
      'alter table %I add constraint %I foreign key (tenant_id, %I) references %I (tenant_id, id) %s',
      rec.child_table, rec.old_conname, rec.col, rec.parent_table, rec.tail
    );
  end loop;
end $$;
