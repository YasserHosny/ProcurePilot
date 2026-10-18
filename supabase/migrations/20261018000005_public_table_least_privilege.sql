-- 20261018000005_public_table_least_privilege.sql — least-privilege table grants for the
-- anon and authenticated roles.
--
-- Earlier migrations GRANT only the rights each table needs (for example
-- `grant select, insert on supplier_commercial_term to authenticated`) and
-- assume nothing else is granted. That holds on the Supabase CLI local stack,
-- whose default privileges in schema public give anon/authenticated no
-- SELECT/INSERT/UPDATE/DELETE. A project whose default privileges grant ALL to
-- anon, authenticated and service_role on every new table keeps those rights
-- alongside the narrow grants, so the narrow grants never take effect there.
--
-- This migration:
--   1. revokes every table and sequence privilege in schema public from anon
--      and authenticated (this includes TRUNCATE, REFERENCES, TRIGGER, MAINTAIN);
--   2. re-grants exactly the rights the earlier migrations grant explicitly.
--      The list was taken from a database built from every earlier migration
--      with all default privileges removed, and matches the CLI local stack
--      that CI runs the API and isolation suites against;
--   3. changes the default privileges of role postgres (and supabase_admin when
--      the migrating role may) so new tables and sequences grant nothing to
--      anon or authenticated. Every new table must GRANT what it needs in its
--      own migration, next to its RLS policies.
--
-- Not changed: service_role grants, function EXECUTE grants (see
-- 20261018000004_definer_caller_tenant_guard.sql), RLS policies, and the auth,
-- storage and realtime schemas.

-- 1. Revoke everything from anon and authenticated.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- 2. Re-grant the intended rights.
-- anon: select (4 tables)
grant select on
  supported_base_unit,
  supported_currency,
  supported_region,
  supported_tax_model
to anon;

-- authenticated: select, insert, update, delete (44 tables)
grant select, insert, update, delete on
  alert_dismissal,
  approval_delegation,
  approval_step,
  auto_preparation_guardrail,
  basket_split_job,
  billing_account,
  branch,
  branch_role_assignment,
  budget,
  catalogue_imports,
  cost_centre,
  device_registration,
  digest_subscription,
  document,
  export_job,
  extraction_job,
  field_extraction,
  import_job,
  ingestion_email_log,
  ingestion_jobs,
  match_task,
  member_invitation,
  membership,
  pack_definition,
  product_alias,
  product_substitute,
  purchase_order_line,
  purchase_record,
  purchase_request,
  purchase_request_line,
  quotation,
  quotation_line,
  report_schedule,
  review_task,
  rfq,
  rfq_line,
  rfq_recipient,
  rfq_response,
  supplier,
  synced_bill_line,
  tenant,
  tenant_email_config,
  threshold_rule,
  workspace_product
to authenticated;

-- authenticated: select, insert, update (9 tables)
grant select, insert, update on
  offer_refresh_schedule,
  purchase_order,
  reorder_proposal,
  saving_record,
  synced_bill,
  synced_product_signal,
  synced_vendor,
  three_way_match,
  webhook_subscription
to authenticated;

-- authenticated: select, insert, delete (2 tables)
grant select, insert, delete on
  pos_product_match,
  purchase_bill_match
to authenticated;

-- authenticated: select, insert (28 tables)
grant select, insert on
  analyst_conversation,
  analyst_turn,
  analyst_turn_citation,
  audit_event,
  auto_preparation_event,
  delivery_quality_issue,
  delivery_quality_issue_photo,
  delivery_receipt,
  delivery_receipt_line,
  demand_forecast,
  landed_cost,
  low_stock_report,
  match_bulk_confirmation,
  match_candidate,
  match_decision,
  match_resolution_idempotency,
  negotiation_brief,
  negotiation_brief_action,
  negotiation_brief_item,
  negotiation_brief_item_evidence,
  purchase_order_edit_idempotency,
  supplier_commercial_term,
  supplier_confirmation,
  supplier_confirmation_line,
  supplier_iq_recompute_idempotency,
  supplier_scorecard_evidence,
  supplier_scorecard_metric,
  supplier_scorecard_snapshot
to authenticated;

-- authenticated: select, update (1 tables)
grant select, update on
  catalogue_refresh_review
to authenticated;

-- authenticated: select (8 tables)
grant select on
  canonical_product,
  plan,
  reconciliation_discrepancy,
  supported_base_unit,
  supported_currency,
  supported_region,
  supported_tax_model,
  webhook_delivery
to authenticated;
-- Column-level grants. A table-level REVOKE ALL also removes column privileges, so these are
-- restated exactly as 20260918000002 (accounting_connection), 20260919000001 (pos_connection)
-- and 20260919000007 (reconciliation_discrepancy, superseding 20260918000006) grant them. access_token and refresh_token stay
-- out of authenticated's SELECT and UPDATE; only the one-time INSERT at connect time sees them.
grant select (
  id, tenant_id, provider, realm_id, display_name, status, connected_by, connected_at,
  last_synced_at, disconnected_at, created_at, updated_at
) on accounting_connection to authenticated;
grant insert (
  id, tenant_id, provider, realm_id, display_name, access_token, refresh_token, status,
  connected_by, connected_at
) on accounting_connection to authenticated;
grant update (
  status, last_synced_at, disconnected_at, updated_at
) on accounting_connection to authenticated;

grant select (
  id, tenant_id, provider, external_account_id, external_account_name, status, connected_by,
  connected_at, last_synced_at, disconnected_at, created_at, updated_at
) on pos_connection to authenticated;
grant insert (
  id, tenant_id, provider, external_account_id, external_account_name, access_token,
  refresh_token, status, connected_by, connected_at
) on pos_connection to authenticated;
grant update (
  status, last_synced_at, disconnected_at, updated_at
) on pos_connection to authenticated;

-- reconciliation_discrepancy: table-level SELECT (above) plus these column-level writes.
grant insert (
  tenant_id, discrepancy_type, synced_bill_id, purchase_record_id, status, detected_at,
  three_way_match_id, purchase_order_id, evidence, source_hash, source_updated_at, reopened_at
) on reconciliation_discrepancy to authenticated;
grant update (
  status, resolved_by, resolved_at, resolution_note, three_way_match_id, purchase_order_id,
  evidence, source_hash, source_updated_at, reopened_at
) on reconciliation_discrepancy to authenticated;

-- audit_event.id is a serial column; authenticated inserts audit rows.
grant usage, select on sequence audit_event_id_seq to authenticated;

-- 3. Future tables and sequences grant nothing to anon or authenticated.
alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated;

do $$
begin
  if pg_has_role(current_user, 'supabase_admin', 'MEMBER') then
    execute 'alter default privileges for role supabase_admin in schema public '
            'revoke all on tables from anon, authenticated';
    execute 'alter default privileges for role supabase_admin in schema public '
            'revoke all on sequences from anon, authenticated';
  else
    raise notice 'skipping supabase_admin default privileges: % is not a member of supabase_admin',
      current_user;
  end if;
end
$$;
